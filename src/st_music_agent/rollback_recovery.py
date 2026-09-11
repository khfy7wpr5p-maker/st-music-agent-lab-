from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from enum import Enum
from typing import Any

from .baseline_registry import BaselineRecord
from .drift_watch import (
    DriftObservationWindow,
    DriftWatchReport,
    RollbackReviewRequest,
    RollbackReviewRequestBuilder,
)

ROLLBACK_EXECUTION_RECEIPT_SCHEMA_VERSION = "1.0.0"
POST_ROLLBACK_RECOVERY_SCHEMA_VERSION = "1.0.0"
POST_ROLLBACK_RECOVERY_POLICY_VERSION = "2026-09-11.v1"
POST_ROLLBACK_MIN_ROUNDS = 2
_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_MODEL_ID = re.compile(r"^model:[0-9a-f]{64}$")


class RollbackRecoveryError(RuntimeError):
    pass


class RollbackExecutionOutcome(str, Enum):
    ROLLED_BACK = "rolled_back"
    FAILED = "failed"


class RecoveryCheckKind(str, Enum):
    SERVING_IDENTITY = "serving_identity"
    HEALTH = "health"
    RECOVERY = "recovery"


class RecoveryCheckStatus(str, Enum):
    SUCCESS = "success"
    FAILURE = "failure"
    UNAVAILABLE = "unavailable"


class PostRollbackRecoveryDecision(str, Enum):
    ELIGIBLE_FOR_BASELINE_REGISTRATION = "eligible_for_baseline_registration"
    REJECTED = "rejected"


def _canonical_hash(value: Any) -> str:
    encoded = json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _require_sha(value: str, label: str) -> None:
    if not isinstance(value, str) or not _SHA256.fullmatch(value):
        raise RollbackRecoveryError(f"{label} must be a lowercase SHA-256 digest")


def _require_model(value: str, label: str) -> None:
    if not isinstance(value, str) or not _MODEL_ID.fullmatch(value):
        raise RollbackRecoveryError(f"{label} must be a model candidate id")


def _require_text(value: str, label: str) -> None:
    if not isinstance(value, str) or not value.strip():
        raise RollbackRecoveryError(f"{label} must be non-empty text")


@dataclass(frozen=True, slots=True)
class RollbackExecutionReceipt:
    baseline_record_fingerprint: str
    rollback_review_request_fingerprint: str
    drift_report_fingerprint: str
    environment: str
    from_model_id: str
    from_checkpoint_sha256: str
    to_model_id: str
    to_checkpoint_sha256: str
    outcome: RollbackExecutionOutcome
    host_authorization_ref: str
    execution_ref: str
    evidence_refs: tuple[str, ...]
    observed_model_id: str | None
    observed_checkpoint_sha256: str | None
    receipt_fingerprint: str
    post_rollback_recovery_required: bool
    auto_rollback: bool = False
    auto_switch: bool = False

    def as_dict(self) -> dict[str, Any]:
        return {
            "schema_version": ROLLBACK_EXECUTION_RECEIPT_SCHEMA_VERSION,
            "baseline_record_fingerprint": self.baseline_record_fingerprint,
            "rollback_review_request_fingerprint": self.rollback_review_request_fingerprint,
            "drift_report_fingerprint": self.drift_report_fingerprint,
            "environment": self.environment,
            "from_model_id": self.from_model_id,
            "from_checkpoint_sha256": self.from_checkpoint_sha256,
            "to_model_id": self.to_model_id,
            "to_checkpoint_sha256": self.to_checkpoint_sha256,
            "outcome": self.outcome.value,
            "host_authorization_ref": self.host_authorization_ref,
            "execution_ref": self.execution_ref,
            "evidence_refs": list(self.evidence_refs),
            "observed_model_id": self.observed_model_id,
            "observed_checkpoint_sha256": self.observed_checkpoint_sha256,
            "receipt_fingerprint": self.receipt_fingerprint,
            "post_rollback_recovery_required": self.post_rollback_recovery_required,
            "auto_rollback": self.auto_rollback,
            "auto_switch": self.auto_switch,
        }


