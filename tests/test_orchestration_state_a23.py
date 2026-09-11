from __future__ import annotations

from pathlib import Path

import pytest

from st_music_agent.orchestration_state import (
    OrchestrationStage,
    OrchestrationStateError,
    OrchestrationStateStore,
)


def _through_shadow_health(path: Path) -> OrchestrationStateStore:
    store = OrchestrationStateStore(path, "orch:a23:v1")
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
    store.record_activation_receipt(receipt_fingerprint="9" * 64)
    store.record_shadow_health(report_fingerprint="a" * 64)
    return store


def test_a23_records_canonical_review_and_receipt_then_resumes(tmp_path: Path) -> None:
    path = tmp_path / "orchestration-a23.jsonl"
    store = _through_shadow_health(path)

    review_state = store.record_canonical_review(review_fingerprint="b" * 64)
    assert review_state.stage is OrchestrationStage.CANONICAL_REVIEWED
    assert review_state.canonical_review_fingerprint == "b" * 64

    final = store.record_canonicalization_receipt(receipt_fingerprint="c" * 64)
    assert final.stage is OrchestrationStage.CANONICALIZATION_RECORDED
    assert final.shadow_health_report_fingerprint == "a" * 64
    assert final.canonical_review_fingerprint == "b" * 64
    assert final.canonicalization_receipt_fingerprint == "c" * 64

    reopened = OrchestrationStateStore(path, "orch:a23:v1")
    assert reopened.latest() == final


def test_a23_stage_skips_and_replacements_fail_closed(tmp_path: Path) -> None:
    path = tmp_path / "orchestration-a23.jsonl"
    store = _through_shadow_health(path)

    with pytest.raises(OrchestrationStateError, match="expected canonical_reviewed"):
        store.record_canonicalization_receipt(receipt_fingerprint="c" * 64)

    store.record_canonical_review(review_fingerprint="b" * 64)
    with pytest.raises(OrchestrationStateError, match="expected canonicalization_recorded"):
        store.record_canonical_review(review_fingerprint="d" * 64)
