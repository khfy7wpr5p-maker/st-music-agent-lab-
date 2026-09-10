from __future__ import annotations

import base64
import binascii
import re
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any
from urllib.parse import quote, urlencode

from .agent_tools import ToolRegistry
from .credentials import EnvCredential
from .transport import JsonRequest, JsonTransport, UrllibJsonTransport

_REPOSITORY = re.compile(r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$")
_SHA = re.compile(r"^[0-9a-fA-F]{7,64}$")
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


class GitHubReadError(RuntimeError):
    pass


@dataclass(frozen=True, slots=True)
class GitHubReadConfig:
    repository: str
    token_env: str | None = None
    api_base: str = "https://api.github.com"
    timeout_seconds: float = 60.0
    max_file_chars: int = 64_000

    def __post_init__(self) -> None:
        if not _REPOSITORY.fullmatch(self.repository):
            raise ValueError("repository must be in owner/name form")
        if self.timeout_seconds <= 0:
            raise ValueError("timeout_seconds must be positive")
        if self.max_file_chars < 1024:
            raise ValueError("max_file_chars must be >= 1024")


class GitHubReadClient:
    """Narrow read-only GitHub REST client for agent tools."""

    def __init__(
        self,
        config: GitHubReadConfig,
        transport: JsonTransport | None = None,
    ) -> None:
        self.config = config
        self.transport = transport or UrllibJsonTransport()

    def repository_metadata(self) -> dict[str, Any]:
        data = self._get("")
        return {
            "full_name": data.get("full_name"),
            "default_branch": data.get("default_branch"),
            "visibility": data.get("visibility"),
            "archived": data.get("archived"),
            "language": data.get("language"),
        }

    def read_file(self, path: str, ref: str | None = None) -> dict[str, Any]:
        normalized = self._safe_path(path)
        query = {"ref": ref} if ref else None
        data = self._get(f"/contents/{quote(normalized, safe='/')}", query)
        if data.get("type") != "file" or data.get("encoding") != "base64":
            raise GitHubReadError("GitHub content response is not a base64 file")
        encoded = data.get("content")
        if not isinstance(encoded, str):
            raise GitHubReadError("GitHub content response is missing file content")
        try:
            compact = "".join(encoded.split())
            decoded = base64.b64decode(compact, validate=True).decode("utf-8")
        except (binascii.Error, ValueError, UnicodeDecodeError) as exc:
            raise GitHubReadError("GitHub file is not valid base64 UTF-8 text") from exc
        limit = self.config.max_file_chars
        truncated = len(decoded) > limit
        return {
            "path": normalized,
            "ref": ref,
            "content": decoded[:limit],
            "truncated": truncated,
            "sha": data.get("sha"),
        }

    def branch_info(self, branch: str) -> dict[str, Any]:
        name = self._safe_name(branch, "branch")
        data = self._get(f"/branches/{quote(name, safe='')}")
        commit = data.get("commit")
        commit_sha = commit.get("sha") if isinstance(commit, Mapping) else None
        return {
            "name": data.get("name"),
            "protected": data.get("protected"),
            "commit_sha": commit_sha,
        }

    def pull_request(self, number: int) -> dict[str, Any]:
        if number < 1:
            raise ValueError("pull request number must be >= 1")
        data = self._get(f"/pulls/{number}")
        head = data.get("head")
        base = data.get("base")
        return {
            "number": data.get("number"),
            "title": data.get("title"),
            "state": data.get("state"),
            "draft": data.get("draft"),
            "mergeable": data.get("mergeable"),
            "head_ref": head.get("ref") if isinstance(head, Mapping) else None,
            "head_sha": head.get("sha") if isinstance(head, Mapping) else None,
            "base_ref": base.get("ref") if isinstance(base, Mapping) else None,
            "base_sha": base.get("sha") if isinstance(base, Mapping) else None,
        }

    def workflow_runs(self, head_sha: str | None = None) -> dict[str, Any]:
        query: dict[str, str | int] = {"per_page": 10}
        if head_sha:
            if not _SHA.fullmatch(head_sha):
                raise ValueError("head_sha must be a hexadecimal Git commit id")
            query["head_sha"] = head_sha
        data = self._get("/actions/runs", query)
        runs = data.get("workflow_runs")
        if not isinstance(runs, list):
            raise GitHubReadError("GitHub workflow response is missing workflow_runs")
        selected = []
        for run in runs[:10]:
            if isinstance(run, Mapping):
                selected.append(
                    {
                        "id": run.get("id"),
                        "name": run.get("name"),
                        "event": run.get("event"),
                        "status": run.get("status"),
                        "conclusion": run.get("conclusion"),
                        "head_sha": run.get("head_sha"),
                        "html_url": run.get("html_url"),
                    }
                )
        return {"workflow_runs": selected}

    def _get(
        self,
        route: str,
        query: Mapping[str, str | int] | None = None,
    ) -> dict[str, Any]:
        suffix = f"?{urlencode(query)}" if query else ""
        url = (
            f"{self.config.api_base.rstrip('/')}/repos/"
            f"{self.config.repository}{route}{suffix}"
        )
        response = self.transport.request(
            JsonRequest(
                method="GET",
                url=url,
                headers=self._headers(),
                timeout_seconds=self.config.timeout_seconds,
            )
        )
        if response.status_code != 200:
            raise GitHubReadError(f"GitHub returned unexpected status {response.status_code}")
        return dict(response.payload)

    def _headers(self) -> dict[str, str]:
        headers = {
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
        }
        if self.config.token_env:
            token = EnvCredential(self.config.token_env).resolve()
            headers["Authorization"] = f"Bearer {token}"
        return headers

    @staticmethod
    def _safe_path(path: str) -> str:
        normalized = path.strip("/")
        if not normalized or "\x00" in normalized or ".." in normalized.split("/"):
            raise ValueError("GitHub file path is invalid")
        parts = tuple(part.lower() for part in normalized.split("/"))
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

    @staticmethod
    def _safe_name(value: str, label: str) -> str:
        if not value.strip() or "\x00" in value or len(value) > 255:
            raise ValueError(f"{label} name is invalid")
        return value


class GitHubReadToolset:
    def __init__(self, client: GitHubReadClient) -> None:
        self.client = client

    def register_into(self, registry: ToolRegistry) -> None:
        registry.register(
            "github.repo_metadata",
            self._repo_metadata,
            description="Read basic metadata for the configured GitHub repository.",
        )
        registry.register(
            "github.read_file",
            self._read_file,
            description="Read one non-sensitive UTF-8 text file from the configured repository.",
            parameters={
                "type": "object",
                "properties": {
                    "path": {"type": "string"},
                    "ref": {"type": "string"},
                },
                "required": ["path"],
                "additionalProperties": False,
            },
        )
        registry.register(
            "github.branch_info",
            self._branch_info,
            description="Read branch name, protection flag and commit SHA.",
            parameters={
                "type": "object",
                "properties": {"branch": {"type": "string"}},
                "required": ["branch"],
                "additionalProperties": False,
            },
        )
        registry.register(
            "github.pull_request",
            self._pull_request,
            description="Read metadata for one pull request by number.",
            parameters={
                "type": "object",
                "properties": {"number": {"type": "integer", "minimum": 1}},
                "required": ["number"],
                "additionalProperties": False,
            },
        )
        registry.register(
            "github.workflow_runs",
            self._workflow_runs,
            description="Read up to ten recent workflow runs, optionally for one commit SHA.",
            parameters={
                "type": "object",
                "properties": {"head_sha": {"type": "string"}},
                "additionalProperties": False,
            },
        )

    def _repo_metadata(self, arguments: Mapping[str, Any]) -> Mapping[str, Any]:
        self._require_keys(arguments, set())
        return self.client.repository_metadata()

    def _read_file(self, arguments: Mapping[str, Any]) -> Mapping[str, Any]:
        self._require_keys(arguments, {"path", "ref"})
        path = arguments.get("path")
        ref = arguments.get("ref")
        if not isinstance(path, str):
            raise ValueError("path must be a string")
        if ref is not None and not isinstance(ref, str):
            raise ValueError("ref must be a string when provided")
        return self.client.read_file(path, ref)

    def _branch_info(self, arguments: Mapping[str, Any]) -> Mapping[str, Any]:
        self._require_keys(arguments, {"branch"})
        branch = arguments.get("branch")
        if not isinstance(branch, str):
            raise ValueError("branch must be a string")
        return self.client.branch_info(branch)

    def _pull_request(self, arguments: Mapping[str, Any]) -> Mapping[str, Any]:
        self._require_keys(arguments, {"number"})
        number = arguments.get("number")
        if not isinstance(number, int) or isinstance(number, bool):
            raise ValueError("number must be an integer")
        return self.client.pull_request(number)

    def _workflow_runs(self, arguments: Mapping[str, Any]) -> Mapping[str, Any]:
        self._require_keys(arguments, {"head_sha"})
        head_sha = arguments.get("head_sha")
        if head_sha is not None and not isinstance(head_sha, str):
            raise ValueError("head_sha must be a string when provided")
        return self.client.workflow_runs(head_sha)

    @staticmethod
    def _require_keys(arguments: Mapping[str, Any], allowed: set[str]) -> None:
        extras = set(arguments) - allowed
        if extras:
            raise ValueError("tool arguments contain unsupported fields")