class RollbackExecutionReceiptBuilder:
    """Records a separately authorized host rollback; it never executes the rollback."""

    def bind(
        self,
        baseline: BaselineRecord,
        windows: tuple[DriftObservationWindow, ...],
        drift_report: DriftWatchReport,
        request: RollbackReviewRequest,
        *,
        outcome: RollbackExecutionOutcome,
        host_authorization_ref: str,
        execution_ref: str,
        evidence_refs: tuple[str, ...],
        observed_model_id: str | None,
        observed_checkpoint_sha256: str | None,
    ) -> RollbackExecutionReceipt:
        request_builder = RollbackReviewRequestBuilder()
        request_builder.verify_with_evidence(baseline, windows, drift_report, request)
        request_builder.verify_record(request)
        _require_text(host_authorization_ref, "host_authorization_ref")
        _require_text(execution_ref, "execution_ref")
        if not evidence_refs or any(not ref.strip() for ref in evidence_refs):
            raise RollbackRecoveryError("rollback execution receipt requires evidence references")

        if outcome is RollbackExecutionOutcome.ROLLED_BACK:
            if observed_model_id != request.rollback_model_id:
                raise RollbackRecoveryError("observed rollback model does not match approved target")
            if observed_checkpoint_sha256 != request.rollback_checkpoint_sha256:
                raise RollbackRecoveryError(
                    "observed rollback checkpoint does not match approved target"
                )
            post_rollback_recovery_required = True
        else:
            if (observed_model_id is None) != (observed_checkpoint_sha256 is None):
                raise RollbackRecoveryError("failed rollback observation must be complete or absent")
            if observed_model_id is not None:
                if observed_model_id != request.current_model_id:
                    raise RollbackRecoveryError("failed rollback can only observe original baseline")
                if observed_checkpoint_sha256 != request.current_checkpoint_sha256:
                    raise RollbackRecoveryError(
                        "failed rollback can only observe original baseline checkpoint"
                    )
            post_rollback_recovery_required = False

        if observed_model_id is not None:
            _require_model(observed_model_id, "observed model id")
        if observed_checkpoint_sha256 is not None:
            _require_sha(observed_checkpoint_sha256, "observed checkpoint")

        base = {
            "schema_version": ROLLBACK_EXECUTION_RECEIPT_SCHEMA_VERSION,
            "baseline_record_fingerprint": baseline.record_fingerprint,
            "rollback_review_request_fingerprint": request.request_fingerprint,
            "drift_report_fingerprint": drift_report.report_fingerprint,
            "environment": baseline.environment,
            "from_model_id": request.current_model_id,
            "from_checkpoint_sha256": request.current_checkpoint_sha256,
            "to_model_id": request.rollback_model_id,
            "to_checkpoint_sha256": request.rollback_checkpoint_sha256,
            "outcome": outcome.value,
            "host_authorization_ref": host_authorization_ref,
            "execution_ref": execution_ref,
            "evidence_refs": list(evidence_refs),
            "observed_model_id": observed_model_id,
            "observed_checkpoint_sha256": observed_checkpoint_sha256,
            "post_rollback_recovery_required": post_rollback_recovery_required,
            "auto_rollback": False,
            "auto_switch": False,
        }
        return RollbackExecutionReceipt(
            baseline_record_fingerprint=baseline.record_fingerprint,
            rollback_review_request_fingerprint=request.request_fingerprint,
            drift_report_fingerprint=drift_report.report_fingerprint,
            environment=baseline.environment,
            from_model_id=request.current_model_id,
            from_checkpoint_sha256=request.current_checkpoint_sha256,
            to_model_id=request.rollback_model_id,
            to_checkpoint_sha256=request.rollback_checkpoint_sha256,
            outcome=outcome,
            host_authorization_ref=host_authorization_ref,
            execution_ref=execution_ref,
            evidence_refs=evidence_refs,
            observed_model_id=observed_model_id,
            observed_checkpoint_sha256=observed_checkpoint_sha256,
            receipt_fingerprint=_canonical_hash(base),
            post_rollback_recovery_required=post_rollback_recovery_required,
        )

    def verify_with_evidence(
        self,
        baseline: BaselineRecord,
        windows: tuple[DriftObservationWindow, ...],
        drift_report: DriftWatchReport,
        request: RollbackReviewRequest,
        receipt: RollbackExecutionReceipt,
    ) -> None:
        recomputed = self.bind(
            baseline,
            windows,
            drift_report,
            request,
            outcome=receipt.outcome,
            host_authorization_ref=receipt.host_authorization_ref,
            execution_ref=receipt.execution_ref,
            evidence_refs=receipt.evidence_refs,
            observed_model_id=receipt.observed_model_id,
            observed_checkpoint_sha256=receipt.observed_checkpoint_sha256,
        )
        if recomputed.as_dict() != receipt.as_dict():
            raise RollbackRecoveryError("rollback receipt differs from source-evidence recomputation")

    @staticmethod
    def verify_record(receipt: RollbackExecutionReceipt) -> None:
        if receipt.auto_rollback or receipt.auto_switch:
            raise RollbackRecoveryError("rollback receipt cannot authorize automatic actions")
        _require_sha(receipt.baseline_record_fingerprint, "baseline record fingerprint")
        _require_sha(receipt.rollback_review_request_fingerprint, "rollback request fingerprint")
        _require_sha(receipt.drift_report_fingerprint, "drift report fingerprint")
        _require_model(receipt.from_model_id, "from model id")
        _require_model(receipt.to_model_id, "to model id")
        _require_sha(receipt.from_checkpoint_sha256, "from checkpoint")
        _require_sha(receipt.to_checkpoint_sha256, "to checkpoint")
        _require_text(receipt.environment, "environment")
        _require_text(receipt.host_authorization_ref, "host authorization ref")
        _require_text(receipt.execution_ref, "execution ref")
        if not receipt.evidence_refs or any(not ref.strip() for ref in receipt.evidence_refs):
            raise RollbackRecoveryError("rollback receipt requires evidence references")

        if receipt.outcome is RollbackExecutionOutcome.ROLLED_BACK:
            if not receipt.post_rollback_recovery_required:
                raise RollbackRecoveryError("successful rollback must require recovery verification")
            if receipt.observed_model_id != receipt.to_model_id:
                raise RollbackRecoveryError("rollback receipt observed model is invalid")
            if receipt.observed_checkpoint_sha256 != receipt.to_checkpoint_sha256:
                raise RollbackRecoveryError("rollback receipt observed checkpoint is invalid")
        else:
            if receipt.post_rollback_recovery_required:
                raise RollbackRecoveryError("failed rollback cannot require target recovery")
            if (receipt.observed_model_id is None) != (
                receipt.observed_checkpoint_sha256 is None
            ):
                raise RollbackRecoveryError("failed rollback observation is incomplete")

        base = receipt.as_dict()
        fingerprint = base.pop("receipt_fingerprint")
        _require_sha(fingerprint, "rollback receipt fingerprint")
        if _canonical_hash(base) != fingerprint:
            raise RollbackRecoveryError("rollback receipt fingerprint does not verify")


