from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import Any, Protocol
from urllib.parse import urlsplit

from .agent_tools import ToolRegistry
from .catalog import DEFAULT_MODELS
from .contracts import ActionRequest, ModelProfile, RiskLevel
from .github_read import GitHubReadClient, GitHubReadConfig, GitHubReadError
from .github_write import GitHubMutationClient, GitHubMutationConfig
from .operator_console import PROJECTS, ProjectDescriptor
from .policy import AutonomyDecision, AutonomyPolicy
from .providers import OpenAICompatibleClient, OpenAICompatibleConfig
from .tool_loop import ToolCallingClient, ToolLoopBudget, ToolLoopRunner
from .tools import ActionApproval, ActionResult

APP_TASK_SCHEMA_VERSION = "1.0.0"
_TASK_ID = re.compile(r"^task:[0-9a-f]{64}$")
_SHA = re.compile(r"^[0-9a-f]{40}$")
_BRANCH_SEGMENT = re.compile(r"[^A-Za-z0-9._-]+")
_MAX_TREE_ENTRIES = 2000
_MAX_INSTRUCTION_CHARS = 8000


class TaskExecutionError(RuntimeError):
    pass


class TaskReadClient(Protocol):
    def repository_metadata(self) -> dict[str, Any]: ...

    def repository_tree(self, ref: str = "main") -> dict[str, Any]: ...

    def read_file(self, path: str, ref: str | None = None) -> dict[str, Any]: ...

    def branch_info(self, branch: str) -> dict[str, Any]: ...

    def workflow_runs(self, head_sha: str | None = None) -> dict[str, Any]: ...


class TaskMutationClient(Protocol):
    def create_branch(
        self,
        branch: str,
        base_sha: str,
        approval: ActionApproval | None = None,
    ) -> ActionResult: ...

    def write_file(
        self,
        *,
        path: str,
        content: str,
        commit_message: str,
        branch: str,
        sha: str | None = None,
        approval: ActionApproval | None = None,
    ) -> ActionResult: ...

    def open_pull_request(
        self,
        *,
        title: str,
        head: str,
        base: str,
        body: str = "",
        approval: ActionApproval | None = None,
    ) -> ActionResult: ...


@dataclass(frozen=True, slots=True)
class TaskExecutionConfig:
    enabled: bool = False
    profile_name: str = "GLM-5.1"
    provider_base_url: str | None = None
    provider_model: str | None = None
    provider_api_key_env: str | None = None
    github_token_env: str = "GITHUB_TOKEN"
    github_api_base: str = "https://api.github.com"
    base_branch: str = "main"

    def __post_init__(self) -> None:
        if not self.github_token_env.strip():
            raise ValueError("github_token_env must not be empty")
        if self.base_branch not in {"main", "master"}:
            raise ValueError("APP2 base_branch must be a protected main/master branch")
        if self.enabled:
            for label, value in (
                ("provider_base_url", self.provider_base_url),
                ("provider_model", self.provider_model),
                ("provider_api_key_env", self.provider_api_key_env),
            ):
                if not isinstance(value, str) or not value.strip():
                    raise ValueError(f"{label} is required when task execution is enabled")
            assert self.provider_base_url is not None
            parsed = urlsplit(self.provider_base_url)
            if parsed.scheme not in {"http", "https"} or not parsed.netloc:
                raise ValueError("provider_base_url must be an absolute HTTP/HTTPS URL")


@dataclass(frozen=True, slots=True)
class TaskPreview:
    task_id: str
    project: str
    repository: str
    instruction: str
    base_branch: str
    base_sha: str
    feature_branch: str
    create_branch_decision: AutonomyDecision
    write_file_decision: AutonomyDecision
    pull_request_decision: AutonomyDecision
    execution_enabled: bool
    production_actions_authorized: bool = False

    def as_dict(self) -> dict[str, Any]:
        return {
            "schema_version": APP_TASK_SCHEMA_VERSION,
            "task_id": self.task_id,
            "project": self.project,
            "repository": self.repository,
            "instruction": self.instruction,
            "base_branch": self.base_branch,
            "base_sha": self.base_sha,
            "feature_branch": self.feature_branch,
            "policy": {
                "create_branch": self.create_branch_decision.value,
                "write_file": self.write_file_decision.value,
                "open_pull_request": self.pull_request_decision.value,
            },
            "execution_enabled": self.execution_enabled,
            "production_actions_authorized": self.production_actions_authorized,
        }


