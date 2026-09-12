from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import pytest

from st_music_agent.app4_task_execution import App4TaskService
from st_music_agent.policy import AutonomyDecision
from st_music_agent.task_execution import TaskExecutionConfig, TaskExecutionError
from st_music_agent.task_state import TaskEventStore, TaskStage
from st_music_agent.tools import ActionApproval, ActionResult

BASE = "a" * 40
HEAD = "b" * 40
TASK_ID = "task:" + "1" * 64
BRANCH = "st-agent/score_restore/review-test"


@dataclass
class FakeState:
    base_sha: str = BASE
    head_sha: str = HEAD
    branch: str = BRANCH
    review_complete: bool = True
    prs: list[dict[str, Any]] = field(default_factory=list)


class FakeReadClient:
    def __init__(self, state: FakeState) -> None:
        self.state = state

    def branch_info(self, branch: str) -> dict[str, Any]:
        if branch == "main":
            return {"name": "main", "protected": True, "commit_sha": self.state.base_sha}
        if branch == self.state.branch:
            return {"name": branch, "protected": False, "commit_sha": self.state.head_sha}
        if branch.startswith("st-agent/score_restore/"):
            return {"name": branch, "protected": False, "commit_sha": self.state.base_sha}
        raise RuntimeError("branch not found")

    def review_compare(self, base_sha: str, head_sha: str) -> dict[str, Any]:
        return {
            "schema_version": "1.0.0",
            "base_sha": base_sha,
            "head_sha": head_sha,
            "status": "ahead",
            "ahead_by": 1,
            "behind_by": 0,
            "total_commits": 1,
            "complete": self.state.review_complete,
            "files": [
                {
                    "path": "README.md",
                    "status": "modified",
                    "additions": 1,
                    "deletions": 1,
                    "changes": 2,
                    "patch": "@@ -1 +1 @@\n-before\n+after",
                    "patch_sha256": "c" * 64,
                    "patch_available": True,
                    "patch_truncated": not self.state.review_complete,
                    "attention": "normal" if self.state.review_complete else "incomplete",
                }
            ],
        }

    def pull_request(self, number: int) -> dict[str, Any]:
        return {
            "number": number,
            "title": "APP4 task",
            "state": "open",
            "draft": False,
            "mergeable": True,
            "head_ref": self.state.branch,
            "head_sha": self.state.head_sha,
            "base_ref": "main",
            "base_sha": self.state.base_sha,
        }


class FakeMutationClient:
    def __init__(self, state: FakeState) -> None:
        self.state = state

    def open_pull_request(
        self,
        *,
        title: str,
        head: str,
        base: str,
        body: str = "",
        approval: ActionApproval | None = None,
    ) -> ActionResult:
        assert approval == ActionApproval("github.open_pull_request", f"{head}->{base}")
        self.state.prs.append({"title": title, "head": head, "base": base, "body": body})
        return ActionResult(
            decision=AutonomyDecision.REQUIRE_HUMAN,
            executed=True,
            value={"number": 41, "state": "open", "html_url": "https://example.invalid/pr/41"},
        )

    def create_branch(self, branch: str, base_sha: str, approval=None):  # pragma: no cover
        raise AssertionError("revision preview must not create a branch")

    def write_file(self, **kwargs):  # pragma: no cover
        raise AssertionError("review tests must not write files")


def _config() -> TaskExecutionConfig:
    return TaskExecutionConfig(
        enabled=True,
        provider_base_url="https://provider.invalid/v1",
        provider_model="test-model",
        provider_api_key_env="TEST_PROVIDER_KEY",
    )


def _service(tmp_path, state: FakeState) -> App4TaskService:
    read = FakeReadClient(state)
    mutation = FakeMutationClient(state)
    return App4TaskService(
        _config(),
        state_path=tmp_path / "events.jsonl",
        read_factory=lambda repository: read,
        mutation_factory=lambda repository: mutation,
    )


