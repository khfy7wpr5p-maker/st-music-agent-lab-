from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path
from typing import Any

from .agent_tools import ToolRegistry
from .github_read import GitHubReadConfig, GitHubReadError
from .policy import AutonomyDecision
from .task_execution import (
    BoundTaskWriteToolset,
    GuardedTaskService,
    TaskExecutionConfig,
    TaskExecutionError,
    TaskGitHubReadClient,
    TaskPreview,
    TaskRepositoryReadToolset,
    TaskRunRecord,
    _require_action,
)
from .task_state import (
    DEFAULT_PROJECT_PROFILES,
    ProjectExecutionProfile,
    TaskEventStore,
    TaskOutcome,
    TaskStage,
    TaskStateError,
    ValidatorResult,
    ValidatorStatus,
    default_task_state_path,
    instruction_fingerprint,
)
from .tool_loop import ToolLoopBudget, ToolLoopRunner
from .tools import ActionApproval

_MAX_CHANGED_FILES = 250


class App3GitHubReadClient(TaskGitHubReadClient):
    """APP3 read adapter with bounded compare evidence for one exact task commit."""

    def compare_commits(self, base_sha: str, head_sha: str) -> dict[str, Any]:
        for label, value in (("base_sha", base_sha), ("head_sha", head_sha)):
            if not _full_sha(value):
                raise ValueError(f"{label} must be a full lowercase Git SHA")
        data = self._get(f"/compare/{base_sha}...{head_sha}")
        raw_files = data.get("files")
        if not isinstance(raw_files, list):
            raise GitHubReadError("GitHub compare response is missing files")
        if len(raw_files) > _MAX_CHANGED_FILES:
            raise GitHubReadError("GitHub compare exceeds configured changed-file limit")

        files: list[dict[str, Any]] = []
        for item in raw_files:
            if not isinstance(item, Mapping):
                continue
            path = item.get("filename")
            if not isinstance(path, str):
                continue
            try:
                safe_path = self._safe_path(path)
            except ValueError:
                continue
            files.append(
                {
                    "path": safe_path,
                    "status": item.get("status"),
                    "additions": _optional_int(item.get("additions")),
                    "deletions": _optional_int(item.get("deletions")),
                    "changes": _optional_int(item.get("changes")),
                }
            )
        files.sort(key=lambda item: item["path"])
        return {
            "base_sha": base_sha,
            "head_sha": head_sha,
            "status": data.get("status"),
            "ahead_by": data.get("ahead_by"),
            "behind_by": data.get("behind_by"),
            "total_commits": data.get("total_commits"),
            "files": files,
        }


