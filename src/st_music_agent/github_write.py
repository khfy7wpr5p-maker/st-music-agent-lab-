from __future__ import annotations

import base64
import re
from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any
from urllib.parse import quote

from .agent_tools import ToolRegistry
from .contracts import ActionRequest, RiskLevel
from .credentials import EnvCredential
from .tools import ActionApproval, ActionResult, GuardedActionExecutor
from .transport import JsonRequest, JsonTransport, UrllibJsonTransport

_REPOSITORY = re.compile(r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$")
_SHA = re.compile(r"^(?:[0-9a-fA-F]{40}|[0-9a-fA-F]{64})$")
_BRANCH = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._/-]{0,254}$")
_SENSITIVE_BASENAMES = frozenset(
    {
        ".npmrc",
        ".pypirc",
        ".netrc",
        "credentials",
        "credentials.json",
        "secrets.json",
        "id_rsa",
        "id_ed25519",
        "id_ecdsa",
        "id_dsa",
    }
)
_SENSITIVE_DIRECTORIES = frozenset({".ssh", ".aws", ".azure", ".gcp"})
_SENSITIVE_SUFFIXES = (".pem", ".key", ".p12", ".pfx")


class GitHubMutationError(RuntimeError):
    pass


@dataclass(frozen=True, slots=True)
class GitHubMutationConfig:
    repository: str
    token_env: str
    api_base: str = "https://api.github.com"
    timeout_seconds: float = 60.0
    max_file_chars: int = 128_000
    max_commit_message_chars: int = 500
    max_pr_body_chars: int = 16_000

    def __post_init__(self) -> None:
        if not _REPOSITORY.fullmatch(self.repository):
            raise ValueError("repository must be in owner/name form")
        if not self.token_env.strip():
            raise ValueError("token_env must not be empty")
        if self.timeout_seconds <= 0:
            raise ValueError("timeout_seconds must be positive")
        if self.max_file_chars < 1024:
            raise ValueError("max_file_chars must be >= 1024")
        if self.max_commit_message_chars < 32:
            raise ValueError("max_commit_message_chars must be >= 32")
        if self.max_pr_body_chars < 256:
            raise ValueError("max_pr_body_chars must be >= 256")


