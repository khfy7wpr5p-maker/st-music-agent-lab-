from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from pathlib import PurePosixPath
from typing import Mapping, Sequence


class AuthorityMode(str, Enum):
    READ_ONLY = "READ_ONLY"
    BRANCH_WRITE = "BRANCH_WRITE"
    PR_WRITE = "PR_WRITE"


class Action(str, Enum):
    READ_REPOSITORY = "read_repository"
    INSPECT_ARCHITECTURE = "inspect_architecture"
    INSPECT_PULL_REQUESTS = "inspect_pull_requests"
    INSPECT_CI = "inspect_ci"
    RUN_BOUNDED_SANDBOX_TESTS = "run_bounded_sandbox_tests"
    PRODUCE_REPORTS = "produce_reports"
    CREATE_NON_DEFAULT_TASK_BRANCH = "create_non_default_task_branch"
    WRITE_BOUNDED_TASK_FILES = "write_bounded_task_files"
    COMMIT_TO_TASK_BRANCH = "commit_to_task_branch"
    RUN_VALIDATORS = "run_validators"
    OPEN_PULL_REQUEST = "open_pull_request"
    UPDATE_TASK_PULL_REQUEST = "update_task_pull_request"
    BOUNDED_CI_REPAIR = "perform_bounded_ci_repair_loop"
    DIRECT_DEFAULT_BRANCH_WRITE = "direct_default_branch_write"
    FORCE_PUSH = "force_push"
    AUTOMATIC_MERGE = "automatic_merge"
    WEAKEN_VALIDATOR = "ci_or_validator_weakening"
    PRODUCTION_DEPLOYMENT = "production_deployment"
    SECRET_COMMIT = "secret_commit"
    PRIVATE_STUDENT_DATA_ACCESS = "private_or_student_data_access"


class RunState(str, Enum):
    SUCCEEDED = "SUCCEEDED"
    NEEDS_REVIEW = "NEEDS_REVIEW"
    BLOCKED = "BLOCKED"
    ABSTAINED = "ABSTAINED"


@dataclass(frozen=True, slots=True)
class TaskSpec:
    task_id: str
    objective: str
    target_repository: str
    base_ref: str = "main"
    mode: AuthorityMode = AuthorityMode.READ_ONLY
    capabilities: frozenset[Action] = field(default_factory=frozenset)
    allowed_paths: tuple[str, ...] = ()
    allowed_commands: tuple[tuple[str, ...], ...] = ()
    timeout_seconds: int = 30
    retry_budget: int = 0

    def __post_init__(self) -> None:
        if not self.task_id.strip():
            raise ValueError("task_id must be non-empty")
        if not self.objective.strip():
            raise ValueError("objective must be non-empty")
        if not self.target_repository.strip():
            raise ValueError("target_repository must be non-empty")
        if not 1 <= self.timeout_seconds <= 60:
            raise ValueError("timeout_seconds must be between 1 and 60")
        if not 0 <= self.retry_budget <= 3:
            raise ValueError("retry_budget must be between 0 and 3")
        for path in self.allowed_paths:
            normalized = PurePosixPath(path)
            if normalized.is_absolute() or ".." in normalized.parts:
                raise ValueError(f"unsafe allowed path: {path}")
        for command in self.allowed_commands:
            if not command or any(not part for part in command):
                raise ValueError("allowed commands must contain non-empty argv parts")


@dataclass(frozen=True, slots=True)
class ActionRequest:
    action: Action
    target_branch: str | None = None
    path: str | None = None
    metadata: Mapping[str, str] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class PolicyDecision:
    allowed: bool
    reason: str


@dataclass(frozen=True, slots=True)
class PlannedAction:
    request: ActionRequest
    rationale: str = ""


@dataclass(frozen=True, slots=True)
class AgentPlan:
    actions: Sequence[PlannedAction]
    blocked_actions: Sequence[PlannedAction]