class App3TaskService(GuardedTaskService):
    """Persistent APP3 task service with exact evidence and human-gated PR opening."""

    def __init__(
        self,
        config: TaskExecutionConfig,
        *,
        state_path: str | Path | None = None,
        store: TaskEventStore | None = None,
        profiles: Mapping[str, ProjectExecutionProfile] | None = None,
        **kwargs: Any,
    ) -> None:
        super().__init__(config, **kwargs)
        self.store = store or TaskEventStore(state_path or default_task_state_path())
        self.profiles = dict(profiles or DEFAULT_PROJECT_PROFILES)

    def preview(self, project: str, instruction: str) -> TaskPreview:
        preview = super().preview(project, instruction)
        payload = {
            "project": preview.project,
            "repository": preview.repository,
            "base_branch": preview.base_branch,
            "base_sha": preview.base_sha,
            "feature_branch": preview.feature_branch,
            "instruction_fingerprint": instruction_fingerprint(preview.instruction),
            "policy": {
                "create_branch": preview.create_branch_decision.value,
                "write_file": preview.write_file_decision.value,
                "open_pull_request": preview.pull_request_decision.value,
            },
        }
        if not self.store.has_task(preview.task_id):
            self.store.append_stage(preview.task_id, TaskStage.PREVIEWED, payload)
        else:
            existing = self.store.task_view(preview.task_id).get("preview")
            if existing != payload:
                raise TaskExecutionError("persistent task identity does not match this preview")
        return preview

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
                {"feature_branch": preview.feature_branch},
            )
        elif stage is TaskStage.AGENT_RUNNING:
            self.store.append_evidence(
                task_id,
                "RESUME_REQUESTED",
                {"feature_branch": preview.feature_branch},
            )
        else:
            raise TaskExecutionError("task is not resumable from its current stage")

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
        try:
            result = runner.run(self._agent_instruction(preview))
        except (RuntimeError, TypeError, ValueError) as exc:
            self._fail(task_id, f"agent execution failed: {_bounded_message(exc)}")
            raise

        self.store.append_stage(
            task_id,
            TaskStage.AGENT_COMPLETED,
            {
                "model_name": self._profile().name,
                "turns": result.turns,
                "tool_calls": result.tool_calls,
                "summary": _message_summary(result.final_message),
            },
        )

        branch = read_client.branch_info(preview.feature_branch)
        head_sha = branch.get("commit_sha")
        if not _full_sha(head_sha):
            self._fail(task_id, "feature branch does not expose a full commit SHA after run")
            raise TaskExecutionError("feature branch does not expose a full commit SHA after run")
        assert isinstance(head_sha, str)
        if head_sha == preview.base_sha:
            self._fail(task_id, "agent completed without producing a feature-branch commit")
            raise TaskExecutionError("agent completed without producing a feature-branch commit")

        try:
            compare = self._compare(read_client, preview.base_sha, head_sha)
        except (RuntimeError, TypeError, ValueError) as exc:
            self._fail(task_id, f"exact compare evidence unavailable: {_bounded_message(exc)}")
            raise TaskExecutionError("exact compare evidence could not be bound") from exc
        changed_files = compare.get("files")
        if not isinstance(changed_files, list) or not changed_files:
            self._fail(task_id, "exact compare evidence contains no changed files")
            raise TaskExecutionError("exact compare evidence contains no changed files")

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
            final_message=result.final_message,
            turns=result.turns,
            tool_calls=result.tool_calls,
            workflow_runs=(),
        )
        self._runs[task_id] = record
        return record

    def refresh_evidence(self, task_id: str) -> dict[str, Any]:
        view = self._persisted_view(task_id)
        stage = TaskStage(view["stage"])
        if stage in {TaskStage.FAILED, TaskStage.PR_OPENED}:
            return self.status(task_id)
        if stage not in {
            TaskStage.CI_PENDING,
            TaskStage.CI_REVIEWED,
            TaskStage.VALIDATORS_REVIEWED,
            TaskStage.VERIFIED_SUCCESS,
        }:
            raise TaskExecutionError("task has not reached exact commit binding")

        preview = self._persistent_preview(view)
        commit = view.get("commit")
        if not isinstance(commit, Mapping):
            raise TaskExecutionError("persistent task is missing commit evidence")
        head_sha = commit.get("head_sha")
        if not _full_sha(head_sha):
            raise TaskExecutionError("persistent task head SHA is invalid")
        assert isinstance(head_sha, str)
        read_client = self._read_factory(str(preview["repository"]))

        branch = read_client.branch_info(str(preview["feature_branch"]))
        exact_head = branch.get("commit_sha") == head_sha
        runs, workflow_error = self._workflow_evidence(read_client, head_sha)
        exact_runs = [item for item in runs if item.get("head_sha") == head_sha]
        profile = self._profile_for(str(preview["project"]))
        ci = self._ci_snapshot(head_sha, exact_runs, profile, workflow_error)
        self.store.append_evidence(task_id, "CI_SNAPSHOT", ci)

        validators = self._validators(preview, commit, head_sha, exact_head=exact_head)
        self.store.append_evidence(
            task_id,
            "VALIDATOR_SNAPSHOT",
            {"head_sha": head_sha, "results": [item.as_dict() for item in validators]},
        )

        if stage is TaskStage.VERIFIED_SUCCESS:
            if not exact_head:
                raise TaskExecutionError("verified task branch moved away from its exact green HEAD")
            return self.status(task_id)

        if ci["state"] == "failed" or any(
            item.status is ValidatorStatus.FAIL for item in validators
        ):
            self._fail(task_id, "required CI or validator evidence failed")
            return self.status(task_id)

        if stage is TaskStage.CI_PENDING and ci["state"] == "success":
            self.store.append_stage(
                task_id,
                TaskStage.CI_REVIEWED,
                {"head_sha": head_sha, "workflow_names": ci["workflow_names"]},
            )
            stage = TaskStage.CI_REVIEWED

        if stage is TaskStage.CI_REVIEWED:
            self.store.append_stage(
                task_id,
                TaskStage.VALIDATORS_REVIEWED,
                {
                    "head_sha": head_sha,
                    "validator_names": [item.name for item in validators],
                },
            )
            stage = TaskStage.VALIDATORS_REVIEWED

        validators_pass = bool(validators) and all(
            item.status is ValidatorStatus.PASS for item in validators
        )
        if stage is TaskStage.VALIDATORS_REVIEWED and ci["state"] == "success":
            if validators_pass:
                self.store.append_stage(
                    task_id,
                    TaskStage.VERIFIED_SUCCESS,
                    {"head_sha": head_sha},
                )
                outcome = TaskOutcome.VERIFIED_SUCCESS
            else:
                outcome = TaskOutcome.REVIEW_REQUIRED
        elif ci["state"] == "unavailable" or any(
            item.status is ValidatorStatus.UNAVAILABLE for item in validators
        ):
            outcome = TaskOutcome.REVIEW_REQUIRED
        else:
            outcome = TaskOutcome.WORKING
        self.store.append_evidence(task_id, "OUTCOME", {"outcome": outcome.value})
        return self.status(task_id)

    def open_pull_request(self, task_id: str) -> Mapping[str, Any]:
        if not self.config.enabled:
            raise TaskExecutionError("task execution is disabled")
        view = self._persisted_view(task_id)
        if view.get("outcome") != TaskOutcome.VERIFIED_SUCCESS.value:
            raise TaskExecutionError("task must reach VERIFIED_SUCCESS before opening a pull request")
        existing = view.get("pull_request")
        if isinstance(existing, Mapping):
            return dict(existing)

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
            raise TaskExecutionError("task branch moved after verification; PR opening is rejected")

        target = f"{feature_branch}->{base_branch}"
        approval = ActionApproval(action_name="github.open_pull_request", target=target)
        mutation = self._mutation_factory(repository)
        result = mutation.open_pull_request(
            title=f"ST Agent APP3 task {task_id[-12:]}",
            head=feature_branch,
            base=base_branch,
            body=(
                "Created from an explicitly reviewed ST Music Agent APP3 task.\n\n"
                f"Task: `{task_id}`\n"
                f"Base SHA at preview: `{preview['base_sha']}`\n"
                f"Verified head SHA: `{head_sha}`\n\n"
                "Exact CI and validator evidence is recorded by the local APP3 task store. "
                "Merge remains a separate human/host action."
            ),
            approval=approval,
        )
        _require_action(result, AutonomyDecision.REQUIRE_HUMAN, "pull request did not execute")
        if not isinstance(result.value, Mapping):
            raise TaskExecutionError("pull request result is invalid")
        number = result.value.get("number")
        if not isinstance(number, int) or isinstance(number, bool):
            raise TaskExecutionError("pull request result does not expose a valid number")

        metadata = dict(result.value)
        pull_request_reader = getattr(read_client, "pull_request", None)
        if callable(pull_request_reader):
            pr = pull_request_reader(number)
            if not isinstance(pr, Mapping):
                raise TaskExecutionError("pull request read-back evidence is invalid")
            if pr.get("head_ref") != feature_branch or pr.get("head_sha") != head_sha:
                raise TaskExecutionError("pull request head does not match the verified task HEAD")
            if pr.get("base_ref") != base_branch:
                raise TaskExecutionError("pull request base does not match the intended task base")
            metadata.update(
                {
                    "head_sha": pr.get("head_sha"),
                    "base_sha": pr.get("base_sha"),
                    "mergeable": pr.get("mergeable"),
                    "draft": pr.get("draft"),
                }
            )
        ci = view.get("ci")
        metadata["ci_status"] = ci.get("state") if isinstance(ci, Mapping) else None
        self.store.append_stage(task_id, TaskStage.PR_OPENED, metadata)
        self._pull_requests[task_id] = metadata
        return metadata

    def status(self, task_id: str) -> dict[str, Any]:
        view = self._persisted_view(task_id)
        current_preview = self._previews.get(task_id)
        if current_preview is not None:
            preview_payload = current_preview.as_dict()
        else:
            preview_payload = {
                "schema_version": "1.0.0",
                **self._persistent_preview(view),
                "instruction": None,
                "resumed_from_persistent_state": True,
            }
        run = self._runs.get(task_id)
        return {
            "schema_version": "1.0.0",
            "task_id": task_id,
            "stage": view.get("stage"),
            "outcome": view.get("outcome"),
            "attempt": view.get("attempt", 1),
            "preview": preview_payload,
            "run": run.as_dict() if run is not None else view.get("execution"),
            "execution": view.get("execution"),
            "commit": view.get("commit"),
            "ci": view.get("ci"),
            "validators": view.get("validators", []),
            "pull_request": view.get("pull_request"),
            "merge_authorized": False,
            "production_actions_authorized": False,
        }

    def recent_tasks(self, limit: int = 20) -> list[dict[str, Any]]:
        if limit < 1 or limit > 100:
            raise ValueError("limit must be between 1 and 100")
        task_ids: list[str] = []
        for item in reversed(self.store._events):
            task_id = item["task_id"]
            if task_id not in task_ids:
                task_ids.append(task_id)
            if len(task_ids) >= limit:
                break
        return [self.status(task_id) for task_id in task_ids]

    def _default_read_factory(self, repository: str) -> App3GitHubReadClient:
        return App3GitHubReadClient(
            GitHubReadConfig(
                repository=repository,
                token_env=self.config.github_token_env,
                api_base=self.config.github_api_base,
            )
        )

    def _persisted_view(self, task_id: str) -> dict[str, Any]:
        try:
            return self.store.task_view(task_id)
        except TaskStateError as exc:
            raise TaskExecutionError(str(exc)) from exc

    @staticmethod
    def _persistent_preview(view: Mapping[str, Any]) -> dict[str, Any]:
        preview = view.get("preview")
        if not isinstance(preview, Mapping):
            raise TaskExecutionError("persistent task is missing preview metadata")
        required = {
            "project",
            "repository",
            "base_branch",
            "base_sha",
            "feature_branch",
            "instruction_fingerprint",
        }
        if not required.issubset(preview):
            raise TaskExecutionError("persistent task preview metadata is incomplete")
        return dict(preview)

    def _profile_for(self, project: str) -> ProjectExecutionProfile:
        profile = self.profiles.get(project)
        if profile is None:
            raise TaskExecutionError(f"APP3 project profile is not configured: {project}")
        return profile

    @staticmethod
    def _workflow_evidence(
        read_client: Any,
        head_sha: str,
    ) -> tuple[list[dict[str, Any]], str | None]:
        try:
            payload = read_client.workflow_runs(head_sha)
            raw_runs = payload.get("workflow_runs", [])
            if not isinstance(raw_runs, list):
                raise TaskExecutionError("workflow run evidence is invalid")
            return [dict(item) for item in raw_runs if isinstance(item, Mapping)], None
        except (RuntimeError, TypeError, ValueError) as exc:
            return [], _bounded_message(exc)

    @staticmethod
    def _ci_snapshot(
        head_sha: str,
        exact_runs: list[dict[str, Any]],
        profile: ProjectExecutionProfile,
        workflow_error: str | None,
    ) -> dict[str, Any]:
        if workflow_error is not None:
            return _ci_payload(head_sha, "unavailable", [], workflow_error)

        selected = _latest_runs_by_workflow(exact_runs)
        if profile.required_workflows:
            required = set(profile.required_workflows)
            selected = [run for run in selected if run.get("name") in required]
            observed = {run.get("name") for run in selected}
            missing = sorted(required - observed)
            if missing:
                return _ci_payload(
                    head_sha,
                    "pending",
                    selected,
                    f"required workflows not observed yet: {', '.join(missing)}",
                )

        if not selected:
            return _ci_payload(
                head_sha,
                "pending",
                [],
                "no exact-SHA workflow run is available yet",
            )
        if any(run.get("status") != "completed" for run in selected):
            state = "pending"
        elif any(run.get("conclusion") != "success" for run in selected):
            state = "failed"
        else:
            state = "success"
        return _ci_payload(head_sha, state, selected, "exact-SHA workflow evidence reviewed")

    def _validators(
        self,
        preview: Mapping[str, Any],
        commit: Mapping[str, Any],
        head_sha: str,
        *,
        exact_head: bool,
    ) -> list[ValidatorResult]:
        profile = self._profile_for(str(preview["project"]))
        results: list[ValidatorResult] = []
        for name in profile.validator_names:
            if name == "exact_commit_binding":
                results.append(
                    ValidatorResult(
                        name=name,
                        status=ValidatorStatus.PASS if exact_head else ValidatorStatus.FAIL,
                        evidence_reference=f"branch:{preview['feature_branch']}",
                        commit_sha=head_sha,
                        message=(
                            "feature branch still resolves to the bound task HEAD"
                            if exact_head
                            else "feature branch moved away from the bound task HEAD"
                        ),
                    )
                )
                continue
            if name == "bounded_diff_evidence":
                changed_files = commit.get("changed_files")
                available = (
                    isinstance(changed_files, list)
                    and 0 < len(changed_files) <= _MAX_CHANGED_FILES
                )
                results.append(
                    ValidatorResult(
                        name=name,
                        status=(
                            ValidatorStatus.PASS if available else ValidatorStatus.UNAVAILABLE
                        ),
                        evidence_reference=f"compare:{preview['base_sha']}...{head_sha}",
                        commit_sha=head_sha,
                        message=(
                            f"bounded compare evidence contains {len(changed_files)} changed file(s)"
                            if available
                            else "bounded changed-file evidence is unavailable"
                        ),
                    )
                )
                continue
            results.append(
                ValidatorResult(
                    name=name,
                    status=ValidatorStatus.UNAVAILABLE,
                    evidence_reference=f"validator:{name}",
                    commit_sha=head_sha,
                    message="validator is configured but no host adapter is available",
                )
            )
        return results

    @staticmethod
    def _compare(read_client: Any, base_sha: str, head_sha: str) -> dict[str, Any]:
        method = getattr(read_client, "compare_commits", None)
        if not callable(method):
            raise TaskExecutionError("read client does not support exact compare evidence")
        result = method(base_sha, head_sha)
        if not isinstance(result, dict):
            raise TaskExecutionError("compare evidence is invalid")
        if result.get("base_sha") != base_sha or result.get("head_sha") != head_sha:
            raise TaskExecutionError("compare evidence is not bound to the requested commits")
        return result

    def _fail(self, task_id: str, message: str) -> None:
        stage = self.store.current_stage(task_id)
        if stage not in {TaskStage.FAILED, TaskStage.PR_OPENED}:
            try:
                self.store.append_stage(task_id, TaskStage.FAILED, {"message": message[:500]})
            except TaskStateError:
                self.store.append_evidence(task_id, "FAILURE", {"message": message[:500]})
        self.store.append_evidence(
            task_id,
            "OUTCOME",
            {"outcome": TaskOutcome.FAILED.value},
        )