@dataclass(frozen=True, slots=True)
class RecoveryCheck:
    kind: RecoveryCheckKind
    status: RecoveryCheckStatus
    evidence_refs: tuple[str, ...]
    observed_model_id: str | None = None
    observed_checkpoint_sha256: str | None = None

    def as_dict(self) -> dict[str, Any]:
        return {
            "kind": self.kind.value,
            "status": self.status.value,
            "evidence_refs": list(self.evidence_refs),
            "observed_model_id": self.observed_model_id,
            "observed_checkpoint_sha256": self.observed_checkpoint_sha256,
        }


@dataclass(frozen=True, slots=True)
class PostRollbackRecoveryRound:
    sequence: int
    observation_ref: str
    checks: tuple[RecoveryCheck, ...]

    def as_dict(self) -> dict[str, Any]:
        return {
            "sequence": self.sequence,
            "observation_ref": self.observation_ref,
            "checks": [check.as_dict() for check in self.checks],
        }


@dataclass(frozen=True, slots=True)
class PostRollbackRecoveryReport:
    policy_version: str
    rollback_receipt_fingerprint: str
    environment: str
    model_id: str
    checkpoint_sha256: str
    observation_round_count: int
    observation_refs: tuple[str, ...]
    decision: PostRollbackRecoveryDecision
    reasons: tuple[str, ...]
    report_fingerprint: str
    host_registration_required: bool = True
    auto_register_baseline: bool = False
    auto_switch: bool = False
    auto_rollback: bool = False

    def as_dict(self) -> dict[str, Any]:
        return {
            "schema_version": POST_ROLLBACK_RECOVERY_SCHEMA_VERSION,
            "policy_version": self.policy_version,
            "rollback_receipt_fingerprint": self.rollback_receipt_fingerprint,
            "environment": self.environment,
            "model_id": self.model_id,
            "checkpoint_sha256": self.checkpoint_sha256,
            "observation_round_count": self.observation_round_count,
            "observation_refs": list(self.observation_refs),
            "decision": self.decision.value,
            "reasons": list(self.reasons),
            "report_fingerprint": self.report_fingerprint,
            "host_registration_required": self.host_registration_required,
            "auto_register_baseline": self.auto_register_baseline,
            "auto_switch": self.auto_switch,
            "auto_rollback": self.auto_rollback,
        }