@dataclass(slots=True)
class GitHubMutationClient:
    config: GitHubMutationConfig
    transport: JsonTransport = field(default_factory=UrllibJsonTransport)
    executor: GuardedActionExecutor = field(default_factory=GuardedActionExecutor)

    def create_branch(
        self,
        branch: str,
        base_sha: str,
        approval: ActionApproval | None = None,
    ) -> ActionResult:
        branch_name = self._safe_branch(branch)
        commit_sha = self._safe_sha(base_sha)
        action = ActionRequest(
            name="github.create_branch",
            target=branch_name,
            risk=RiskLevel.REVERSIBLE_WRITE,
            metadata={"branch": branch_name},
        )

        def operation() -> dict[str, Any]:
            data = self._request(
                "POST",
                "/git/refs",
                {"ref": f"refs/heads/{branch_name}", "sha": commit_sha},
                expected_statuses={201},
            )
            obj = data.get("object")
            return {
                "ref": data.get("ref"),
                "sha": obj.get("sha") if isinstance(obj, Mapping) else None,
            }

        return self.executor.execute(action, operation, approval)

    def write_file(
        self,
        *,
        path: str,
        content: str,
        commit_message: str,
        branch: str,
        sha: str | None = None,
        approval: ActionApproval | None = None,
    ) -> ActionResult:
        normalized_path = self._safe_path(path)
        branch_name = self._safe_branch(branch)
        message = self._safe_commit_message(commit_message)
        if not isinstance(content, str):
            raise TypeError("content must be a string")
        if len(content) > self.config.max_file_chars:
            raise ValueError("file content exceeds configured limit")
        current_sha = self._safe_sha(sha) if sha is not None else None
        target = f"{branch_name}:{normalized_path}"
        action = ActionRequest(
            name="github.write_file",
            target=target,
            risk=RiskLevel.REVERSIBLE_WRITE,
            metadata={"branch": branch_name},
        )

        def operation() -> dict[str, Any]:
            payload: dict[str, Any] = {
                "message": message,
                "content": base64.b64encode(content.encode("utf-8")).decode("ascii"),
                "branch": branch_name,
            }
            if current_sha is not None:
                payload["sha"] = current_sha
            data = self._request(
                "PUT",
                f"/contents/{quote(normalized_path, safe='/')}",
                payload,
                expected_statuses={200, 201},
            )
            commit = data.get("commit")
            remote_content = data.get("content")
            return {
                "path": normalized_path,
                "branch": branch_name,
                "commit_sha": commit.get("sha") if isinstance(commit, Mapping) else None,
                "content_sha": (
                    remote_content.get("sha") if isinstance(remote_content, Mapping) else None
                ),
            }

        return self.executor.execute(action, operation, approval)

    def delete_file(
        self,
        *,
        path: str,
        sha: str,
        commit_message: str,
        branch: str,
        approval: ActionApproval | None = None,
    ) -> ActionResult:
        normalized_path = self._safe_path(path)
        branch_name = self._safe_branch(branch)
        current_sha = self._safe_sha(sha)
        message = self._safe_commit_message(commit_message)
        target = f"{branch_name}:{normalized_path}"
        action = ActionRequest(
            name="github.delete_file",
            target=target,
            risk=RiskLevel.DESTRUCTIVE,
            metadata={"branch": branch_name},
        )

        def operation() -> dict[str, Any]:
            data = self._request(
                "DELETE",
                f"/contents/{quote(normalized_path, safe='/')}",
                {"message": message, "sha": current_sha, "branch": branch_name},
                expected_statuses={200},
            )
            commit = data.get("commit")
            return {
                "path": normalized_path,
                "branch": branch_name,
                "commit_sha": commit.get("sha") if isinstance(commit, Mapping) else None,
            }

        return self.executor.execute(action, operation, approval)

    def open_pull_request(
        self,
        *,
        title: str,
        head: str,
        base: str,
        body: str = "",
        approval: ActionApproval | None = None,
    ) -> ActionResult:
        head_branch = self._safe_branch(head)
        base_branch = self._safe_branch(base)
        if not isinstance(title, str):
            raise TypeError("pull request title must be a string")
        normalized_title = title.strip()
        if not normalized_title:
            raise ValueError("pull request title must not be empty")
        if len(normalized_title) > 256:
            raise ValueError("pull request title is too long")
        if not isinstance(body, str):
            raise TypeError("pull request body must be a string")
        if len(body) > self.config.max_pr_body_chars:
            raise ValueError("pull request body exceeds configured limit")
        target = f"{head_branch}->{base_branch}"
        action = ActionRequest(
            name="github.open_pull_request",
            target=target,
            risk=RiskLevel.EXTERNAL_SIDE_EFFECT,
            metadata={"branch": base_branch},
        )

        def operation() -> dict[str, Any]:
            data = self._request(
                "POST",
                "/pulls",
                {
                    "title": normalized_title,
                    "head": head_branch,
                    "base": base_branch,
                    "body": body,
                },
                expected_statuses={201},
            )
            return {
                "number": data.get("number"),
                "title": data.get("title"),
                "state": data.get("state"),
                "html_url": data.get("html_url"),
            }

        return self.executor.execute(action, operation, approval)

    def _request(
        self,
        method: str,
        route: str,
        payload: Mapping[str, Any],
        *,
        expected_statuses: set[int],
    ) -> dict[str, Any]:
        token = EnvCredential(self.config.token_env).resolve()
        response = self.transport.request(
            JsonRequest(
                method=method,
                url=(
                    f"{self.config.api_base.rstrip('/')}/repos/"
                    f"{self.config.repository}{route}"
                ),
                payload=payload,
                headers={
                    "Accept": "application/vnd.github+json",
                    "Authorization": f"Bearer {token}",
                    "X-GitHub-Api-Version": "2022-11-28",
                },
                timeout_seconds=self.config.timeout_seconds,
            )
        )
        if response.status_code not in expected_statuses:
            raise GitHubMutationError(
                f"GitHub returned unexpected status {response.status_code}"
            )
        return dict(response.payload)

    @staticmethod
    def _safe_sha(value: str) -> str:
        if not isinstance(value, str):
            raise TypeError("sha must be a string")
        if not _SHA.fullmatch(value):
            raise ValueError("sha must be a full hexadecimal Git commit/blob id")
        return value

    @staticmethod
    def _safe_branch(value: str) -> str:
        if not isinstance(value, str):
            raise TypeError("branch must be a string")
        lowered = value.lower()
        segments = value.split("/")
        if (
            not _BRANCH.fullmatch(value)
            or lowered == "head"
            or lowered.startswith("refs/")
            or lowered.startswith("heads/")
            or ".." in value
            or "//" in value
            or "@{" in value
            or value.endswith("/")
            or value.endswith(".")
            or any(segment.startswith(".") or segment.endswith(".lock") for segment in segments)
        ):
            raise ValueError("branch name is invalid")
        return value

    @staticmethod
    def _safe_path(path: str) -> str:
        if not isinstance(path, str):
            raise TypeError("path must be a string")
        normalized = path.strip("/")
        segments = normalized.split("/")
        if (
            not normalized
            or "\x00" in normalized
            or "\\" in normalized
            or len(normalized) > 1024
            or ".." in segments
            or "" in segments
        ):
            raise ValueError("GitHub file path is invalid")
        parts = tuple(part.lower() for part in segments)
        basename = parts[-1]
        if any(part in _SENSITIVE_DIRECTORIES for part in parts[:-1]):
            raise ValueError("GitHub file path is credential-sensitive")
        if (
            basename == ".env"
            or basename.startswith(".env.")
            or basename in _SENSITIVE_BASENAMES
            or basename.endswith(_SENSITIVE_SUFFIXES)
        ):
            raise ValueError("GitHub file path is credential-sensitive")
        return normalized

    def _safe_commit_message(self, value: str) -> str:
        if not isinstance(value, str):
            raise TypeError("commit_message must be a string")
        message = value.strip()
        if not message:
            raise ValueError("commit_message must not be empty")
        if len(message) > self.config.max_commit_message_chars:
            raise ValueError("commit_message exceeds configured limit")
        return message


