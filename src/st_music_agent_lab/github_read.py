from __future__ import annotations

import base64
import hashlib
import json
import re
from dataclasses import dataclass
from pathlib import PurePosixPath
from typing import Mapping, Protocol
from urllib.parse import quote
from urllib.request import Request, urlopen

from .models import Action, ActionRequest, TaskSpec
from .policy import PolicyEngine

_REPOSITORY_RE = re.compile(r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$")
_SHA_RE = re.compile(r"^[0-9a-fA-F]{7,64}$")


class GitHubReadError(RuntimeError):
    pass


class GitHubReadBackend(Protocol):
    def get_json(self, path: str) -> Mapping[str, object]: ...

    def get_text(self, path: str, *, accept: str) -> str: ...


@dataclass(frozen=True, slots=True)
class GitHubEvidence:
    kind: str
    repository: str
    locator: str
    payload: object
    digest: str

    @classmethod
    def build(cls, *, kind: str, repository: str, locator: str, payload: object) -> "GitHubEvidence":
        encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
        return cls(
            kind=kind,
            repository=repository,
            locator=locator,
            payload=payload,
            digest=hashlib.sha256(encoded).hexdigest(),
        )


@dataclass(frozen=True, slots=True)
class PullRequestDiagnostic:
    repository: str
    pull_request: int
    state: str
    head_sha: str | None
    ci_state: str
    failing_runs: tuple[str, ...]
    evidence_locators: tuple[str, ...]


class GitHubRestReadBackend:
    """Small GET-only GitHub REST backend. No mutation methods exist by design."""

    def __init__(self, repository: str, *, token: str | None = None, timeout_seconds: int = 15, max_bytes: int = 1_000_000) -> None:
        if not _REPOSITORY_RE.fullmatch(repository):
            raise ValueError("repository must be owner/name")
        if not 1 <= timeout_seconds <= 30:
            raise ValueError("timeout_seconds must be between 1 and 30")
        if not 1 <= max_bytes <= 5_000_000:
            raise ValueError("max_bytes must be between 1 and 5,000,000")
        self.repository = repository
        self._token = token
        self._timeout_seconds = timeout_seconds
        self._max_bytes = max_bytes
        self._root = f"/repos/{repository}"

    def _request(self, path: str, *, accept: str) -> bytes:
        if not path.startswith(self._root):
            raise GitHubReadError("GitHub path escaped configured repository")
        headers = {
            "Accept": accept,
            "User-Agent": "st-music-agent-lab-read-only",
            "X-GitHub-Api-Version": "2022-11-28",
        }
        if self._token:
            headers["Authorization"] = f"Bearer {self._token}"
        request = Request(f"https://api.github.com{path}", headers=headers, method="GET")
        with urlopen(request, timeout=self._timeout_seconds) as response:
            data = response.read(self._max_bytes + 1)
        if len(data) > self._max_bytes:
            raise GitHubReadError("GitHub response exceeded configured byte limit")
        return data

    def get_json(self, path: str) -> Mapping[str, object]:
        raw = self._request(path, accept="application/vnd.github+json")
        parsed = json.loads(raw.decode("utf-8"))
        if not isinstance(parsed, dict):
            raise GitHubReadError("expected GitHub JSON object")
        return parsed

    def get_text(self, path: str, *, accept: str) -> str:
        return self._request(path, accept=accept).decode("utf-8")


class GitHubReadAdapter:
    """Policy-gated, repository-scoped, read-only GitHub inspection surface."""

    def __init__(self, task: TaskSpec, backend: GitHubReadBackend, *, policy: PolicyEngine | None = None) -> None:
        if not _REPOSITORY_RE.fullmatch(task.target_repository):
            raise ValueError("TaskSpec target_repository must be owner/name")
        self.task = task
        self.backend = backend
        self.policy = policy or PolicyEngine()

    def _require(self, action: Action) -> None:
        decision = self.policy.evaluate(self.task, ActionRequest(action=action))
        if not decision.allowed:
            raise PermissionError(decision.reason)

    def _evidence(self, kind: str, locator: str, payload: object) -> GitHubEvidence:
        return GitHubEvidence.build(kind=kind, repository=self.task.target_repository, locator=locator, payload=payload)

    def repository(self) -> GitHubEvidence:
        self._require(Action.READ_REPOSITORY)
        locator = f"/repos/{self.task.target_repository}"
        return self._evidence("repository", locator, dict(self.backend.get_json(locator)))

    def branch(self, name: str) -> GitHubEvidence:
        self._require(Action.READ_REPOSITORY)
        if not name or ".." in name or name.startswith("/"):
            raise ValueError("unsafe branch name")
        locator = f"/repos/{self.task.target_repository}/branches/{quote(name, safe='')}"
        return self._evidence("branch", locator, dict(self.backend.get_json(locator)))

    def commit(self, ref: str) -> GitHubEvidence:
        self._require(Action.READ_REPOSITORY)
        if not ref or len(ref) > 255:
            raise ValueError("invalid commit ref")
        locator = f"/repos/{self.task.target_repository}/commits/{quote(ref, safe='')}"
        return self._evidence("commit", locator, dict(self.backend.get_json(locator)))

    def file(self, path: str, *, ref: str | None = None) -> GitHubEvidence:
        self._require(Action.READ_REPOSITORY)
        candidate = PurePosixPath(path)
        if candidate.is_absolute() or ".." in candidate.parts or not path:
            raise ValueError("unsafe repository path")
        encoded_path = "/".join(quote(part, safe="") for part in candidate.parts)
        locator = f"/repos/{self.task.target_repository}/contents/{encoded_path}"
        if ref:
            locator = f"{locator}?ref={quote(ref, safe='')}"
        payload = dict(self.backend.get_json(locator))
        if payload.get("encoding") == "base64" and isinstance(payload.get("content"), str):
            try:
                decoded = base64.b64decode(payload["content"], validate=False).decode("utf-8")
            except (ValueError, UnicodeDecodeError) as exc:
                raise GitHubReadError("file content is not valid UTF-8 base64") from exc
            payload = {
                "path": payload.get("path", path),
                "sha": payload.get("sha"),
                "size": payload.get("size"),
                "content": decoded,
            }
        return self._evidence("file", locator, payload)

    def pull_request(self, number: int) -> GitHubEvidence:
        self._require(Action.INSPECT_PULL_REQUESTS)
        if number <= 0:
            raise ValueError("pull request number must be positive")
        locator = f"/repos/{self.task.target_repository}/pulls/{number}"
        return self._evidence("pull_request", locator, dict(self.backend.get_json(locator)))

    def pull_request_diff(self, number: int) -> GitHubEvidence:
        self._require(Action.INSPECT_PULL_REQUESTS)
        if number <= 0:
            raise ValueError("pull request number must be positive")
        locator = f"/repos/{self.task.target_repository}/pulls/{number}"
        diff = self.backend.get_text(locator, accept="application/vnd.github.diff")
        return self._evidence("pull_request_diff", locator, {"diff": diff})

    def workflow_runs_for_commit(self, sha: str) -> GitHubEvidence:
        self._require(Action.INSPECT_CI)
        if not _SHA_RE.fullmatch(sha):
            raise ValueError("workflow lookup requires a commit SHA")
        locator = f"/repos/{self.task.target_repository}/actions/runs?head_sha={sha}&per_page=100"
        return self._evidence("workflow_runs", locator, dict(self.backend.get_json(locator)))

    def diagnose_pull_request(self, number: int) -> PullRequestDiagnostic:
        pr = self.pull_request(number)
        payload = pr.payload if isinstance(pr.payload, dict) else {}
        head = payload.get("head")
        head_sha = head.get("sha") if isinstance(head, dict) and isinstance(head.get("sha"), str) else None
        locators = [pr.locator]
        failing: list[str] = []
        ci_state = "UNAVAILABLE"

        if head_sha and _SHA_RE.fullmatch(head_sha):
            ci = self.workflow_runs_for_commit(head_sha)
            locators.append(ci.locator)
            ci_payload = ci.payload if isinstance(ci.payload, dict) else {}
            runs = ci_payload.get("workflow_runs")
            normalized_runs = runs if isinstance(runs, list) else []
            conclusions: list[str] = []
            for run in normalized_runs:
                if not isinstance(run, dict):
                    continue
                status = run.get("status")
                conclusion = run.get("conclusion")
                name = str(run.get("name") or run.get("display_title") or "unnamed")
                if status != "completed":
                    conclusions.append("IN_PROGRESS")
                elif conclusion in {"success", "neutral", "skipped"}:
                    conclusions.append("PASS")
                else:
                    conclusions.append("FAIL")
                    failing.append(name)
            if not conclusions:
                ci_state = "NO_RUNS"
            elif "FAIL" in conclusions:
                ci_state = "FAILED"
            elif "IN_PROGRESS" in conclusions:
                ci_state = "IN_PROGRESS"
            else:
                ci_state = "PASSED"

        state = str(payload.get("state") or "unknown").upper()
        return PullRequestDiagnostic(
            repository=self.task.target_repository,
            pull_request=number,
            state=state,
            head_sha=head_sha,
            ci_state=ci_state,
            failing_runs=tuple(sorted(failing)),
            evidence_locators=tuple(locators),
        )