class PostRollbackRecoveryGate:
    """Requires repeated recovery evidence after an externally executed rollback."""

    def evaluate(
        self,
        receipt: RollbackExecutionReceipt,
        rounds: tuple[PostRollbackRecoveryRound, ...],
    ) -> PostRollbackRecoveryReport:
        RollbackExecutionReceiptBuilder.verify_record(receipt)
        if receipt.outcome is not RollbackExecutionOutcome.ROLLED_BACK:
            raise RollbackRecoveryError("post-rollback recovery requires successful rollback")
        if not receipt.post_rollback_recovery_required:
            raise RollbackRecoveryError("rollback receipt does not require recovery verification")
        if len(rounds) < POST_ROLLBACK_MIN_ROUNDS:
            raise RollbackRecoveryError(
                f"post-rollback recovery requires at least {POST_ROLLBACK_MIN_ROUNDS} rounds"
            )

        expected = set(RecoveryCheckKind)
        observation_refs: list[str] = []
        reasons: list[str] = []
        seen_refs: set[str] = set()
        all_success = True

        for expected_sequence, round_ in enumerate(rounds, start=1):
            if round_.sequence != expected_sequence:
                raise RollbackRecoveryError("recovery round sequences must be contiguous from one")
            _require_text(round_.observation_ref, "recovery observation ref")
            if round_.observation_ref in seen_refs:
                raise RollbackRecoveryError("recovery observation refs must be unique")
            seen_refs.add(round_.observation_ref)
            observation_refs.append(round_.observation_ref)

            by_kind = {check.kind: check for check in round_.checks}
            if len(by_kind) != len(round_.checks) or set(by_kind) != expected:
                raise RollbackRecoveryError("each recovery round requires exact required checks")
            for check in round_.checks:
                if not check.evidence_refs or any(not ref.strip() for ref in check.evidence_refs):
                    raise RollbackRecoveryError("recovery checks require evidence references")

            identity = by_kind[RecoveryCheckKind.SERVING_IDENTITY]
            if identity.observed_model_id != receipt.to_model_id:
                raise RollbackRecoveryError("recovery serving identity does not match rollback target")
            if identity.observed_checkpoint_sha256 != receipt.to_checkpoint_sha256:
                raise RollbackRecoveryError(
                    "recovery serving checkpoint does not match rollback target"
                )
            if identity.status is not RecoveryCheckStatus.SUCCESS:
                all_success = False
                reasons.append(f"round {round_.sequence} serving identity not successful")

            for kind in (RecoveryCheckKind.HEALTH, RecoveryCheckKind.RECOVERY):
                check = by_kind[kind]
                if check.status is not RecoveryCheckStatus.SUCCESS:
                    all_success = False
                    reasons.append(
                        f"round {round_.sequence} {kind.value} {check.status.value}"
                    )

        decision = (
            PostRollbackRecoveryDecision.ELIGIBLE_FOR_BASELINE_REGISTRATION
            if all_success
            else PostRollbackRecoveryDecision.REJECTED
        )
        if all_success:
            reasons.append("rollback target passed repeated serving, health, and recovery checks")

        base = {
            "schema_version": POST_ROLLBACK_RECOVERY_SCHEMA_VERSION,
            "policy_version": POST_ROLLBACK_RECOVERY_POLICY_VERSION,
            "rollback_receipt_fingerprint": receipt.receipt_fingerprint,
            "environment": receipt.environment,
            "model_id": receipt.to_model_id,
            "checkpoint_sha256": receipt.to_checkpoint_sha256,
            "observation_round_count": len(rounds),
            "observation_refs": observation_refs,
            "decision": decision.value,
            "reasons": reasons,
            "host_registration_required": True,
            "auto_register_baseline": False,
            "auto_switch": False,
            "auto_rollback": False,
        }
        return PostRollbackRecoveryReport(
            policy_version=POST_ROLLBACK_RECOVERY_POLICY_VERSION,
            rollback_receipt_fingerprint=receipt.receipt_fingerprint,
            environment=receipt.environment,
            model_id=receipt.to_model_id,
            checkpoint_sha256=receipt.to_checkpoint_sha256,
            observation_round_count=len(rounds),
            observation_refs=tuple(observation_refs),
            decision=decision,
            reasons=tuple(reasons),
            report_fingerprint=_canonical_hash(base),
        )

    def verify(
        self,
        receipt: RollbackExecutionReceipt,
        rounds: tuple[PostRollbackRecoveryRound, ...],
        report: PostRollbackRecoveryReport,
    ) -> None:
        recomputed = self.evaluate(receipt, rounds)
        if recomputed.as_dict() != report.as_dict():
            raise RollbackRecoveryError("recovery report differs from source-evidence recomputation")