@dataclass(frozen=True, slots=True)
class TaskRunRecord:
    task_id: str
    repository: str
    feature_branch: str
    base_sha: str
    head_sha: str
    model_name: str
    final_message: Mapping[str, Any]
    turns: int
    tool_calls: int
    workflow_runs: tuple[Mapping[str, Any], ...]

    def as_dict(self) -> dict[str, Any]:
        return {
            "schema_version": APP_TASK_SCHEMA_VERSION,
            "task_id": self.task_id,
            "repository": self.repository,
            "feature_branch": self.feature_branch,
            "base_sha": self.base_sha,
            "head_sha": self.head_sha,
            "model_name": self.model_name,
            "final_message": dict(self.final_message),
            "turns": self.turns,
            "tool_calls": self.tool_calls,
            "workflow_runs": [dict(item) for item in self.workflow_runs],
            "merge_authorized": False,
            "production_actions_authorized": False,
        }


class TaskGitHubReadClient(GitHubReadClient):
    """GitHub read client with one bounded non-sensitive repository-tree projection."""

    def repository_tree(self, ref: str = "main") -> dict[str, Any]:
        branch = self.branch_info(ref)
        commit_sha = branch.get("commit_sha")
        if not isinstance(commit_sha, str) or not _SHA.fullmatch(commit_sha):
            raise GitHubReadError("branch does not expose a full commit SHA")
        data = self._get(f"/git/trees/{commit_sha}", {"recursive": "1"})
        if data.get("truncated") is True:
            raise GitHubReadError("GitHub repository tree is truncated")
        remote_tree = data.get("tree")
        if not isinstance(remote_tree, list):
            raise GitHubReadError("GitHub repository tree response is invalid")
        files: list[dict[str, Any]] = []
        for item in remote_tree:
            if not isinstance(item, Mapping) or item.get("type") != "blob":
                continue
            path = item.get("path")
            sha = item.get("sha")
            if not isinstance(path, str) or not isinstance(sha, str):
                continue
            try:
                safe_path = self._safe_path(path)
            except ValueError:
                continue
            files.append(
                {
                    "path": safe_path,
                    "sha": sha,
                    "size": item.get("size") if isinstance(item.get("size"), int) else None,
                }
            )
        files.sort(key=lambda item: item["path"])
        if len(files) > _MAX_TREE_ENTRIES:
            raise GitHubReadError("repository tree exceeds configured entry limit")
        return {"ref": ref, "commit_sha": commit_sha, "files": files}


class TaskRepositoryReadToolset:
    def __init__(self, client: TaskReadClient) -> None:
        self.client = client

    def register_into(self, registry: ToolRegistry) -> None:
        registry.register(
            "github.repo_metadata",
            self._repo_metadata,
            description="Read basic metadata for the task repository.",
        )
        registry.register(
            "github.tree",
            self._tree,
            description=(
                "List the bounded non-sensitive UTF-8 repository file paths for one branch."
            ),
            parameters={
                "type": "object",
                "properties": {"ref": {"type": "string"}},
                "additionalProperties": False,
            },
        )
        registry.register(
            "github.read_file",
            self._read_file,
            description="Read one non-sensitive UTF-8 file from the task repository.",
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
            description="Read one branch's protection flag and exact commit SHA.",
            parameters={
                "type": "object",
                "properties": {"branch": {"type": "string"}},
                "required": ["branch"],
                "additionalProperties": False,
            },
        )
        registry.register(
            "github.workflow_runs",
            self._workflow_runs,
            description="Read recent workflow runs for an exact task commit SHA.",
            parameters={
                "type": "object",
                "properties": {"head_sha": {"type": "string"}},
                "additionalProperties": False,
            },
        )

    def _repo_metadata(self, arguments: Mapping[str, Any]) -> Mapping[str, Any]:
        self._require_keys(arguments, set())
        return self.client.repository_metadata()

    def _tree(self, arguments: Mapping[str, Any]) -> Mapping[str, Any]:
        self._require_keys(arguments, {"ref"})
        ref = arguments.get("ref", "main")
        if not isinstance(ref, str) or not ref.strip():
            raise TypeError("ref must be non-empty text")
        return self.client.repository_tree(ref)

    def _read_file(self, arguments: Mapping[str, Any]) -> Mapping[str, Any]:
        self._require_keys(arguments, {"path", "ref"})
        path = arguments.get("path")
        ref = arguments.get("ref")
        if not isinstance(path, str):
            raise TypeError("path must be a string")
        if ref is not None and not isinstance(ref, str):
            raise TypeError("ref must be a string when provided")
        return self.client.read_file(path, ref)

    def _branch_info(self, arguments: Mapping[str, Any]) -> Mapping[str, Any]:
        self._require_keys(arguments, {"branch"})
        branch = arguments.get("branch")
        if not isinstance(branch, str):
            raise TypeError("branch must be a string")
        return self.client.branch_info(branch)

    def _workflow_runs(self, arguments: Mapping[str, Any]) -> Mapping[str, Any]:
        self._require_keys(arguments, {"head_sha"})
        head_sha = arguments.get("head_sha")
        if head_sha is not None and not isinstance(head_sha, str):
            raise TypeError("head_sha must be a string when provided")
        return self.client.workflow_runs(head_sha)

    @staticmethod
    def _require_keys(arguments: Mapping[str, Any], allowed: set[str]) -> None:
        extras = set(arguments) - allowed
        if extras:
            raise ValueError("tool arguments contain unsupported fields")