def _seed_verified(store: TaskEventStore) -> None:
    store.append_stage(
        TASK_ID,
        TaskStage.PREVIEWED,
        {
            "project": "score_restore",
            "repository": "owner/repo",
            "base_branch": "main",
            "base_sha": BASE,
            "feature_branch": BRANCH,
            "instruction_fingerprint": "d" * 64,
            "policy": {
                "create_branch": "auto_execute",
                "write_file": "auto_execute",
                "open_pull_request": "require_human",
            },
        },
    )
    store.append_stage(TASK_ID, TaskStage.BRANCH_CREATED, {"feature_branch": BRANCH})
    store.append_stage(TASK_ID, TaskStage.AGENT_RUNNING, {"feature_branch": BRANCH})
    store.append_stage(
        TASK_ID,
        TaskStage.AGENT_COMPLETED,
        {"model_name": "GLM-5.1", "turns": 2, "tool_calls": 1, "summary": "done"},
    )
    store.append_stage(
        TASK_ID,
        TaskStage.COMMIT_BOUND,
        {
            "base_sha": BASE,
            "head_sha": HEAD,
            "feature_branch": BRANCH,
            "changed_files": [{"path": "README.md", "changes": 2}],
        },
    )
    store.append_stage(TASK_ID, TaskStage.CI_PENDING, {"head_sha": HEAD})
    store.append_stage(TASK_ID, TaskStage.CI_REVIEWED, {"head_sha": HEAD})
    store.append_stage(TASK_ID, TaskStage.VALIDATORS_REVIEWED, {"head_sha": HEAD})
    store.append_stage(TASK_ID, TaskStage.VERIFIED_SUCCESS, {"head_sha": HEAD})
    store.append_evidence(TASK_ID, "OUTCOME", {"outcome": "VERIFIED_SUCCESS"})


def test_pr_requires_exact_review_acknowledgement(tmp_path) -> None:
    state = FakeState()
    service = _service(tmp_path, state)
    _seed_verified(service.store)

    review = service.review_bundle(TASK_ID)

    assert review["complete"] is True
    assert len(review["review_digest"]) == 64
    with pytest.raises(TaskExecutionError, match="acknowledgement"):
        service.open_pull_request(TASK_ID)

    status = service.acknowledge_review(TASK_ID, review["review_digest"])
    assert status["review_ready_for_pr"] is True

    pr = service.open_pull_request(TASK_ID)
    final = service.status(TASK_ID)

    assert pr["number"] == 41
    assert final["stage"] == "PR_OPENED"
    assert final["pr_review"]["review_digest"] == review["review_digest"]
    assert final["pr_review"]["exact_head_match"] is True
    assert final["merge_authorized"] is False


def test_incomplete_review_cannot_be_acknowledged(tmp_path) -> None:
    state = FakeState(review_complete=False)
    service = _service(tmp_path, state)
    _seed_verified(service.store)

    review = service.review_bundle(TASK_ID)

    assert review["complete"] is False
    with pytest.raises(TaskExecutionError, match="incomplete or truncated"):
        service.acknowledge_review(TASK_ID, review["review_digest"])


def test_branch_move_invalidates_review(tmp_path) -> None:
    state = FakeState()
    service = _service(tmp_path, state)
    _seed_verified(service.store)
    service.review_bundle(TASK_ID)
    state.head_sha = "e" * 40

    with pytest.raises(TaskExecutionError, match="moved"):
        service.review_bundle(TASK_ID)


def test_retry_creates_distinct_child_and_preserves_parent(tmp_path) -> None:
    state = FakeState(base_sha=BASE, head_sha=BASE)
    service = _service(tmp_path, state)
    parent = "task:" + "2" * 64
    service.store.append_stage(
        parent,
        TaskStage.PREVIEWED,
        {
            "project": "score_restore",
            "repository": "owner/repo",
            "base_branch": "main",
            "base_sha": BASE,
            "feature_branch": "st-agent/score_restore/failed-parent",
            "instruction_fingerprint": "f" * 64,
            "policy": {},
        },
    )
    service.store.append_stage(parent, TaskStage.FAILED, {"message": "provider failed"})

    revision = service.create_revision(
        parent,
        "Retry the bounded README correction without changing any other file.",
        mode="retry",
    )
    child_id = revision["child"]["task_id"]
    parent_status = service.status(parent)
    child_status = service.status(child_id)

    assert child_id != parent
    assert parent_status["stage"] == "FAILED"
    assert parent_status["lineage"]["children"][0]["child_task_id"] == child_id
    assert child_status["lineage"]["parent"]["parent_task_id"] == parent
    assert child_status["stage"] == "PREVIEWED"


def test_amend_requires_parent_commit(tmp_path) -> None:
    service = _service(tmp_path, FakeState())
    parent = "task:" + "3" * 64
    service.store.append_stage(
        parent,
        TaskStage.PREVIEWED,
        {
            "project": "score_restore",
            "repository": "owner/repo",
            "base_branch": "main",
            "base_sha": BASE,
            "feature_branch": "st-agent/score_restore/no-commit",
            "instruction_fingerprint": "f" * 64,
            "policy": {},
        },
    )

    with pytest.raises(TaskExecutionError, match="exact parent commit"):
        service.create_revision(parent, "Amend the result", mode="amend")
