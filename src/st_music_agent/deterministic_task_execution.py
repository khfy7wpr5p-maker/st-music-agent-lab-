from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from .app3_task_execution import App3TaskService
from .app7_task_execution import App7TaskService
from .deterministic_executor import DeterministicExecutionError, DeterministicExecutor
from .policy import AutonomyDecision
from .structured_planner import StructuredCompactPlanner
from .task_execution import TaskExecutionError, TaskRunRecord, _require_action
from .task_state import TaskOutcome, TaskStage, ValidatorStatus
from .tools import ActionApproval


class _DeterministicRunMixin:
    """Replace the inherited model tool-loop with MODEL_PLANS_HOST_EXECUTES."""

    def open_pull_request(self, task_id: str) -> Mapping[str, Any]:
        """Open a human-approved validation PR when PR-triggered CI is the remaining gate.

        The PR does not imply VERIFIED_SUCCESS and does not authorize merge. It exists only so
        repositories whose workflows run on pull_request can produce exact-SHA CI evidence.
        """
        if not self.config.enabled:
            raise TaskExecutionError("task execution is disabled")

        view = self._persisted_view(task_id)
        existing = view.get("pull_request")
        if isinstance(existing, Mapping):
            return dict(existing)

        if view.get("outcome") == TaskOutcome.VERIFIED_SUCCESS.value:
            return super().open_pull_request(task_id)

        if view.get("stage") != TaskStage.CI_PENDING.value:
            raise TaskExecutionError(
                "task must be CI_PENDING or VERIFIED_SUCCESS before opening a pull request"
            )

        refreshed = self.refresh_evidence(task_id)
        if refreshed.get("stage") == TaskStage.FAILED.value:
            raise TaskExecutionError("task failed while refreshing validation evidence")
        if refreshed.get("outcome") == TaskOutcome.VERIFIED_SUCCESS.value:
            return super().open_pull_request(task_id)

        ci = refreshed.get("ci")
        validators = refreshed.get("validators")
        if not isinstance(ci, Mapping) or ci.get("state") != "pending":
            raise TaskExecutionError(
                "validation PR requires pending exact-SHA CI evidence"
            )
        if not isinstance(validators, list) or not validators:
            raise TaskExecutionError("validation PR requires host validator evidence")
        if any(
            not isinstance(item, Mapping)
            or item.get("status") != ValidatorStatus.PASS.value
            for item in validators
        ):
            raise TaskExecutionError(
                "validation PR requires all configured host validators to pass"
            )

        view = self._persisted_view(task_id)
        preview = self._persistent_preview(view)
        commit = view.get("commit")
        if not isinstance(commit, Mapping):
            raise TaskExecutionError("task is missing exact commit evidence")
        head_sha = commit.get("head_sha")
        if not _full_sha(head_sha):
            raise TaskExecutionError("task head SHA is invalid")
        assert isinstance(head_sha, str)

        repository = str(preview["repository"])
        feature_branch = str(preview["feature_branch"])
        base_branch = str(preview["base_branch"])
        read_client = self._read_factory(repository)
        branch = read_client.branch_info(feature_branch)
        if branch.get("commit_sha") != head_sha:
            raise TaskExecutionError(
                "task branch moved after commit binding; validation PR opening is rejected"
            )

        target = f"{feature_branch}->{base_branch}"
        approval = ActionApproval(action_name="github.open_pull_request", target=target)
        mutation = self._mutation_factory(repository)
        result = mutation.open_pull_request(
            title=f"ST Agent validation task {task_id[-12:]}",
            head=feature_branch,
            base=base_branch,
            body=(
                "Human-approved validation PR created by ST Music Agent.\n\n"
                f"Task: `{task_id}`\n"
                f"Base SHA at preview: `{preview['base_sha']}`\n"
                f"Bound head SHA: `{head_sha}`\n\n"
                "This PR exists to trigger exact-SHA pull-request CI. The task is not yet "
                "VERIFIED_SUCCESS. Merge and production actions remain unauthorized until CI and "
                "validators are reviewed."
            ),
            approval=approval,
        )
        _require_action(
            result,
            AutonomyDecision.REQUIRE_HUMAN,
            "validation pull request did not execute",
        )
        if not isinstance(result.value, Mapping):
            raise TaskExecutionError("validation pull request result is invalid")
        number = result.value.get("number")
        if not isinstance(number, int) or isinstance(number, bool):
            raise TaskExecutionError("validation pull request does not expose a valid number")

        metadata = dict(result.value)
        pull_request_reader = getattr(read_client, "pull_request", None)
        if callable(pull_request_reader):
            pr = pull_request_reader(number)
            if not isinstance(pr, Mapping):
                raise TaskExecutionError("validation pull request read-back evidence is invalid")
            if pr.get("head_ref") != feature_branch or pr.get("head_sha") != head_sha:
                raise TaskExecutionError(
                    "validation pull request head does not match the bound task HEAD"
                )
            if pr.get("base_ref") != base_branch:
                raise TaskExecutionError(
                    "validation pull request base does not match the intended task base"
                )
            metadata.update(
                {
                    "head_sha": pr.get("head_sha"),
                    "base_sha": pr.get("base_sha"),
                    "mergeable": pr.get("mergeable"),
                    "draft": pr.get("draft"),
                }
            )

        metadata.update(
            {
                "ci_status": "pending",
                "validation_only": True,
                "verification_status": "PENDING_CI",
                "merge_authorized": False,
                "production_actions_authorized": False,
            }
        )
        # Record PR metadata without advancing the stage. TaskEventStore projects any PR_OPENED
        # event into pull_request while the stage remains CI_PENDING, allowing CI refresh to proceed.
        self.store.append_evidence(task_id, TaskStage.PR_OPENED.value, metadata)
        self._pull_requests[task_id] = metadata
        return metadata

    def run(self, task_id: str) -> TaskRunRecord:
        preview = self._preview(task_id)
        if not self.config.enabled:
            raise TaskExecutionError("task execution is disabled; start the app with --enable-writes")
        if not self.store.has_task(task_id):
            raise TaskExecutionError("task must be persisted by preview before execution")

        stage = self.store.current_stage(task_id)
        completed_stages = {
            TaskStage.COMMIT_BOUND,
            TaskStage.CI_PENDING,
            TaskStage.CI_REVIEWED,
            TaskStage.VALIDATORS_REVIEWED,
            TaskStage.VERIFIED_SUCCESS,
            TaskStage.PR_OPENED,
        }
        if stage in completed_stages:
            existing = self._runs.get(task_id)
            if existing is not None:
                return existing
            raise TaskExecutionError("task execution already completed; refresh its evidence instead")
        if stage is TaskStage.FAILED:
            raise TaskExecutionError("failed task attempt cannot be rewritten; create a new task attempt")

        mutation = self._mutation_factory(preview.repository)
        read_client = self._read_factory(preview.repository)
        if stage is TaskStage.PREVIEWED:
            branch_result = mutation.create_branch(preview.feature_branch, preview.base_sha)
            _require_action(
                branch_result,
                AutonomyDecision.AUTO_EXECUTE,
                "feature branch creation did not execute",
            )
            self.store.append_stage(
                task_id,
                TaskStage.BRANCH_CREATED,
                {"feature_branch": preview.feature_branch, "base_sha": preview.base_sha},
            )
            stage = TaskStage.BRANCH_CREATED

        if stage is TaskStage.BRANCH_CREATED:
            self.store.append_stage(
                task_id,
                TaskStage.AGENT_RUNNING,
                {
                    "feature_branch": preview.feature_branch,
                    "execution_mode": "MODEL_PLANS_HOST_EXECUTES",
                },
            )
        elif stage is TaskStage.AGENT_RUNNING:
            self.store.append_evidence(
                task_id,
                "RESUME_REQUESTED",
                {
                    "feature_branch": preview.feature_branch,
                    "execution_mode": "MODEL_PLANS_HOST_EXECUTES",
                },
            )
        else:
            raise TaskExecutionError("task is not resumable from its current stage")

        provider = self._provider_client or self._build_provider()
        planner = StructuredCompactPlanner(provider)
        try:
            planner_result = planner.build_plan(
                repository=preview.repository,
                base_sha=preview.base_sha,
                feature_branch=preview.feature_branch,
                instruction=preview.instruction,
                read_client=read_client,
            )
        except Exception as exc:  # noqa: BLE001 - provider/transport failures must fail the task closed.
            message = f"deterministic planner failed: {_bounded_message(exc)}"
            self.store.append_evidence(task_id, "PLANNER_FAILURE", {"message": message[:500]})
            self._fail(task_id, message)
            raise TaskExecutionError(message) from exc

        plan = planner_result.plan
        self.store.append_evidence(
            task_id,
            "PLAN_VALIDATED",
            {
                "repository": plan.repository,
                "base_sha": plan.base_sha,
                "feature_branch": plan.feature_branch,
                "selected_paths": list(planner_result.selected_paths),
                "planned_changes": [
                    {
                        "path": change.path,
                        "operation": change.operation,
                        "expected_blob_sha": change.expected_blob_sha,
                    }
                    for change in plan.changes
                ],
                "validation_targets": list(plan.validation_targets),
                "summary": plan.summary,
                "model_calls": planner_result.model_calls,
                "model_write_tools_exposed": False,
            },
        )
        self.store.append_stage(
            task_id,
            TaskStage.AGENT_COMPLETED,
            {
                "model_name": self._profile().name,
                "turns": planner_result.model_calls,
                "tool_calls": 0,
                "summary": plan.summary[:1000],
                "execution_mode": "MODEL_PLANS_HOST_EXECUTES",
            },
        )

        executor = DeterministicExecutor(read_client, mutation)
        try:
            execution = executor.execute(plan)
        except Exception as exc:  # noqa: BLE001 - host adapter failures must fail the task closed.
            message = f"deterministic executor failed: {_bounded_message(exc)}"
            self._fail(task_id, message)
            raise TaskExecutionError(message) from exc

        for checkpoint in execution.checkpoints:
            self.store.append_evidence(task_id, "EXECUTOR_CHECKPOINT", dict(checkpoint))

        if not execution.applied:
            reason = execution.failure_reason or "deterministic executor did not apply the plan"
            self.store.append_evidence(
                task_id,
                "EXECUTOR_FAILURE",
                {
                    "head_sha": execution.head_sha,
                    "changed_files": list(execution.changed_files),
                    "message": reason[:500],
                },
            )
            self._fail(task_id, f"deterministic executor failed: {reason}")
            raise TaskExecutionError(f"deterministic executor failed: {reason}")

        head_sha = execution.head_sha
        if not _full_sha(head_sha):
            self._fail(task_id, "deterministic executor returned an invalid feature-branch HEAD")
            raise TaskExecutionError("deterministic executor returned an invalid feature-branch HEAD")
        if head_sha == preview.base_sha:
            self._fail(task_id, "deterministic executor produced no feature-branch commit")
            raise TaskExecutionError("deterministic executor produced no feature-branch commit")

        try:
            compare = self._compare(read_client, preview.base_sha, head_sha)
        except (RuntimeError, TypeError, ValueError) as exc:
            self._fail(task_id, f"exact compare evidence unavailable: {_bounded_message(exc)}")
            raise TaskExecutionError("exact compare evidence could not be bound") from exc
        changed_files = compare.get("files")
        if not isinstance(changed_files, list) or not changed_files:
            self._fail(task_id, "exact compare evidence contains no changed files")
            raise TaskExecutionError("exact compare evidence contains no changed files")
        compare_paths = {
            item.get("path")
            for item in changed_files
            if isinstance(item, Mapping) and isinstance(item.get("path"), str)
        }
        if not set(execution.changed_files).issubset(compare_paths):
            self._fail(task_id, "exact compare evidence does not contain all executor changed files")
            raise TaskExecutionError(
                "exact compare evidence does not contain all executor changed files"
            )

        self.store.append_stage(
            task_id,
            TaskStage.COMMIT_BOUND,
            {
                "head_sha": head_sha,
                "base_sha": preview.base_sha,
                "feature_branch": preview.feature_branch,
                "changed_files": changed_files,
                "ahead_by": compare.get("ahead_by"),
                "behind_by": compare.get("behind_by"),
                "total_commits": compare.get("total_commits"),
                "execution_mode": "MODEL_PLANS_HOST_EXECUTES",
            },
        )
        self.store.append_stage(
            task_id,
            TaskStage.CI_PENDING,
            {"head_sha": head_sha, "reason": "awaiting explicit CI/validator refresh"},
        )

        record = TaskRunRecord(
            task_id=task_id,
            repository=preview.repository,
            feature_branch=preview.feature_branch,
            base_sha=preview.base_sha,
            head_sha=head_sha,
            model_name=self._profile().name,
            final_message=planner_result.final_message,
            turns=planner_result.model_calls,
            tool_calls=0,
            workflow_runs=(),
        )
        self._runs[task_id] = record
        return record


class DeterministicApp3TaskService(_DeterministicRunMixin, App3TaskService):
    """APP3 service using a bounded planner and deterministic host-side mutation executor."""


class DeterministicApp7TaskService(_DeterministicRunMixin, App7TaskService):
    """APP7-compatible service preserving audit/validator authority with deterministic writes."""


def _bounded_message(exc: BaseException) -> str:
    return (" ".join(str(exc).split()) or exc.__class__.__name__)[:300]


def _full_sha(value: Any) -> bool:
    return isinstance(value, str) and len(value) == 40 and all(
        char in "0123456789abcdef" for char in value
    )