def _latest_runs_by_workflow(runs: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Keep the newest exact-SHA run for each workflow identity; GitHub returns newest first."""
    selected: dict[str, dict[str, Any]] = {}
    for run in runs:
        name = run.get("name")
        identity = str(name) if name is not None else f"id:{run.get('id')}"
        selected.setdefault(identity, run)
    return list(selected.values())


def _ci_payload(
    head_sha: str,
    state: str,
    runs: list[dict[str, Any]],
    message: str,
) -> dict[str, Any]:
    return {
        "head_sha": head_sha,
        "state": state,
        "workflow_names": sorted({str(run.get("name")) for run in runs}),
        "runs": runs,
        "message": message,
    }


def _message_summary(message: Mapping[str, Any]) -> str:
    content = message.get("content")
    if isinstance(content, str):
        return " ".join(content.split())[:1000]
    return "agent completed without a text summary"


def _bounded_message(exc: Exception) -> str:
    return (" ".join(str(exc).split()) or exc.__class__.__name__)[:300]


def _full_sha(value: Any) -> bool:
    return isinstance(value, str) and len(value) == 40 and all(
        char in "0123456789abcdef" for char in value
    )


def _optional_int(value: Any) -> int | None:
    return value if isinstance(value, int) and not isinstance(value, bool) else None
