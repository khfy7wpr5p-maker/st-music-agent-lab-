from __future__ import annotations

import hashlib
import json

import pytest

from st_music_agent.baseline_registry import (
    BASELINE_REGISTRY_SCHEMA_VERSION,
    BaselineRecord,
    BaselineRecordKind,
)
from st_music_agent.drift_watch import (
    DriftCheck,
    DriftCheckKind,
    DriftCheckStatus,
    DriftObservationWindow,
    DriftWatchGate,
    RollbackReviewRequestBuilder,
)
from st_music_agent.operational_watch import (
    OperationalWatchStage,
    OperationalWatchStateError,
    OperationalWatchStateStore,
)


def _hash(value: object) -> str:
    return hashlib.sha256(
        json.dumps(
            value,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        ).encode("utf-8")
    ).hexdigest()


def _baseline(*, model_char: str = "1", checkpoint_char: str = "a") -> BaselineRecord:
    base = {
        "schema_version": BASELINE_REGISTRY_SCHEMA_VERSION,
        "generation": 2,
        "environment": "production",
        "record_kind": "canonicalization",
        "model_id": "model:" + model_char * 64,
        "checkpoint_sha256": checkpoint_char * 64,
        "previous_model_id": "model:" + "2" * 64,
        "previous_checkpoint_sha256": "b" * 64,
        "rollback_model_id": "model:" + "2" * 64,
        "rollback_checkpoint_sha256": "b" * 64,
        "canonicalization_receipt_fingerprint": "c" * 64,
        "stability_report_fingerprint": "d" * 64,
        "host_registration_ref": "host:baseline:2",
        "evidence_refs": ["evidence:baseline"],
        "auto_switch": False,
        "auto_rollback": False,
    }
    return BaselineRecord(
        generation=2,
        environment="production",
        record_kind=BaselineRecordKind.CANONICALIZATION,
        model_id=base["model_id"],
        checkpoint_sha256=base["checkpoint_sha256"],
        previous_model_id=base["previous_model_id"],
        previous_checkpoint_sha256=base["previous_checkpoint_sha256"],
        rollback_model_id=base["rollback_model_id"],
        rollback_checkpoint_sha256=base["rollback_checkpoint_sha256"],
        canonicalization_receipt_fingerprint=base["canonicalization_receipt_fingerprint"],
        stability_report_fingerprint=base["stability_report_fingerprint"],
        host_registration_ref="host:baseline:2",
        evidence_refs=("evidence:baseline",),
        record_fingerprint=_hash(base),
    )


def _window(index: int, *, degraded: bool = False) -> DriftObservationWindow:
    baseline = _baseline()
    quality = DriftCheckStatus.DEGRADED if degraded else DriftCheckStatus.STABLE
    return DriftObservationWindow(
        window_id=f"window-{index}",
        checks=(
            DriftCheck(
                DriftCheckKind.SERVING_IDENTITY,
                DriftCheckStatus.STABLE,
                (f"evidence:{index}:identity",),
                observed_model_id=baseline.model_id,
                observed_checkpoint_sha256=baseline.checkpoint_sha256,
            ),
            DriftCheck(DriftCheckKind.HEALTH, DriftCheckStatus.STABLE, (f"e:{index}:h",)),
            DriftCheck(DriftCheckKind.QUALITY, quality, (f"e:{index}:q",)),
            DriftCheck(
                DriftCheckKind.DISTRIBUTION,
                DriftCheckStatus.STABLE,
                (f"e:{index}:d",),
            ),
            DriftCheck(
                DriftCheckKind.ROLLBACK_READINESS,
                DriftCheckStatus.STABLE,
                (f"e:{index}:r",),
            ),
        ),
    )


def _eligible_evidence():
    baseline = _baseline()
    windows = (_window(0), _window(1), _window(2, degraded=True), _window(3, degraded=True))
    report = DriftWatchGate().evaluate(baseline, windows)
    request = RollbackReviewRequestBuilder().build(
        baseline,
        windows,
        report,
        evidence_refs=("evidence:rollback-review",),
    )
    return baseline, windows, report, request


def test_operational_watch_resumes_through_rollback_review_request(tmp_path) -> None:
    baseline, windows, report, request = _eligible_evidence()
    path = tmp_path / "watch.jsonl"
    store = OperationalWatchStateStore(path, "watch-001")
    bound = store.bind_baseline(baseline)
    assert bound.stage is OperationalWatchStage.BASELINE_BOUND
    reviewed = store.record_drift_review(baseline, windows, report)
    assert reviewed.stage is OperationalWatchStage.DRIFT_REVIEWED

    reopened = OperationalWatchStateStore(path, "watch-001")
    assert reopened.latest() == reviewed
    requested = reopened.record_rollback_review_request(baseline, windows, report, request)
    assert requested.stage is OperationalWatchStage.ROLLBACK_REVIEW_REQUESTED
    assert requested.rollback_review_request_fingerprint == request.request_fingerprint


def test_healthy_watch_can_stop_after_drift_review(tmp_path) -> None:
    baseline = _baseline()
    windows = tuple(_window(i) for i in range(4))
    report = DriftWatchGate().evaluate(baseline, windows)
    store = OperationalWatchStateStore(tmp_path / "healthy.jsonl", "watch-healthy")
    store.bind_baseline(baseline)
    state = store.record_drift_review(baseline, windows, report)
    assert state.stage is OperationalWatchStage.DRIFT_REVIEWED
    assert state.rollback_review_request_fingerprint is None


def test_operational_watch_rejects_stage_skip(tmp_path) -> None:
    baseline, windows, report, request = _eligible_evidence()
    store = OperationalWatchStateStore(tmp_path / "skip.jsonl", "watch-skip")
    store.bind_baseline(baseline)
    with pytest.raises(OperationalWatchStateError, match="expected drift_reviewed"):
        store.record_rollback_review_request(baseline, windows, report, request)


def test_operational_watch_rejects_baseline_replacement(tmp_path) -> None:
    baseline, windows, report, _request = _eligible_evidence()
    store = OperationalWatchStateStore(tmp_path / "replace.jsonl", "watch-replace")
    store.bind_baseline(baseline)
    changed = _baseline(model_char="9", checkpoint_char="e")
    with pytest.raises(OperationalWatchStateError, match="baseline record changed"):
        store.record_drift_review(changed, windows, report)
