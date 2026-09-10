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
_BRANCH_RE = re.compile(r"^[A-Za-z0-9._/-]+$")
_SHA40_RE = re.compile(r"^[0-9a-fA-F]{40}$")
_DEFAULT_BRANCHES = frozenset({"main", "master"})
_MAX_FILE_BYTES = 256_000


class GitHubWriteError(RuntimeError):
    pass


class GitHubWriteBackend(Protocol):
    def post_json(self, path: str, payload: Mapping[str, object]) -> Mapping[str, object]: ...

    def put_json(self, path: str, payload: Mapping[str, object]) -> Mapping[str, object]: ...


@dataclass(frozen=True, slots=True)
class GitHubMutationReceipt:
    operation: str
    repository: str
    branch: str
    locator: str
    commit_sha: str | None = None
    pull_request: int | None = None
    payload_digest: str | None = None


class GitHubRestLabWriteBackend:
    """Narrow GitHub REST mutation backend for one trusted lab repository.

    Only three endpoint shapes exist:
    - POST /git/refs to create a branch;
    - PUT /contents/<path> to create/update a file and commit it;
    - POST /pulls to open a pull request.

    There is intentionally no PATCH, DELETE, merge, ref-update, workflow-rerun,
    release, deployment, secret, or cross-repository method.
    """

    def __init__(
        self,
        repository: str,
        *,
        token: str,
        timeout_seconds: int = 15,
        max_response_bytes: int = 1_000_000,
    ) -> None:
        if not _REPOSITORY_RE.fullmatch(repository):
            raise ValueError("repository must be owner/name")
        if not token.strip():
            raise ValueError("a runtime GitHub token is required for mutation")
        if not 1 <= timeout_seconds <= 30:
            raise ValueError("timeout_seconds must be between 1 and 30")
        if not 1 <= max_response_bytes <= 5_000_000:
            raise ValueError("max_response_bytes must be between 1 and 5,000,000")
        self.repository = repository
        self._token = token
        self._timeout_seconds = timeout_seconds
        self._max_response_bytes = max_response_bytes
        self._root = f"/repos/{repository}"

    def _validate_route(self, method: str, path: str) -> None:
        if not path.startswith(self._root + "/"):
            raise GitHubWriteError("GitHub path escaped configured repository")
        if method == "POST" and path in {f"{self._root}/git/refs", f"{self._root}/pulls"}:
            return
        if method == "PUT" and path.startswith(f"{self._root}/contents/"):
            return
        raise GitHubWriteError("GitHub mutation route is outside A5 allowlist")

    def _request(self, method: str, path: str, payload: Mapping[str, object]) -> Mapping[str, object]:
        self._validate_route(method, path)
        data = json.dumps(dict(payload), separators=(",", ":"), ensure_ascii=False).encode("utf-8")
        request = Request(
            f"https://api.github.com{path}",
            data=data,
            method=method,
            headers={
                "Accept": "application/vnd.github+json",
                "Authorization": f"Bearer {self._token}",
                "Content-Type": "application/json",
                "User-Agent": "st-music-agent-lab-a5-writer",
                "X-GitHub-Api-Version": "2022-11-28",
            },
        )
        with urlopen(request, timeout=self._timeout_seconds) as response:
            raw = response.read(self._max_response_bytes + 1)
        if len(raw) > self._max_response_bytes:
            raise GitHubWriteError("GitHub response exceeded configured byte limit")
        parsed = json.loads(raw.decode("utf-8"))
        if not isinstance(parsed, dict):
            raise GitHubWriteError("expected GitHub JSON object")
        return parsed

    def post_json(self, path: str, payload: Mapping[str, object]) -> Mapping[str, object]:
        return self._request("POST", path, payload)

    def put_json(self, path: str, payload: Mapping[str, object]) -> Mapping[str, object]:
        return self._request("PUT", path, payload)


