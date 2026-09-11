from __future__ import annotations

from pathlib import Path

import pytest

from st_music_agent.orchestration_state import (
    OrchestrationStage,
    OrchestrationStateError,
    OrchestrationStateStore,
)


def _through_canonicalization(path: Path) -> OrchestrationStateStore:
    store = OrchestrationStateStore(path, "orch:a24:v1")
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
    store.record_canonical_review(review_fingerprint="b" * 64)
    store.record_canonicalization_receipt(receipt_fingerprint="c" * 64)
    return store


def test_orchestration_records_stability_and_baseline_registry_then_resumes(tmp_path: Path) -> None:
    path = tmp_path / "orchestration-a24.jsonl"
    store = _through_canonicalization(path)

    stability = store.record_post_canonical_stability(report_fingerprint="d" * 64)
    assert stability.stage is OrchestrationStage.POST_CANONICAL_STABILITY_REVIEWED
    assert stability.post_canonical_stability_report_fingerprint == "d" * 64

    final = store.record_baseline_registry(record_fingerprint="e" * 64)
    assert final.stage is OrchestrationStage.BASELINE_REGISTERED
    assert final.canonicalization_receipt_fingerprint == "c" * 64
    assert final.post_canonical_stability_report_fingerprint == "d" * 64
    assert final.baseline_registry_record_fingerprint == "e" * 64

    reopened = OrchestrationStateStore(path, "orch:a24:v1")
    assert reopened.latest() == final


def test_orchestration_cannot_skip_stability_or_replace_baseline_record(tmp_path: Path) -> None:
    path = tmp_path / "orchestration-a24.jsonl"
    store = _through_canonicalization(path)

    with pytest.raises(OrchestrationStateError, match="post_canonical_stability_reviewed"):
        store.record_baseline_registry(record_fingerprint="e" * 64)

    store.record_post_canonical_stability(report_fingerprint="d" * 64)
    store.record_baseline_registry(record_fingerprint="e" * 64)
    with pytest.raises(OrchestrationStateError, match="expected complete"):
        store.record_baseline_registry(record_fingerprint="f" * 64)