class BoundTaskWriteToolset:
    """Model-facing write tool that injects one immutable feature branch host-side."""

    def __init__(self, client: TaskMutationClient, feature_branch: str) -> None:
        self.client = client
        self.feature_branch = feature_branch

    def register_into(self, registry: ToolRegistry) -> None:
        registry.register(
            "task.write_file",
            self._write_file,
            description=(
                "Create or update one non-sensitive file on this task's already-bound feature branch."
            ),
            parameters={
                "type": "object",
                "properties": {
                    "path": {"type": "string"},
                    "content": {"type": "string"},
                    "commit_message": {"type": "string"},
                    "sha": {"type": "string"},
                },
                "required": ["path", "content", "commit_message"],
                "additionalProperties": False,
            },
        )

    def _write_file(self, arguments: Mapping[str, Any]) -> Mapping[str, Any]:
        extras = set(arguments) - {"path", "content", "commit_message", "sha"}
        if extras:
            raise ValueError("tool arguments contain unsupported fields")
        path = arguments.get("path")
        content = arguments.get("content")
        commit_message = arguments.get("commit_message")
        sha = arguments.get("sha")
        if not isinstance(path, str) or not isinstance(content, str):
            raise TypeError("path and content must be strings")
        if not isinstance(commit_message, str):
            raise TypeError("commit_message must be a string")
        if sha is not None and not isinstance(sha, str):
            raise TypeError("sha must be a string when provided")
        result = self.client.write_file(
            path=path,
            content=content,
            commit_message=commit_message,
            branch=self.feature_branch,
            sha=sha,
        )
        return _action_payload(result)


ReadFactory = Callable[[str], TaskReadClient]
MutationFactory = Callable[[str], TaskMutationClient]