class GitHubLabWriteAdapter:
    """Policy-gated A5 writer confined to a host-trusted lab repository."""

    def __init__(
        self,
        task: TaskSpec,
        backend: GitHubWriteBackend,
        *,
        lab_repository: str,
        branch_prefix: str = "agent/",
        policy: PolicyEngine | None = None,
    ) -> None:
        if not _REPOSITORY_RE.fullmatch(lab_repository):
            raise ValueError("lab_repository must be owner/name")
        if task.target_repository != lab_repository:
            raise PermissionError("A5 writer is confined to the trusted lab repository")
        if not branch_prefix or branch_prefix.startswith("/") or ".." in branch_prefix:
            raise ValueError("unsafe branch prefix")
        self.task = task
        self.backend = backend
        self.lab_repository = lab_repository
        self.branch_prefix = branch_prefix
        self.policy = policy or PolicyEngine()
        self._repair_attempts = 0

    @property
    def repair_attempts(self) -> int:
        return self._repair_attempts

    def _require(self, action: Action, *, branch: str | None = None, path: str | None = None) -> None:
        decision = self.policy.evaluate(
            self.task,
            ActionRequest(action=action, target_branch=branch, path=path),
        )
        if not decision.allowed:
            raise PermissionError(decision.reason)

    def _validate_task_branch(self, branch: str) -> None:
        if (
            not branch
            or len(branch) > 120
            or not _BRANCH_RE.fullmatch(branch)
            or branch.startswith("/")
            or branch.endswith("/")
            or "//" in branch
            or ".." in branch
            or branch in _DEFAULT_BRANCHES
            or not branch.startswith(self.branch_prefix)
        ):
            raise PermissionError("branch is outside the A5 task-branch boundary")

    def create_task_branch(self, branch: str, *, base_sha: str) -> GitHubMutationReceipt:
        self._validate_task_branch(branch)
        self._require(Action.CREATE_NON_DEFAULT_TASK_BRANCH, branch=branch)
        if not _SHA40_RE.fullmatch(base_sha):
            raise ValueError("branch creation requires an exact 40-character base SHA")
        locator = f"/repos/{self.lab_repository}/git/refs"
        payload = {"ref": f"refs/heads/{branch}", "sha": base_sha.lower()}
        response = dict(self.backend.post_json(locator, payload))
        obj = response.get("object")
        commit_sha = obj.get("sha") if isinstance(obj, dict) and isinstance(obj.get("sha"), str) else base_sha.lower()
        return GitHubMutationReceipt(
            operation="create_branch",
            repository=self.lab_repository,
            branch=branch,
            locator=locator,
            commit_sha=commit_sha,
            payload_digest=_digest(payload),
        )

    def write_file(
        self,
        branch: str,
        path: str,
        content: str,
        *,
        message: str,
        expected_sha: str | None = None,
    ) -> GitHubMutationReceipt:
        self._validate_task_branch(branch)
        self._require(Action.WRITE_BOUNDED_TASK_FILES, branch=branch, path=path)
        self._require(Action.COMMIT_TO_TASK_BRANCH, branch=branch)
        if not message.strip() or len(message) > 160:
            raise ValueError("commit message must contain 1-160 characters")
        encoded = content.encode("utf-8")
        if len(encoded) > _MAX_FILE_BYTES:
            raise ValueError("A5 file mutation exceeds 256,000-byte limit")
        if expected_sha is not None and not _SHA40_RE.fullmatch(expected_sha):
            raise ValueError("expected_sha must be an exact 40-character blob SHA")

        candidate = PurePosixPath(path)
        encoded_path = "/".join(quote(part, safe="") for part in candidate.parts)
        locator = f"/repos/{self.lab_repository}/contents/{encoded_path}"
        payload: dict[str, object] = {
            "message": message,
            "content": base64.b64encode(encoded).decode("ascii"),
            "branch": branch,
        }
        if expected_sha is not None:
            payload["sha"] = expected_sha.lower()
        response = dict(self.backend.put_json(locator, payload))
        commit = response.get("commit")
        commit_sha = commit.get("sha") if isinstance(commit, dict) and isinstance(commit.get("sha"), str) else None
        if commit_sha is None:
            raise GitHubWriteError("GitHub file mutation returned no commit SHA")
        return GitHubMutationReceipt(
            operation="write_file",
            repository=self.lab_repository,
            branch=branch,
            locator=locator,
            commit_sha=commit_sha,
            payload_digest=_digest(payload),
        )

    def open_pull_request(self, branch: str, *, title: str, body: str = "") -> GitHubMutationReceipt:
        self._validate_task_branch(branch)
        self._require(Action.OPEN_PULL_REQUEST, branch=branch)
        if not title.strip() or len(title) > 180:
            raise ValueError("pull request title must contain 1-180 characters")
        if branch == self.task.base_ref:
            raise ValueError("pull request head and base must differ")
        locator = f"/repos/{self.lab_repository}/pulls"
        payload = {
            "title": title,
            "head": branch,
            "base": self.task.base_ref,
            "body": body,
            "draft": False,
        }
        response = dict(self.backend.post_json(locator, payload))
        number = response.get("number")
        if not isinstance(number, int) or number <= 0:
            raise GitHubWriteError("GitHub pull request creation returned no PR number")
        head = response.get("head")
        commit_sha = head.get("sha") if isinstance(head, dict) and isinstance(head.get("sha"), str) else None
        return GitHubMutationReceipt(
            operation="open_pull_request",
            repository=self.lab_repository,
            branch=branch,
            locator=locator,
            commit_sha=commit_sha,
            pull_request=number,
            payload_digest=_digest(payload),
        )

    def claim_ci_repair_attempt(self) -> int:
        self._require(Action.BOUNDED_CI_REPAIR)
        if self._repair_attempts >= self.task.retry_budget:
            raise PermissionError("TaskSpec CI repair budget exhausted")
        self._repair_attempts += 1
        return self._repair_attempts


def _digest(payload: Mapping[str, object]) -> str:
    encoded = json.dumps(dict(payload), sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()