class GitHubMutationToolset:
    """Model-callable mutation subset. Human-gated operations are intentionally excluded."""

    def __init__(self, client: GitHubMutationClient) -> None:
        self.client = client

    def register_into(self, registry: ToolRegistry) -> None:
        registry.register(
            "github.create_branch",
            self._create_branch,
            description="Create a new non-protected GitHub branch from an exact commit SHA.",
            parameters={
                "type": "object",
                "properties": {
                    "branch": {"type": "string"},
                    "base_sha": {"type": "string"},
                },
                "required": ["branch", "base_sha"],
                "additionalProperties": False,
            },
        )
        registry.register(
            "github.write_file",
            self._write_file,
            description="Create or update one non-sensitive file on a non-protected branch.",
            parameters={
                "type": "object",
                "properties": {
                    "path": {"type": "string"},
                    "content": {"type": "string"},
                    "commit_message": {"type": "string"},
                    "branch": {"type": "string"},
                    "sha": {"type": "string"},
                },
                "required": ["path", "content", "commit_message", "branch"],
                "additionalProperties": False,
            },
        )

    def _create_branch(self, arguments: Mapping[str, Any]) -> Mapping[str, Any]:
        self._require_keys(arguments, {"branch", "base_sha"})
        branch = arguments.get("branch")
        base_sha = arguments.get("base_sha")
        if not isinstance(branch, str):
            raise TypeError("branch must be a string")
        if not isinstance(base_sha, str):
            raise TypeError("base_sha must be a string")
        return self._result_payload(self.client.create_branch(branch, base_sha))

    def _write_file(self, arguments: Mapping[str, Any]) -> Mapping[str, Any]:
        self._require_keys(arguments, {"path", "content", "commit_message", "branch", "sha"})
        path = arguments.get("path")
        content = arguments.get("content")
        commit_message = arguments.get("commit_message")
        branch = arguments.get("branch")
        sha = arguments.get("sha")
        if not isinstance(path, str):
            raise TypeError("path must be a string")
        if not isinstance(content, str):
            raise TypeError("content must be a string")
        if not isinstance(commit_message, str):
            raise TypeError("commit_message must be a string")
        if not isinstance(branch, str):
            raise TypeError("branch must be a string")
        if sha is not None and not isinstance(sha, str):
            raise TypeError("sha must be a string when provided")
        return self._result_payload(
            self.client.write_file(
                path=path,
                content=content,
                commit_message=commit_message,
                branch=branch,
                sha=sha,
            )
        )

    @staticmethod
    def _result_payload(result: ActionResult) -> Mapping[str, Any]:
        return {
            "decision": result.decision.value,
            "executed": result.executed,
            "value": result.value,
        }

    @staticmethod
    def _require_keys(arguments: Mapping[str, Any], allowed: set[str]) -> None:
        extras = set(arguments) - allowed
        if extras:
            raise ValueError("tool arguments contain unsupported fields")
