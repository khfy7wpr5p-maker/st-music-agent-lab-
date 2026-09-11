from __future__ import annotations

import json

import pytest

from st_music_agent.task_state import (
    TaskEventStore,
    TaskOutcome,
    TaskStage,
    TaskStateError,
    ValidatorResult,
    ValidatorStatus,
)


def _preview() -> dict[str, object]:
    return {
        "project": "score_restore",
        "repository": "owner/repo",
        "base_branch": "main",
        "base_sha": "a" * 40,
        "feature_branch": "st-agent/score_restore/example",
        "instruction_fingerprint": "b" * 64,
        "policy": {
            "create_branch": "auto_execute",
            "write_file": "auto_execute",
            "open_pull_request": "require_human",
        },
    }


def test_task_state_persists_and_reopens_without_replacing_history(tmp_path) -> None:
    path = tmp_path / "task-events.jsonl"
    task_id = "task:" + "c" * 64
    store = TaskEventStore(path)
    store.append_stage(task_id, TaskStage.PREVIEWED, _preview())
    store.append_stage(
        task_id,
        TaskStage.BRANCH_CREATED,
        {"feature_branch": "st-agent/score_restore/example", "base_sha": "a" * 40},
    )
    store.append_stage(
        task_id,
        TaskStage.AGENT_RUNNING,
        {"feature_branch": "st-agent/score_restore/example"},
    )
    store.append_evidence(task_id, "RESUME_REQUESTED", {"reason": "process restart"})

    reopened = TaskEventStore(path)

    assert reopened.current_stage(task_id) is TaskStage.AGENT_RUNNING
    assert len(reopened.task_events(task_id)) == 4
    assert reopened.task_view(task_id)["preview"]["repository"] == "owner/repo"


def test_task_state_rejects_stage_skipping_and_terminal_rewrite(tmp_path) -> None:
    store = TaskEventStore(tmp_path / "task-events.jsonl")
    task_id = "task:" + "d" * 64
    store.append_stage(task_id, TaskStage.PREVIEWED, _preview())

    with pytest.raises(TaskStateError, match="invalid task stage transition"):
        store.append_stage(task_id, TaskStage.AGENT_RUNNING, {})

    store.append_stage(task_id, TaskStage.FAILED, {"message": "failed"})
    with pytest.raises(TaskStateError, match="invalid task stage transition"):
        store.append_stage(task_id, TaskStage.VERIFIED_SUCCESS, {"head_sha": "e" * 40})


def test_task_state_hash_chain_detects_tampering(tmp_path) -> None:
    path = tmp_path / "task-events.jsonl"
    task_id = "task:" + "f" * 64
    store = TaskEventStore(path)
    store.append_stage(task_id, TaskStage.PREVIEWED, _preview())

    item = json.loads(path.read_text(encoding="utf-8"))
    item["payload"]["repository"] = "attacker/changed"
    path.write_text(json.dumps(item) + "\n", encoding="utf-8")

    with pytest.raises(TaskStateError, match="hash does not match"):
        TaskEventStore(path)


def test_validator_contract_keeps_unavailable_distinct_from_pass() -> None:
    result = ValidatorResult(
        name="project_validator",
        status=ValidatorStatus.UNAVAILABLE,
        evidence_reference="validator:project_validator",
        commit_sha="a" * 40,
        message="adapter not configured",
    )

    assert result.as_dict()["status"] == "UNAVAILABLE"
    assert result.status is not ValidatorStatus.PASS
    assert TaskOutcome.REVIEW_REQUIRED.value == "REVIEW_REQUIRED"
