from __future__ import annotations

import json
from pathlib import Path

import pytest

from st_music_agent.journal import JournalIntegrityError
from st_music_agent.orchestration_state import (
    OrchestrationStage,
    OrchestrationStateError,
    OrchestrationStateStore,
)


def _started(path: Path) -> OrchestrationStateStore:
    store = OrchestrationStateStore(path, "orch:restore:v1")
    store.start_plan(plan_id="1" * 64, plan_verification_ref="plan-verification:1")
    return store


def test_orchestration_state_progresses_and_resumes_exact_evidence_chain(tmp_path: Path) -> None:
    path = tmp_path / "orchestration.jsonl"
    store = _started(path)
    store.record_execution(execution_record_id="2" * 64)
    store.attach_learning_evidence(
        experience_record_id="3" * 64,
        evaluation_report_hash="4" * 64,
    )
    store.record_dataset(dataset_manifest_hash="5" * 64)
    store.record_training(
        input_fingerprint="6" * 64,
        completion_fingerprint="7" * 64,
        authorization_ref="host-approval:training:1",
    )
    store.record_model_candidate(candidate_id=f"model:{'8' * 64}")
    store.record_promotion_review(review_fingerprint="9" * 64)
    final = store.record_activation_request(request_fingerprint="a" * 64)

    assert final.stage is OrchestrationStage.ACTIVATION_REQUESTED
    assert final.plan_id == "1" * 64
    assert final.execution_record_id == "2" * 64
    assert final.experience_record_id == "3" * 64
    assert final.evaluation_report_hash == "4" * 64
    assert final.dataset_manifest_hash == "5" * 64
    assert final.training_input_fingerprint == "6" * 64
    assert final.training_completion_fingerprint == "7" * 64
    assert final.model_candidate_id == f"model:{'8' * 64}"
    assert final.promotion_review_fingerprint == "9" * 64
    assert final.activation_request_fingerprint == "a" * 64
    assert len(final.state_fingerprint) == 64

    reopened = OrchestrationStateStore(path, "orch:restore:v1")
    assert reopened.latest() == final


def test_stage_skips_and_restarts_fail_closed(tmp_path: Path) -> None:
    path = tmp_path / "orchestration.jsonl"
    store = _started(path)

    with pytest.raises(OrchestrationStateError, match="expected execution_verified"):
        store.record_dataset(dataset_manifest_hash="5" * 64)
    with pytest.raises(OrchestrationStateError, match="already started"):
        store.start_plan(plan_id="1" * 64, plan_verification_ref="again")


def test_learning_evidence_requires_execution_and_cannot_be_replaced(tmp_path: Path) -> None:
    path = tmp_path / "orchestration.jsonl"
    store = _started(path)

    with pytest.raises(OrchestrationStateError, match="requires verified execution"):
        store.attach_learning_evidence(experience_record_id="3" * 64)

    store.record_execution(execution_record_id="2" * 64)
    store.attach_learning_evidence(experience_record_id="3" * 64)
    with pytest.raises(OrchestrationStateError, match="cannot be replaced"):
        store.attach_learning_evidence(experience_record_id="4" * 64)


def test_reopen_preserves_next_stage_and_allows_continuation(tmp_path: Path) -> None:
    path = tmp_path / "orchestration.jsonl"
    first = _started(path)
    first.record_execution(execution_record_id="2" * 64)

    resumed = OrchestrationStateStore(path, "orch:restore:v1")
    state = resumed.record_dataset(dataset_manifest_hash="5" * 64)
    assert state.stage is OrchestrationStage.DATASET_CURATED
    assert state.execution_record_id == "2" * 64


def test_journal_tampering_is_detected_before_resume(tmp_path: Path) -> None:
    path = tmp_path / "orchestration.jsonl"
    store = _started(path)
    store.record_execution(execution_record_id="2" * 64)

    lines = path.read_text(encoding="utf-8").splitlines()
    second = json.loads(lines[1])
    second["payload"]["execution_record_id"] = "f" * 64
    lines[1] = json.dumps(second, sort_keys=True, separators=(",", ":"))
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")

    with pytest.raises(JournalIntegrityError, match="event hash does not verify"):
        OrchestrationStateStore(path, "orch:restore:v1")


def test_invalid_ids_fail_closed(tmp_path: Path) -> None:
    store = OrchestrationStateStore(tmp_path / "o.jsonl", "orch:restore:v1")
    with pytest.raises(ValueError, match="plan_id"):
        store.start_plan(plan_id="short", plan_verification_ref="plan-verification:1")

    store.start_plan(plan_id="1" * 64, plan_verification_ref="plan-verification:1")
    with pytest.raises(ValueError, match="execution_record_id"):
        store.record_execution(execution_record_id="bad")
