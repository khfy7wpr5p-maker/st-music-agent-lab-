from __future__ import annotations

import hashlib
import json
from dataclasses import replace
from pathlib import Path

import pytest

from st_music_agent.baseline_registry import (
    BASELINE_REGISTRY_SCHEMA_VERSION,
    BaselineRecord,
    BaselineRecordKind,
    BaselineRegistry,
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
from st_music_agent.rollback_recovery import (
    POST_ROLLBACK_MIN_ROUNDS,
    PostRollbackRecoveryDecision,
    PostRollbackRecoveryGate,
    PostRollbackRecoveryRound,
    RecoveryCheck,
    RecoveryCheckKind,
    RecoveryCheckStatus,
    RollbackExecutionOutcome,
    RollbackExecutionReceiptBuilder,
    RollbackRecoveryError,
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


def _current_baseline() -> BaselineRecord:
    model_id = "model:" + "1" * 64
    checkpoint = "a" * 64
    previous_id = "model:" + "2" * 64
    previous_checkpoint = "b" * 64
    base = {
        "schema_version": BASELINE_REGISTRY_SCHEMA_VERSION,
        "generation": 2,
        "environment": "production",
        "record_kind": BaselineRecordKind.CANONICALIZATION.value,
        "model_id": model_id,
        "checkpoint_sha256": checkpoint,
        "previous_model_id": previous_id,
        "previous_checkpoint_sha256": previous_checkpoint,
        "rollback_model_id": previous_id,
        "rollback_checkpoint_sha256": previous_checkpoint,
        "canonicalization_receipt_fingerprint": "c" * 64,
        "stability_report_fingerprint": "d" * 64,
        "host_registration_ref": "host:canonical:2",
        "evidence_refs": ["evidence:canonical:2"],
        "auto_switch": False,
        "auto_rollback": False,
    }
    return BaselineRecord(
        generation=2,
        environment="production",
        record_kind=BaselineRecordKind.CANONICALIZATION,
        model_id=model_id,
        checkpoint_sha256=checkpoint,
        previous_model_id=previous_id,
        previous_checkpoint_sha256=previous_checkpoint,
        rollback_model_id=previous_id,
        rollback_checkpoint_sha256=previous_checkpoint,
        canonicalization_receipt_fingerprint="c" * 64,
        stability_report_fingerprint="d" * 64,
        host_registration_ref="host:canonical:2",
        evidence_refs=("evidence:canonical:2",),
        record_fingerprint=_hash(base),
    )


def _windows(baseline: BaselineRecord) -> tuple[DriftObservationWindow, ...]:
    result: list[DriftObservationWindow] = []
    for index in range(4):
        quality = DriftCheckStatus.DEGRADED if index >= 2 else DriftCheckStatus.STABLE
        result.append(
            DriftObservationWindow(
                window_id=f"window-{index + 1}",
                checks=(
                    DriftCheck(
                        DriftCheckKind.SERVING_IDENTITY,
                        DriftCheckStatus.STABLE,
                        (f"e:{index}:identity",),
                        observed_model_id=baseline.model_id,
                        observed_checkpoint_sha256=baseline.checkpoint_sha256,
                    ),
                    DriftCheck(
                        DriftCheckKind.HEALTH,
                        DriftCheckStatus.STABLE,
                        (f"e:{index}:health",),
                    ),
                    DriftCheck(
                        DriftCheckKind.QUALITY,
                        quality,
                        (f"e:{index}:quality",),
                    ),
                    DriftCheck(
                        DriftCheckKind.DISTRIBUTION,
                        DriftCheckStatus.STABLE,
                        (f"e:{index}:distribution",),
                    ),
                    DriftCheck(
                        DriftCheckKind.ROLLBACK_READINESS,
                        DriftCheckStatus.STABLE,
                        (f"e:{index}:rollback",),
                    ),
                ),
            )
        )
    return tuple(result)


def _rollback_evidence():
    baseline = _current_baseline()
    windows = _windows(baseline)
    drift_report = DriftWatchGate().evaluate(baseline, windows)
    request = RollbackReviewRequestBuilder().build(
        baseline,
        windows,
        drift_report,
        evidence_refs=("evidence:rollback-review",),
    )
    receipt = RollbackExecutionReceiptBuilder().bind(
        baseline,
        windows,
        drift_report,
        request,
        outcome=RollbackExecutionOutcome.ROLLED_BACK,
        host_authorization_ref="host:rollback:approval:1",
        execution_ref="runtime:rollback:1",
        evidence_refs=("runtime:rollback-log:1",),
        observed_model_id=request.rollback_model_id,
        observed_checkpoint_sha256=request.rollback_checkpoint_sha256,
    )
    return baseline, windows, drift_report, request, receipt


def _recovery_rounds(receipt) -> tuple[PostRollbackRecoveryRound, ...]:
    rounds: list[PostRollbackRecoveryRound] = []
    for sequence in range(1, POST_ROLLBACK_MIN_ROUNDS + 1):
        rounds.append(
            PostRollbackRecoveryRound(
                sequence=sequence,
                observation_ref=f"recovery:{sequence}",
                checks=(
                    RecoveryCheck(
                        RecoveryCheckKind.SERVING_IDENTITY,
                        RecoveryCheckStatus.SUCCESS,
                        (f"e:recovery:{sequence}:identity",),
                        observed_model_id=receipt.to_model_id,
                        observed_checkpoint_sha256=receipt.to_checkpoint_sha256,
                    ),
                    RecoveryCheck(
                        RecoveryCheckKind.HEALTH,
                        RecoveryCheckStatus.SUCCESS,
                        (f"e:recovery:{sequence}:health",),
                    ),
                    RecoveryCheck(
                        RecoveryCheckKind.RECOVERY,
                        RecoveryCheckStatus.SUCCESS,
                        (f"e:recovery:{sequence}:quality",),
                    ),
                ),
            )
        )
    return tuple(rounds)


def test_successful_rollback_receipt_is_evidence_only() -> None:
    baseline, windows, drift_report, request, receipt = _rollback_evidence()
    RollbackExecutionReceiptBuilder().verify_with_evidence(
        baseline,
        windows,
        drift_report,
        request,
        receipt,
    )
    assert receipt.outcome is RollbackExecutionOutcome.ROLLED_BACK
    assert receipt.to_model_id == baseline.previous_model_id
    assert receipt.post_rollback_recovery_required is True
    assert receipt.auto_rollback is False
    assert receipt.auto_switch is False


def test_rollback_receipt_rejects_wrong_target_and_tampering() -> None:
    baseline = _current_baseline()
    windows = _windows(baseline)
    drift_report = DriftWatchGate().evaluate(baseline, windows)
    request = RollbackReviewRequestBuilder().build(
        baseline,
        windows,
        drift_report,
        evidence_refs=("evidence:rollback-review",),
    )
    with pytest.raises(RollbackRecoveryError, match="approved target"):
        RollbackExecutionReceiptBuilder().bind(
            baseline,
            windows,
            drift_report,
            request,
            outcome=RollbackExecutionOutcome.ROLLED_BACK,
            host_authorization_ref="host:rollback:approval:1",
            execution_ref="runtime:rollback:1",
            evidence_refs=("runtime:rollback-log:1",),
            observed_model_id="model:" + "9" * 64,
            observed_checkpoint_sha256=request.rollback_checkpoint_sha256,
        )

    receipt = _rollback_evidence()[-1]
    with pytest.raises(RollbackRecoveryError, match="fingerprint"):
        RollbackExecutionReceiptBuilder.verify_record(
            replace(receipt, receipt_fingerprint="0" * 64)
        )


def test_recovery_requires_repeated_success_and_exact_identity() -> None:
    receipt = _rollback_evidence()[-1]
    rounds = _recovery_rounds(receipt)
    gate = PostRollbackRecoveryGate()
    report = gate.evaluate(receipt, rounds)
    assert report.decision is PostRollbackRecoveryDecision.ELIGIBLE_FOR_BASELINE_REGISTRATION
    assert report.observation_round_count == POST_ROLLBACK_MIN_ROUNDS
    assert report.auto_register_baseline is False
    assert report.auto_switch is False
    assert report.auto_rollback is False
    gate.verify(receipt, rounds, report)

    with pytest.raises(RollbackRecoveryError, match="at least"):
        gate.evaluate(receipt, rounds[:-1])

    failed_rounds = list(rounds)
    checks = list(failed_rounds[0].checks)
    checks[1] = replace(checks[1], status=RecoveryCheckStatus.UNAVAILABLE)
    failed_rounds[0] = replace(failed_rounds[0], checks=tuple(checks))
    rejected = gate.evaluate(receipt, tuple(failed_rounds))
    assert rejected.decision is PostRollbackRecoveryDecision.REJECTED

    wrong_rounds = list(rounds)
    wrong_checks = list(wrong_rounds[0].checks)
    wrong_checks[0] = replace(wrong_checks[0], observed_model_id="model:" + "8" * 64)
    wrong_rounds[0] = replace(wrong_rounds[0], checks=tuple(wrong_checks))
    with pytest.raises(RollbackRecoveryError, match="rollback target"):
        gate.evaluate(receipt, tuple(wrong_rounds))


def _registry_with_current(path: Path) -> BaselineRegistry:
    baseline = _current_baseline()
    registry = BaselineRegistry(path, "production")
    bootstrap = registry.bootstrap(
        model_id=baseline.previous_model_id or "",
        checkpoint_sha256=baseline.previous_checkpoint_sha256 or "",
        host_registration_ref="host:bootstrap:1",
        evidence_refs=("evidence:bootstrap",),
    )
    assert bootstrap.generation == 1
    registry.journal.append("baseline_registry_record", baseline.as_dict())
    return BaselineRegistry(path, "production")


def test_registry_appends_rollback_generation_without_erasing_failed_baseline(
    tmp_path: Path,
) -> None:
    baseline, windows, drift_report, request, receipt = _rollback_evidence()
    recovery_rounds = _recovery_rounds(receipt)
    recovery_report = PostRollbackRecoveryGate().evaluate(receipt, recovery_rounds)
    path = tmp_path / "baseline.jsonl"
    registry = _registry_with_current(path)

    record = registry.register_rollback(
        baseline,
        windows,
        drift_report,
        request,
        receipt,
        recovery_rounds,
        recovery_report,
        host_registration_ref="host:registry:rollback:3",
        evidence_refs=("evidence:registry:rollback",),
    )

    history = registry.history()
    assert len(history) == 3
    assert history[1].model_id == baseline.model_id
    assert history[1].record_kind is BaselineRecordKind.CANONICALIZATION
    assert record.generation == 3
    assert record.record_kind is BaselineRecordKind.ROLLBACK
    assert record.model_id == baseline.previous_model_id
    assert record.previous_model_id == baseline.model_id
    assert record.rollback_execution_receipt_fingerprint == receipt.receipt_fingerprint
    assert record.recovery_report_fingerprint == recovery_report.report_fingerprint
    assert record.rollback_model_id is None
    assert record.auto_rollback is False

    reopened = BaselineRegistry(path, "production")
    assert reopened.history() == history
    assert reopened.current() == record


def test_operational_watch_resumes_through_rollback_registration(tmp_path: Path) -> None:
    baseline, windows, drift_report, request, receipt = _rollback_evidence()
    recovery_rounds = _recovery_rounds(receipt)
    recovery_report = PostRollbackRecoveryGate().evaluate(receipt, recovery_rounds)
    registry = _registry_with_current(tmp_path / "registry.jsonl")
    record = registry.register_rollback(
        baseline,
        windows,
        drift_report,
        request,
        receipt,
        recovery_rounds,
        recovery_report,
        host_registration_ref="host:registry:rollback:3",
        evidence_refs=("evidence:registry:rollback",),
    )

    path = tmp_path / "watch.jsonl"
    store = OperationalWatchStateStore(path, "watch-a26")
    store.bind_baseline(baseline)
    store.record_drift_review(baseline, windows, drift_report)
    store.record_rollback_review_request(baseline, windows, drift_report, request)
    store.record_rollback_execution(baseline, windows, drift_report, request, receipt)
    store.record_post_rollback_recovery(receipt, recovery_rounds, recovery_report)
    state = store.record_rollback_baseline_registration(record)
    assert state.stage is OperationalWatchStage.ROLLBACK_BASELINE_REGISTERED
    assert state.rollback_baseline_record_fingerprint == record.record_fingerprint

    reopened = OperationalWatchStateStore(path, "watch-a26")
    assert reopened.latest() == state


def test_operational_watch_rejects_recovery_stage_skip(tmp_path: Path) -> None:
    baseline, windows, drift_report, request, receipt = _rollback_evidence()
    recovery_rounds = _recovery_rounds(receipt)
    recovery_report = PostRollbackRecoveryGate().evaluate(receipt, recovery_rounds)
    store = OperationalWatchStateStore(tmp_path / "skip.jsonl", "watch-skip-a26")
    store.bind_baseline(baseline)
    store.record_drift_review(baseline, windows, drift_report)
    store.record_rollback_review_request(baseline, windows, drift_report, request)
    with pytest.raises(OperationalWatchStateError, match="rollback_execution_recorded"):
        store.record_post_rollback_recovery(receipt, recovery_rounds, recovery_report)
