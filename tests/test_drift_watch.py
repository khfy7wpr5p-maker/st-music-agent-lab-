from __future__ import annotations

import hashlib
import json
from dataclasses import replace

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
    DriftWatchDecision,
    DriftWatchError,
    DriftWatchGate,
    RollbackReviewDecision,
    RollbackReviewRequestBuilder,
)


def _hash(value: object) -> str:
    encoded = json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _baseline(*, rollback: bool = True) -> BaselineRecord:
    model_id = "model:" + "1" * 64
    checkpoint = "a" * 64
    previous_id = "model:" + "2" * 64 if rollback else None
    previous_checkpoint = "b" * 64 if rollback else None
    kind = BaselineRecordKind.CANONICALIZATION if rollback else BaselineRecordKind.BOOTSTRAP
    base = {
        "schema_version": BASELINE_REGISTRY_SCHEMA_VERSION,
        "generation": 2 if rollback else 1,
        "environment": "production",
        "record_kind": kind.value,
        "model_id": model_id,
        "checkpoint_sha256": checkpoint,
        "previous_model_id": previous_id,
        "previous_checkpoint_sha256": previous_checkpoint,
        "rollback_model_id": previous_id,
        "rollback_checkpoint_sha256": previous_checkpoint,
        "canonicalization_receipt_fingerprint": "c" * 64 if rollback else None,
        "stability_report_fingerprint": "d" * 64 if rollback else None,
        "host_registration_ref": "host:baseline:2",
        "evidence_refs": ["evidence:baseline"],
        "auto_switch": False,
        "auto_rollback": False,
    }
    return BaselineRecord(
        generation=base["generation"],
        environment="production",
        record_kind=kind,
        model_id=model_id,
        checkpoint_sha256=checkpoint,
        previous_model_id=previous_id,
        previous_checkpoint_sha256=previous_checkpoint,
        rollback_model_id=previous_id,
        rollback_checkpoint_sha256=previous_checkpoint,
        canonicalization_receipt_fingerprint=base["canonicalization_receipt_fingerprint"],
        stability_report_fingerprint=base["stability_report_fingerprint"],
        host_registration_ref="host:baseline:2",
        evidence_refs=("evidence:baseline",),
        record_fingerprint=_hash(base),
    )


def _window(
    index: int,
    *,
    health: DriftCheckStatus = DriftCheckStatus.STABLE,
    quality: DriftCheckStatus = DriftCheckStatus.STABLE,
    distribution: DriftCheckStatus = DriftCheckStatus.STABLE,
    readiness: DriftCheckStatus = DriftCheckStatus.STABLE,
    model_id: str | None = None,
) -> DriftObservationWindow:
    baseline = _baseline()
    observed_model = model_id or baseline.model_id
    return DriftObservationWindow(
        window_id=f"window-{index}",
        checks=(
            DriftCheck(
                DriftCheckKind.SERVING_IDENTITY,
                DriftCheckStatus.STABLE,
                (f"evidence:{index}:identity",),
                observed_model_id=observed_model,
                observed_checkpoint_sha256=baseline.checkpoint_sha256,
            ),
            DriftCheck(
                DriftCheckKind.HEALTH,
                health,
                (f"evidence:{index}:health",),
            ),
            DriftCheck(
                DriftCheckKind.QUALITY,
                quality,
                (f"evidence:{index}:quality",),
            ),
            DriftCheck(
                DriftCheckKind.DISTRIBUTION,
                distribution,
                (f"evidence:{index}:distribution",),
            ),
            DriftCheck(
                DriftCheckKind.ROLLBACK_READINESS,
                readiness,
                (f"evidence:{index}:rollback",),
            ),
        ),
    )


def test_healthy_baseline_remains_healthy() -> None:
    report = DriftWatchGate().evaluate(_baseline(), tuple(_window(i) for i in range(4)))
    assert report.decision is DriftWatchDecision.HEALTHY
    assert report.degraded_window_count == 0
    assert report.rollback_authorized is False
    assert report.auto_rollback is False


def test_two_consecutive_latest_degraded_windows_open_review_only() -> None:
    windows = (
        _window(0),
        _window(1),
        _window(2, quality=DriftCheckStatus.DEGRADED),
        _window(3, quality=DriftCheckStatus.DEGRADED),
    )
    report = DriftWatchGate().evaluate(_baseline(), windows)
    assert report.decision is DriftWatchDecision.ELIGIBLE_FOR_ROLLBACK_REVIEW
    assert report.max_consecutive_degraded_windows == 2
    assert report.latest_window_degraded is True
    assert report.rollback_authorized is False


