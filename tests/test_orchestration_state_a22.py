from __future__ import annotations

from pathlib import Path

import pytest

from st_music_agent.orchestration_state import (
    OrchestrationStage,
    OrchestrationStateError,
    OrchestrationStateStore,
)


def _through_activation_request(path: Path) -> OrchestrationStateStore:
    store = OrchestrationStateStore(path, "orch:a22:v1")
    store.start_plan(plan_id="1" * 64, plan_verification_ref="plan-verification:1")
    store.record_execution(execution_record_id="2" * 64)
    store.record_dataset(dataset_manifest_hash="3" * 64)
    store.record_training(
        input_fingerprint="4" * 64,
        completion_fingerprint="5" * 64,
        authorization_ref="host-approval:training:1",
    )
    store.record_model_candidate(candidate_id=f"model:{'6' * 64}")
    store.record_promotion_review(review_fingerprint="7" * 64)
    store.record_activation_request(request_fingerprint="8" * 64)
    return store


def test_orchestration_records_activation_receipt_and_shadow_health_then_resumes(
    tmp_path: Path,
) -> None:
    path = tmp_path / "orchestration-a22.jsonl"
    store = _through_activation_request(path)
    receipt_state = store.record_activation_receipt(receipt_fingerprint="9" * 64)
    assert receipt_state.stage is OrchestrationStage.ACTIVATION_RECORDED
    assert receipt_state.activation_receipt_fingerprint == "9" * 64

    final = store.record_shadow_health(report_fingerprint="a" * 64)
    assert final.stage is OrchestrationStage.SHADOW_HEALTH_REVIEWED
    assert final.activation_request_fingerprint == "8" * 64
    assert final.activation_receipt_fingerprint == "9" * 64
    assert final.shadow_health_report_fingerprint == "a" * 64

    reopened = OrchestrationStateStore(path, "orch:a22:v1")
    assert reopened.latest() == final


def test_orchestration_cannot_skip_activation_receipt_or_replace_runtime_evidence(
    tmp_path: Path,
) -> None:
    path = tmp_path / "orchestration-a22.jsonl"
    store = _through_activation_request(path)

    with pytest.raises(OrchestrationStateError, match="expected activation_recorded"):
        store.record_shadow_health(report_fingerprint="a" * 64)

    store.record_activation_receipt(receipt_fingerprint="9" * 64)
    with pytest.raises(OrchestrationStateError, match="expected shadow_health_reviewed"):
        store.record_activation_receipt(receipt_fingerprint="b" * 64)
