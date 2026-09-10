from __future__ import annotations

from pathlib import PurePosixPath

from .models import Action, ActionRequest, AuthorityMode, PolicyDecision, TaskSpec


HARD_DENY: frozenset[Action] = frozenset(
    {
        Action.DIRECT_DEFAULT_BRANCH_WRITE,
        Action.FORCE_PUSH,
        Action.AUTOMATIC_MERGE,
        Action.WEAKEN_VALIDATOR,
        Action.PRODUCTION_DEPLOYMENT,
        Action.SECRET_COMMIT,
        Action.PRIVATE_STUDENT_DATA_ACCESS,
    }
)

BRANCH_WRITE_ACTIONS: frozenset[Action] = frozenset(
    {
        Action.CREATE_NON_DEFAULT_TASK_BRANCH,
        Action.WRITE_BOUNDED_TASK_FILES,
        Action.COMMIT_TO_TASK_BRANCH,
        Action.RUN_VALIDATORS,
    }
)

PR_WRITE_ACTIONS: frozenset[Action] = frozenset(
    {
        Action.OPEN_PULL_REQUEST,
        Action.UPDATE_TASK_PULL_REQUEST,
        Action.BOUNDED_CI_REPAIR,
    }
)

DEFAULT_BRANCH_NAMES = frozenset({"main", "master"})


class PolicyEngine:
    """Framework-independent authority gate for every proposed agent action."""

    def evaluate(self, task: TaskSpec, request: ActionRequest) -> PolicyDecision:
        if request.action in HARD_DENY:
            return PolicyDecision(False, "hard-denied by ST authority policy")

        if request.action not in task.capabilities:
            return PolicyDecision(False, "capability not granted by TaskSpec")

        if request.action in BRANCH_WRITE_ACTIONS:
            if task.mode not in {AuthorityMode.BRANCH_WRITE, AuthorityMode.PR_WRITE}:
                return PolicyDecision(False, "branch mutation requires BRANCH_WRITE or PR_WRITE mode")
            branch_decision = self._check_non_default_branch(request.target_branch)
            if not branch_decision.allowed:
                return branch_decision

        if request.action in PR_WRITE_ACTIONS and task.mode is not AuthorityMode.PR_WRITE:
            return PolicyDecision(False, "pull-request mutation requires PR_WRITE mode")

        if request.action is Action.WRITE_BOUNDED_TASK_FILES:
            return self._check_path(task, request.path)

        return PolicyDecision(True, "allowed by TaskSpec and ST authority policy")

    @staticmethod
    def _check_non_default_branch(branch: str | None) -> PolicyDecision:
        if not branch:
            return PolicyDecision(False, "write action requires an explicit task branch")
        if branch in DEFAULT_BRANCH_NAMES:
            return PolicyDecision(False, "default-branch mutation is forbidden")
        return PolicyDecision(True, "non-default task branch admitted")

    @staticmethod
    def _check_path(task: TaskSpec, path: str | None) -> PolicyDecision:
        if not path:
            return PolicyDecision(False, "file write requires an explicit path")
        candidate = PurePosixPath(path)
        if candidate.is_absolute() or ".." in candidate.parts:
            return PolicyDecision(False, "unsafe path rejected")
        if not task.allowed_paths:
            return PolicyDecision(False, "TaskSpec grants no writable paths")
        for allowed in task.allowed_paths:
            root = PurePosixPath(allowed)
            if candidate == root or root in candidate.parents:
                return PolicyDecision(True, "path is inside TaskSpec write boundary")
        return PolicyDecision(False, "path is outside TaskSpec write boundary")