def test_one_degraded_window_is_observe_not_rollback_review() -> None:
    windows = (
        _window(0),
        _window(1),
        _window(2),
        _window(3, quality=DriftCheckStatus.DEGRADED),
    )
    report = DriftWatchGate().evaluate(_baseline(), windows)
    assert report.decision is DriftWatchDecision.OBSERVE


def test_unavailable_evidence_stays_observe() -> None:
    windows = (
        _window(0),
        _window(1),
        _window(2, quality=DriftCheckStatus.DEGRADED),
        _window(3, distribution=DriftCheckStatus.UNAVAILABLE),
    )
    report = DriftWatchGate().evaluate(_baseline(), windows)
    assert report.decision is DriftWatchDecision.OBSERVE


def test_unstable_rollback_readiness_blocks_rollback_review() -> None:
    windows = (
        _window(0),
        _window(1, readiness=DriftCheckStatus.DEGRADED),
        _window(2, quality=DriftCheckStatus.DEGRADED),
        _window(3, quality=DriftCheckStatus.DEGRADED),
    )
    report = DriftWatchGate().evaluate(_baseline(), windows)
    assert report.decision is DriftWatchDecision.OBSERVE


def test_wrong_serving_identity_fails_closed() -> None:
    windows = tuple(_window(i) for i in range(3)) + (
        _window(3, model_id="model:" + "9" * 64),
    )
    with pytest.raises(DriftWatchError, match="serving identity"):
        DriftWatchGate().evaluate(_baseline(), windows)


def test_baseline_without_predecessor_cannot_open_rollback_review() -> None:
    windows = (
        _window(0),
        _window(1),
        _window(2, health=DriftCheckStatus.DEGRADED),
        _window(3, health=DriftCheckStatus.DEGRADED),
    )
    report = DriftWatchGate().evaluate(_baseline(rollback=False), windows)
    assert report.decision is DriftWatchDecision.OBSERVE


def test_forged_drift_report_is_rejected() -> None:
    baseline = _baseline()
    windows = tuple(_window(i) for i in range(4))
    report = DriftWatchGate().evaluate(baseline, windows)
    forged = replace(report, decision=DriftWatchDecision.ELIGIBLE_FOR_ROLLBACK_REVIEW)
    with pytest.raises(DriftWatchError, match="recomputation"):
        DriftWatchGate().verify(baseline, windows, forged)


def test_rollback_review_request_binds_exact_previous_baseline() -> None:
    baseline = _baseline()
    windows = (
        _window(0),
        _window(1),
        _window(2, quality=DriftCheckStatus.DEGRADED),
        _window(3, quality=DriftCheckStatus.FAILED),
    )
    report = DriftWatchGate().evaluate(baseline, windows)
    request = RollbackReviewRequestBuilder().build(
        baseline,
        windows,
        report,
        evidence_refs=("evidence:rollback-review",),
    )
    assert request.decision is RollbackReviewDecision.ELIGIBLE_FOR_HOST_ROLLBACK_REVIEW
    assert request.current_model_id == baseline.model_id
    assert request.rollback_model_id == baseline.previous_model_id
    assert request.rollback_checkpoint_sha256 == baseline.previous_checkpoint_sha256
    assert request.human_approval_required is True
    assert request.rollback_authorized is False
    assert request.auto_rollback is False
    RollbackReviewRequestBuilder().verify_with_evidence(baseline, windows, report, request)


def test_healthy_report_cannot_create_rollback_request() -> None:
    baseline = _baseline()
    windows = tuple(_window(i) for i in range(4))
    report = DriftWatchGate().evaluate(baseline, windows)
    with pytest.raises(DriftWatchError, match="not eligible"):
        RollbackReviewRequestBuilder().build(
            baseline,
            windows,
            report,
            evidence_refs=("evidence:rollback-review",),
        )


def test_rollback_request_cannot_self_authorize() -> None:
    baseline = _baseline()
    windows = (
        _window(0),
        _window(1),
        _window(2, quality=DriftCheckStatus.DEGRADED),
        _window(3, quality=DriftCheckStatus.DEGRADED),
    )
    report = DriftWatchGate().evaluate(baseline, windows)
    request = RollbackReviewRequestBuilder().build(
        baseline,
        windows,
        report,
        evidence_refs=("evidence:rollback-review",),
    )
    forged = replace(request, rollback_authorized=True)
    with pytest.raises(DriftWatchError, match="cannot authorize rollback"):
        RollbackReviewRequestBuilder.verify_record(forged)