class GuardedTaskService:
    """Host-side APP2 task service; feature-branch writes only, no merge/deploy authority."""

    def __init__(
        self,
        config: TaskExecutionConfig,
        *,
        policy: AutonomyPolicy | None = None,
        read_factory: ReadFactory | None = None,
        mutation_factory: MutationFactory | None = None,
        provider_client: ToolCallingClient | None = None,
    ) -> None:
        self.config = config
        self.policy = policy or AutonomyPolicy()
        self._read_factory = read_factory or self._default_read_factory
        self._mutation_factory = mutation_factory or self._default_mutation_factory
        self._provider_client = provider_client
        self._previews: dict[str, TaskPreview] = {}
        self._runs: dict[str, TaskRunRecord] = {}
        self._pull_requests: dict[str, Mapping[str, Any]] = {}

    def preview(self, project: str, instruction: str) -> TaskPreview:
        descriptor = _descriptor(project)
        normalized_instruction = _instruction(instruction)
        read_client = self._read_factory(descriptor.repository)
        base = read_client.branch_info(self.config.base_branch)
        base_sha = base.get("commit_sha")
        if not isinstance(base_sha, str) or not _SHA.fullmatch(base_sha):
            raise TaskExecutionError("base branch does not expose a full commit SHA")

        identity = {
            "schema_version": APP_TASK_SCHEMA_VERSION,
            "project": descriptor.project.value,
            "repository": descriptor.repository,
            "instruction": normalized_instruction,
            "base_branch": self.config.base_branch,
            "base_sha": base_sha,
        }
        digest = _canonical_hash(identity)
        task_id = f"task:{digest}"
        branch_project = _BRANCH_SEGMENT.sub("-", descriptor.project.value).strip("-")
        feature_branch = f"st-agent/{branch_project}/{digest[:12]}"

        create_action = ActionRequest(
            name="github.create_branch",
            target=feature_branch,
            risk=RiskLevel.REVERSIBLE_WRITE,
            metadata={"branch": feature_branch},
        )
        write_action = ActionRequest(
            name="github.write_file",
            target=f"{feature_branch}:<bounded-file>",
            risk=RiskLevel.REVERSIBLE_WRITE,
            metadata={"branch": feature_branch},
        )
        pr_action = ActionRequest(
            name="github.open_pull_request",
            target=f"{feature_branch}->{self.config.base_branch}",
            risk=RiskLevel.EXTERNAL_SIDE_EFFECT,
            metadata={"branch": self.config.base_branch},
        )
        preview = TaskPreview(
            task_id=task_id,
            project=descriptor.project.value,
            repository=descriptor.repository,
            instruction=normalized_instruction,
            base_branch=self.config.base_branch,
            base_sha=base_sha,
            feature_branch=feature_branch,
            create_branch_decision=self.policy.decide(create_action),
            write_file_decision=self.policy.decide(write_action),
            pull_request_decision=self.policy.decide(pr_action),
            execution_enabled=self.config.enabled,
            production_actions_authorized=False,
        )
        if preview.create_branch_decision is not AutonomyDecision.AUTO_EXECUTE:
            raise TaskExecutionError("policy does not allow autonomous feature-branch creation")
        if preview.write_file_decision is not AutonomyDecision.AUTO_EXECUTE:
            raise TaskExecutionError("policy does not allow autonomous feature-branch writes")
        if preview.pull_request_decision is not AutonomyDecision.REQUIRE_HUMAN:
            raise TaskExecutionError("policy must keep pull requests human-gated")
        self._previews[task_id] = preview
        return preview

    def run(self, task_id: str) -> TaskRunRecord:
        preview = self._preview(task_id)
        if not self.config.enabled:
            raise TaskExecutionError("task execution is disabled; start the app with --enable-writes")
        existing = self._runs.get(task_id)
        if existing is not None:
            return existing

        mutation = self._mutation_factory(preview.repository)
        branch_result = mutation.create_branch(preview.feature_branch, preview.base_sha)
        _require_action(
            branch_result,
            AutonomyDecision.AUTO_EXECUTE,
            "feature branch creation did not execute",
        )

        read_client = self._read_factory(preview.repository)
        registry = ToolRegistry()
        TaskRepositoryReadToolset(read_client).register_into(registry)
        BoundTaskWriteToolset(mutation, preview.feature_branch).register_into(registry)
        provider = self._provider_client or self._build_provider()
        runner = ToolLoopRunner(
            provider,
            registry,
            budget=ToolLoopBudget(
                max_turns=8,
                max_tool_calls=12,
                max_argument_chars=32_768,
                max_elapsed_seconds=600.0,
                max_model_facing_bytes=2_000_000,
            ),
        )
        result = runner.run(self._agent_instruction(preview))

        branch = read_client.branch_info(preview.feature_branch)
        head_sha = branch.get("commit_sha")
        if not isinstance(head_sha, str) or not _SHA.fullmatch(head_sha):
            raise TaskExecutionError("feature branch does not expose a full commit SHA after run")
        if head_sha == preview.base_sha:
            raise TaskExecutionError("agent completed without producing a feature-branch commit")
        workflow_payload = read_client.workflow_runs(head_sha)
        raw_runs = workflow_payload.get("workflow_runs", [])
        if not isinstance(raw_runs, list):
            raise TaskExecutionError("workflow run evidence is invalid")
        record = TaskRunRecord(
            task_id=task_id,
            repository=preview.repository,
            feature_branch=preview.feature_branch,
            base_sha=preview.base_sha,
            head_sha=head_sha,
            model_name=self._profile().name,
            final_message=result.final_message,
            turns=result.turns,
            tool_calls=result.tool_calls,
            workflow_runs=tuple(dict(item) for item in raw_runs if isinstance(item, Mapping)),
        )
        self._runs[task_id] = record
        return record

    def open_pull_request(self, task_id: str) -> Mapping[str, Any]:
        preview = self._preview(task_id)
        if not self.config.enabled:
            raise TaskExecutionError("task execution is disabled")
        run = self._runs.get(task_id)
        if run is None:
            raise TaskExecutionError("task must run successfully before opening a pull request")
        existing = self._pull_requests.get(task_id)
        if existing is not None:
            return existing

        target = f"{preview.feature_branch}->{preview.base_branch}"
        approval = ActionApproval(action_name="github.open_pull_request", target=target)
        mutation = self._mutation_factory(preview.repository)
        title = f"ST Agent: {preview.instruction[:180]}"
        body = (
            "Created from an explicitly reviewed ST Music Agent APP2 task.\n\n"
            f"Task: `{preview.task_id}`\n"
            f"Base SHA: `{preview.base_sha}`\n"
            f"Head SHA: `{run.head_sha}`\n\n"
            "Merge remains a separate human/host action."
        )
        result = mutation.open_pull_request(
            title=title,
            head=preview.feature_branch,
            base=preview.base_branch,
            body=body,
            approval=approval,
        )
        _require_action(result, AutonomyDecision.REQUIRE_HUMAN, "pull request did not execute")
        value = result.value
        if not isinstance(value, Mapping):
            raise TaskExecutionError("pull request result is invalid")
        projected = dict(value)
        self._pull_requests[task_id] = projected
        return projected

    def status(self, task_id: str) -> dict[str, Any]:
        preview = self._preview(task_id)
        run = self._runs.get(task_id)
        pull_request = self._pull_requests.get(task_id)
        return {
            "schema_version": APP_TASK_SCHEMA_VERSION,
            "preview": preview.as_dict(),
            "run": run.as_dict() if run is not None else None,
            "pull_request": dict(pull_request) if pull_request is not None else None,
            "merge_authorized": False,
            "production_actions_authorized": False,
        }

    def _preview(self, task_id: str) -> TaskPreview:
        if not isinstance(task_id, str) or not _TASK_ID.fullmatch(task_id):
            raise TaskExecutionError("task_id is invalid")
        preview = self._previews.get(task_id)
        if preview is None:
            raise TaskExecutionError("task preview does not exist in this app session")
        return preview

    def _profile(self) -> ModelProfile:
        for profile in DEFAULT_MODELS:
            if profile.name == self.config.profile_name:
                return profile
        raise TaskExecutionError(f"unknown model profile: {self.config.profile_name}")

    def _build_provider(self) -> ToolCallingClient:
        if not self.config.enabled:
            raise TaskExecutionError("provider is unavailable while task execution is disabled")
        assert self.config.provider_base_url is not None
        assert self.config.provider_model is not None
        assert self.config.provider_api_key_env is not None
        return OpenAICompatibleClient(
            self._profile(),
            OpenAICompatibleConfig(
                base_url=self.config.provider_base_url,
                model=self.config.provider_model,
                api_key_env=self.config.provider_api_key_env,
            ),
        )

    def _default_read_factory(self, repository: str) -> TaskReadClient:
        return TaskGitHubReadClient(
            GitHubReadConfig(
                repository=repository,
                token_env=self.config.github_token_env,
                api_base=self.config.github_api_base,
            )
        )

    def _default_mutation_factory(self, repository: str) -> TaskMutationClient:
        return GitHubMutationClient(
            GitHubMutationConfig(
                repository=repository,
                token_env=self.config.github_token_env,
                api_base=self.config.github_api_base,
            )
        )

    @staticmethod
    def _agent_instruction(preview: TaskPreview) -> str:
        return (
            "You are executing one bounded ST Music Agent engineering task. "
            f"Repository: {preview.repository}. "
            f"Base branch: {preview.base_branch} at {preview.base_sha}. "
            f"Your only writable branch is {preview.feature_branch}. "
            "Inspect the repository with github.tree and github.read_file before editing. "
            "Use task.write_file only for the smallest files required by the user's instruction. "
            "Never request or write credentials, secrets, deployment settings, protected branches, "
            "pull requests, merges, releases, training, activation, canonicalization, or rollback. "
            "Do not claim tests or CI passed unless tool evidence actually establishes it. "
            "When the requested bounded change is complete, summarize exactly what changed.\n\n"
            f"User task: {preview.instruction}"
        )


def _descriptor(project: str) -> ProjectDescriptor:
    for descriptor in PROJECTS:
        if descriptor.project.value == project:
            return descriptor
    raise TaskExecutionError(f"unknown project: {project}")


def _instruction(value: str) -> str:
    if not isinstance(value, str):
        raise TypeError("instruction must be text")
    normalized = " ".join(value.split())
    if not normalized:
        raise TaskExecutionError("instruction must not be empty")
    if len(normalized) > _MAX_INSTRUCTION_CHARS:
        raise TaskExecutionError("instruction exceeds configured limit")
    return normalized


def _canonical_hash(value: Any) -> str:
    encoded = json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _action_payload(result: ActionResult) -> Mapping[str, Any]:
    return {
        "decision": result.decision.value,
        "executed": result.executed,
        "value": result.value,
    }


def _require_action(
    result: ActionResult,
    expected: AutonomyDecision,
    message: str,
) -> None:
    if result.decision is not expected or not result.executed:
        raise TaskExecutionError(message)
