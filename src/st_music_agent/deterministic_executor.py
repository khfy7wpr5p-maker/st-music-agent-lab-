from __future__ import annotations

import json
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any, Protocol

from .task_execution import TaskMutationClient, TaskReadClient
from .tool_loop import ToolCallingClient

_SHA = re.compile(r"^[0-9a-f]{40}$")
_REPOSITORY = re.compile(r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$")
_PROTECTED_BRANCHES = frozenset({"main", "master"})
_SENSITIVE_BASENAMES = frozenset(
    {
        ".env",
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
_SENSITIVE_DIRECTORIES = frozenset({".git", ".ssh", ".aws", ".azure", ".gcp"})
_SENSITIVE_SUFFIXES = (".pem", ".key", ".p12", ".pfx")
_CONTROL_PATH_PREFIXES = (".github/workflows/", ".github/actions/")
_MAX_TREE_PATHS_FOR_SELECTION = 600
_MAX_SELECTION_PATHS = 3


class PlanValidationError(ValueError):
    pass


class DeterministicExecutionError(RuntimeError):
    pass


@dataclass(frozen=True, slots=True)
class PlannedFileChange:
    path: str
    operation: str
    expected_blob_sha: str | None
    content: str
    commit_message: str

    def as_dict(self) -> dict[str, Any]:
        return {
            "path": self.path,
            "operation": self.operation,
            "expected_blob_sha": self.expected_blob_sha,
            "content": self.content,
            "commit_message": self.commit_message,
        }


@dataclass(frozen=True, slots=True)
class DeterministicExecutionPlan:
    repository: str
    base_sha: str
    feature_branch: str
    changes: tuple[PlannedFileChange, ...]
    validation_targets: tuple[str, ...]
    summary: str

    def as_dict(self) -> dict[str, Any]:
        return {
            "repository": self.repository,
            "base_sha": self.base_sha,
            "feature_branch": self.feature_branch,
            "changes": [change.as_dict() for change in self.changes],
            "validation_targets": list(self.validation_targets),
            "summary": self.summary,
        }


@dataclass(frozen=True, slots=True)
class DeterministicExecutionResult:
    applied: bool
    head_sha: str
    changed_files: tuple[str, ...]
    checkpoints: tuple[Mapping[str, Any], ...]
    failure_reason: str | None

    def as_dict(self) -> dict[str, Any]:
        return {
            "applied": self.applied,
            "head_sha": self.head_sha,
            "changed_files": list(self.changed_files),
            "checkpoints": [dict(item) for item in self.checkpoints],
            "failure_reason": self.failure_reason,
        }


@dataclass(frozen=True, slots=True)
class PlannerSelection:
    read_paths: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class PlannerResult:
    plan: DeterministicExecutionPlan
    selected_paths: tuple[str, ...]
    model_calls: int
    final_message: Mapping[str, Any]


class _PlannerProvider(Protocol):
    def complete_with_tools(
        self,
        messages: Sequence[Mapping[str, Any]],
        tools: Sequence[Mapping[str, Any]],
    ) -> Mapping[str, Any]: ...


class SmallModelPlanner:
    """Two bounded model calls: select read evidence, then emit one strict mutation plan."""

    def __init__(
        self,
        provider: ToolCallingClient | _PlannerProvider,
        *,
        max_changed_files: int = 3,
        max_content_chars_per_file: int = 50_000,
        max_selected_files: int = _MAX_SELECTION_PATHS,
    ) -> None:
        if max_changed_files < 1:
            raise ValueError("max_changed_files must be >= 1")
        if max_content_chars_per_file < 1:
            raise ValueError("max_content_chars_per_file must be >= 1")
        if not 1 <= max_selected_files <= 8:
            raise ValueError("max_selected_files must be between 1 and 8")
        self.provider = provider
        self.max_changed_files = max_changed_files
        self.max_content_chars_per_file = max_content_chars_per_file
        self.max_selected_files = max_selected_files

    def build_plan(
        self,
        *,
        repository: str,
        base_sha: str,
        feature_branch: str,
        instruction: str,
        read_client: TaskReadClient,
    ) -> PlannerResult:
        tree = read_client.repository_tree(feature_branch)
        tree_sha = tree.get("commit_sha")
        if tree_sha != base_sha:
            raise PlanValidationError("planner inspection requires feature branch at exact base SHA")
        raw_files = tree.get("files")
        if not isinstance(raw_files, list):
            raise PlanValidationError("repository tree evidence is invalid")

        candidates: list[dict[str, Any]] = []
        existing_by_path: dict[str, Mapping[str, Any]] = {}
        for item in raw_files:
            if not isinstance(item, Mapping):
                continue
            path = item.get("path")
            sha = item.get("sha")
            if not isinstance(path, str) or not isinstance(sha, str):
                continue
            if _is_sensitive_path(path):
                continue
            evidence = {"path": path, "sha": sha, "size": item.get("size")}
            candidates.append(evidence)
            existing_by_path[path] = evidence
        candidates.sort(key=lambda item: item["path"])
        if len(candidates) > _MAX_TREE_PATHS_FOR_SELECTION:
            candidates = candidates[:_MAX_TREE_PATHS_FOR_SELECTION]

        selection_message = self._complete(
            self._selection_prompt(
                repository=repository,
                base_sha=base_sha,
                feature_branch=feature_branch,
                instruction=instruction,
                candidates=candidates,
            )
        )
        selection = _parse_selection(
            _message_content(selection_message),
            existing_paths=frozenset(existing_by_path),
            max_paths=self.max_selected_files,
        )

        file_evidence: list[dict[str, Any]] = []
        for path in selection.read_paths:
            evidence = read_client.read_file(path, feature_branch)
            if evidence.get("truncated") is True:
                raise PlanValidationError(f"planner evidence file is truncated: {path}")
            content = evidence.get("content")
            sha = evidence.get("sha")
            if not isinstance(content, str) or not isinstance(sha, str):
                raise PlanValidationError(f"planner evidence file is invalid: {path}")
            if len(content) > self.max_content_chars_per_file:
                raise PlanValidationError(f"planner evidence file exceeds content limit: {path}")
            expected_sha = existing_by_path[path].get("sha")
            if sha != expected_sha:
                raise PlanValidationError(f"planner evidence blob changed during inspection: {path}")
            file_evidence.append({"path": path, "sha": sha, "content": content})

        plan_message = self._complete(
            self._plan_prompt(
                repository=repository,
                base_sha=base_sha,
                feature_branch=feature_branch,
                instruction=instruction,
                file_evidence=file_evidence,
            )
        )
        plan = parse_execution_plan(
            _message_content(plan_message),
            expected_repository=repository,
            expected_base_sha=base_sha,
            expected_feature_branch=feature_branch,
            allowed_update_paths=frozenset(selection.read_paths),
            existing_paths=frozenset(existing_by_path),
            max_changed_files=self.max_changed_files,
            max_content_chars_per_file=self.max_content_chars_per_file,
        )
        return PlannerResult(
            plan=plan,
            selected_paths=selection.read_paths,
            model_calls=2,
            final_message={"role": "assistant", "content": plan.summary},
        )

    def _complete(self, prompt: str) -> Mapping[str, Any]:
        message = self.provider.complete_with_tools(
            [{"role": "user", "content": prompt}],
            [],
        )
        if not isinstance(message, Mapping):
            raise PlanValidationError("planner response must be an object")
        tool_calls = message.get("tool_calls")
        if tool_calls not in (None, []):
            raise PlanValidationError("planner must not request tools")
        return message

    def _selection_prompt(
        self,
        *,
        repository: str,
        base_sha: str,
        feature_branch: str,
        instruction: str,
        candidates: Sequence[Mapping[str, Any]],
    ) -> str:
        payload = {
            "repository": repository,
            "base_sha": base_sha,
            "feature_branch": feature_branch,
            "instruction": instruction,
            "candidate_files": [dict(item) for item in candidates],
        }
        return (
            "You are a bounded repository planner. Do not write files and do not request tools. "
            f"Select at most {self.max_selected_files} existing non-sensitive files whose full content "
            "the host should read before planning. Return strict JSON only with exactly this shape: "
            '{"read_paths":["path"]}. Use an empty list when no existing file must be read. '
            "Do not add unknown fields. Repository evidence follows:\n"
            + json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        )

    def _plan_prompt(
        self,
        *,
        repository: str,
        base_sha: str,
        feature_branch: str,
        instruction: str,
        file_evidence: Sequence[Mapping[str, Any]],
    ) -> str:
        payload = {
            "repository": repository,
            "base_sha": base_sha,
            "feature_branch": feature_branch,
            "instruction": instruction,
            "read_evidence": [dict(item) for item in file_evidence],
        }
        schema = {
            "repository": repository,
            "base_sha": base_sha,
            "feature_branch": feature_branch,
            "changes": [
                {
                    "path": "path",
                    "operation": "create|update",
                    "expected_blob_sha": "40-char sha for update, null for create",
                    "content": "complete UTF-8 replacement content",
                    "commit_message": "bounded commit message",
                }
            ],
            "validation_targets": ["targeted test command or check"],
            "summary": "short summary",
        }
        return (
            "You are a small planning model. The host, not you, executes repository mutations. "
            "Return strict JSON only, no markdown and no commentary. Updates are allowed only for files "
            "whose complete content appears in read_evidence. Creates may target a new safe path. "
            f"Plan at most {self.max_changed_files} file changes. Never target main/master, credentials, "
            "GitHub workflow/action control files, deploy/release/training/activation/rollback surfaces, "
            "or request shell/PR/merge actions. The JSON must contain exactly these top-level fields: "
            + json.dumps(schema, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
            + "\nRepository evidence:\n"
            + json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        )


class DeterministicExecutor:
    """Host-side bounded file executor with exact branch/blob/content checkpoints."""

    def __init__(self, read_client: TaskReadClient, mutation_client: TaskMutationClient) -> None:
        self.read_client = read_client
        self.mutation_client = mutation_client

    def execute(self, plan: DeterministicExecutionPlan) -> DeterministicExecutionResult:
        checkpoints: list[Mapping[str, Any]] = []
        changed_files: list[str] = []
        current_head = self._branch_head(plan.feature_branch)
        if current_head != plan.base_sha:
            return self._failure(
                current_head,
                changed_files,
                checkpoints,
                "feature branch does not match exact plan base SHA before execution",
            )
        if not plan.changes:
            return self._failure(
                current_head,
                changed_files,
                checkpoints,
                "plan contains no file changes",
            )

        for index, change in enumerate(plan.changes, start=1):
            before_head = self._branch_head(plan.feature_branch)
            if before_head != current_head:
                return self._failure(
                    before_head,
                    changed_files,
                    checkpoints,
                    f"feature branch moved before change {index}",
                )

            try:
                tree = self.read_client.repository_tree(plan.feature_branch)
                if tree.get("commit_sha") != before_head:
                    raise DeterministicExecutionError("tree evidence is not bound to exact branch HEAD")
                blob_by_path = _blob_map(tree)
                if change.operation == "update":
                    actual_blob = blob_by_path.get(change.path)
                    if actual_blob != change.expected_blob_sha:
                        raise DeterministicExecutionError(
                            f"stale blob mismatch for update: {change.path}"
                        )
                    write_sha = change.expected_blob_sha
                else:
                    if change.path in blob_by_path:
                        raise DeterministicExecutionError(
                            f"create target already exists: {change.path}"
                        )
                    write_sha = None

                action = self.mutation_client.write_file(
                    path=change.path,
                    content=change.content,
                    commit_message=change.commit_message,
                    branch=plan.feature_branch,
                    sha=write_sha,
                )
                if not action.executed:
                    raise DeterministicExecutionError(
                        f"host mutation policy did not execute change: {change.path}"
                    )
                if not isinstance(action.value, Mapping):
                    raise DeterministicExecutionError("mutation result does not contain exact evidence")
                commit_sha = action.value.get("commit_sha")
                content_sha = action.value.get("content_sha")
                if not isinstance(commit_sha, str) or not _SHA.fullmatch(commit_sha):
                    raise DeterministicExecutionError("mutation result commit SHA is invalid")

                after_head = self._branch_head(plan.feature_branch)
                if after_head != commit_sha or after_head == before_head:
                    raise DeterministicExecutionError(
                        f"branch HEAD did not advance exactly after change: {change.path}"
                    )

                read_back = self.read_client.read_file(change.path, plan.feature_branch)
                if read_back.get("truncated") is True:
                    raise DeterministicExecutionError(
                        f"read-back content is truncated: {change.path}"
                    )
                if read_back.get("content") != change.content:
                    raise DeterministicExecutionError(
                        f"read-back content mismatch: {change.path}"
                    )
                read_back_sha = read_back.get("sha")
                if isinstance(content_sha, str) and read_back_sha != content_sha:
                    raise DeterministicExecutionError(
                        f"read-back blob SHA mismatch: {change.path}"
                    )

                checkpoints.append(
                    {
                        "index": index,
                        "path": change.path,
                        "operation": change.operation,
                        "before_head_sha": before_head,
                        "after_head_sha": after_head,
                        "content_sha": read_back_sha,
                        "status": "APPLIED_VERIFIED",
                    }
                )
                changed_files.append(change.path)
                current_head = after_head
            except (RuntimeError, TypeError, ValueError) as exc:
                exact_head = self._branch_head(plan.feature_branch)
                return self._failure(
                    exact_head,
                    changed_files,
                    checkpoints,
                    _bounded_reason(exc),
                )

        return DeterministicExecutionResult(
            applied=True,
            head_sha=current_head,
            changed_files=tuple(changed_files),
            checkpoints=tuple(checkpoints),
            failure_reason=None,
        )

    def _branch_head(self, branch: str) -> str:
        info = self.read_client.branch_info(branch)
        head = info.get("commit_sha")
        if not isinstance(head, str) or not _SHA.fullmatch(head):
            raise DeterministicExecutionError("branch does not expose a full lowercase commit SHA")
        return head

    @staticmethod
    def _failure(
        head_sha: str,
        changed_files: Sequence[str],
        checkpoints: Sequence[Mapping[str, Any]],
        reason: str,
    ) -> DeterministicExecutionResult:
        return DeterministicExecutionResult(
            applied=False,
            head_sha=head_sha,
            changed_files=tuple(changed_files),
            checkpoints=tuple(checkpoints),
            failure_reason=reason,
        )


def parse_execution_plan(
    raw_json: str,
    *,
    expected_repository: str,
    expected_base_sha: str,
    expected_feature_branch: str,
    allowed_update_paths: frozenset[str] | None = None,
    existing_paths: frozenset[str] | None = None,
    max_changed_files: int = 3,
    max_content_chars_per_file: int = 50_000,
) -> DeterministicExecutionPlan:
    data = _strict_json_object(raw_json, "planner execution plan")
    expected_keys = {
        "repository",
        "base_sha",
        "feature_branch",
        "changes",
        "validation_targets",
        "summary",
    }
    _require_exact_keys(data, expected_keys, "execution plan")

    repository = data["repository"]
    base_sha = data["base_sha"]
    feature_branch = data["feature_branch"]
    changes = data["changes"]
    validation_targets = data["validation_targets"]
    summary = data["summary"]

    if repository != expected_repository or not isinstance(repository, str):
        raise PlanValidationError("plan repository does not match bound repository")
    if not _REPOSITORY.fullmatch(repository):
        raise PlanValidationError("plan repository is invalid")
    if base_sha != expected_base_sha or not isinstance(base_sha, str) or not _SHA.fullmatch(base_sha):
        raise PlanValidationError("plan base_sha does not match exact bound SHA")
    if feature_branch != expected_feature_branch or not isinstance(feature_branch, str):
        raise PlanValidationError("plan feature_branch does not match bound branch")
    if feature_branch.lower() in _PROTECTED_BRANCHES:
        raise PlanValidationError("plan targets a protected branch")
    if feature_branch.startswith("refs/") or ".." in feature_branch or "//" in feature_branch:
        raise PlanValidationError("plan feature branch is invalid")

    if not isinstance(changes, list):
        raise PlanValidationError("plan changes must be a list")
    if len(changes) > max_changed_files:
        raise PlanValidationError("plan exceeds maximum changed-file count")
    seen_paths: set[str] = set()
    parsed_changes: list[PlannedFileChange] = []
    for raw_change in changes:
        if not isinstance(raw_change, Mapping):
            raise PlanValidationError("each planned change must be an object")
        _require_exact_keys(
            raw_change,
            {"path", "operation", "expected_blob_sha", "content", "commit_message"},
            "planned change",
        )
        path = _safe_plan_path(raw_change["path"])
        if path in seen_paths:
            raise PlanValidationError("plan contains duplicate file paths")
        seen_paths.add(path)
        operation = raw_change["operation"]
        expected_blob_sha = raw_change["expected_blob_sha"]
        content = raw_change["content"]
        commit_message = raw_change["commit_message"]
        if operation not in {"create", "update"}:
            raise PlanValidationError("planned operation must be create or update")
        if not isinstance(content, str):
            raise PlanValidationError("planned file content must be text")
        if len(content) > max_content_chars_per_file:
            raise PlanValidationError("planned file content exceeds configured limit")
        if not isinstance(commit_message, str) or not commit_message.strip():
            raise PlanValidationError("planned commit_message must be non-empty text")
        if len(commit_message) > 500:
            raise PlanValidationError("planned commit_message exceeds configured limit")

        if operation == "update":
            if not isinstance(expected_blob_sha, str) or not _SHA.fullmatch(expected_blob_sha):
                raise PlanValidationError("update requires an exact expected_blob_sha")
            if allowed_update_paths is not None and path not in allowed_update_paths:
                raise PlanValidationError("update targets a file not supplied as full read evidence")
            if existing_paths is not None and path not in existing_paths:
                raise PlanValidationError("update target does not exist in inspected tree")
        else:
            if expected_blob_sha is not None:
                raise PlanValidationError("create requires expected_blob_sha to be null")
            if existing_paths is not None and path in existing_paths:
                raise PlanValidationError("create target already exists in inspected tree")

        parsed_changes.append(
            PlannedFileChange(
                path=path,
                operation=operation,
                expected_blob_sha=expected_blob_sha,
                content=content,
                commit_message=commit_message.strip(),
            )
        )

    if not isinstance(validation_targets, list) or not all(
        isinstance(item, str) and item.strip() for item in validation_targets
    ):
        raise PlanValidationError("validation_targets must be a list of non-empty strings")
    if len(validation_targets) > 12:
        raise PlanValidationError("validation_targets exceeds configured limit")
    normalized_targets = tuple(item.strip()[:300] for item in validation_targets)
    if not isinstance(summary, str) or not summary.strip():
        raise PlanValidationError("plan summary must be non-empty text")
    if len(summary) > 1000:
        raise PlanValidationError("plan summary exceeds configured limit")

    return DeterministicExecutionPlan(
        repository=repository,
        base_sha=base_sha,
        feature_branch=feature_branch,
        changes=tuple(parsed_changes),
        validation_targets=normalized_targets,
        summary=summary.strip(),
    )


def _parse_selection(
    raw_json: str,
    *,
    existing_paths: frozenset[str],
    max_paths: int,
) -> PlannerSelection:
    data = _strict_json_object(raw_json, "planner selection")
    _require_exact_keys(data, {"read_paths"}, "planner selection")
    read_paths = data["read_paths"]
    if not isinstance(read_paths, list):
        raise PlanValidationError("planner read_paths must be a list")
    if len(read_paths) > max_paths:
        raise PlanValidationError("planner selected too many files")
    normalized: list[str] = []
    seen: set[str] = set()
    for raw_path in read_paths:
        path = _safe_plan_path(raw_path)
        if path not in existing_paths:
            raise PlanValidationError("planner selected a file outside inspected tree")
        if path in seen:
            raise PlanValidationError("planner selected duplicate files")
        seen.add(path)
        normalized.append(path)
    return PlannerSelection(read_paths=tuple(normalized))


def _strict_json_object(raw_json: str, label: str) -> dict[str, Any]:
    if not isinstance(raw_json, str):
        raise PlanValidationError(f"{label} must be JSON text")
    stripped = raw_json.strip()
    if not stripped or stripped.startswith("```"):
        raise PlanValidationError(f"{label} must be strict JSON without markdown fences")
    try:
        decoded = json.loads(stripped)
    except json.JSONDecodeError as exc:
        raise PlanValidationError(f"{label} is not valid JSON") from exc
    if not isinstance(decoded, dict):
        raise PlanValidationError(f"{label} must decode to an object")
    return decoded


def _require_exact_keys(value: Mapping[str, Any], expected: set[str], label: str) -> None:
    keys = set(value)
    if keys != expected:
        unknown = sorted(keys - expected)
        missing = sorted(expected - keys)
        detail: list[str] = []
        if unknown:
            detail.append(f"unknown={unknown}")
        if missing:
            detail.append(f"missing={missing}")
        raise PlanValidationError(f"{label} fields are invalid: {'; '.join(detail)}")


def _safe_plan_path(raw_path: Any) -> str:
    if not isinstance(raw_path, str):
        raise PlanValidationError("planned path must be text")
    path = raw_path.strip("/")
    parts = path.split("/")
    if (
        not path
        or len(path) > 1024
        or "\x00" in path
        or "\\" in path
        or ".." in parts
        or "" in parts
    ):
        raise PlanValidationError("planned path is invalid")
    if _is_sensitive_path(path):
        raise PlanValidationError("planned path is sensitive or control-plane protected")
    return path


def _is_sensitive_path(path: str) -> bool:
    normalized = path.strip("/")
    parts = tuple(part.lower() for part in normalized.split("/") if part)
    if not parts:
        return True
    basename = parts[-1]
    lowered = normalized.lower()
    if any(part in _SENSITIVE_DIRECTORIES for part in parts[:-1]):
        return True
    if basename in _SENSITIVE_BASENAMES or basename.startswith(".env."):
        return True
    if basename.endswith(_SENSITIVE_SUFFIXES):
        return True
    return lowered.startswith(_CONTROL_PATH_PREFIXES)


def _message_content(message: Mapping[str, Any]) -> str:
    if message.get("role", "assistant") != "assistant":
        raise PlanValidationError("planner response role must be assistant")
    content = message.get("content")
    if not isinstance(content, str):
        raise PlanValidationError("planner response content must be text")
    return content


def _blob_map(tree: Mapping[str, Any]) -> dict[str, str]:
    raw_files = tree.get("files")
    if not isinstance(raw_files, list):
        raise DeterministicExecutionError("repository tree evidence is invalid")
    result: dict[str, str] = {}
    for item in raw_files:
        if not isinstance(item, Mapping):
            continue
        path = item.get("path")
        sha = item.get("sha")
        if isinstance(path, str) and isinstance(sha, str):
            result[path] = sha
    return result


def _bounded_reason(exc: BaseException) -> str:
    text = " ".join(str(exc).split()) or exc.__class__.__name__
    return text[:500]
