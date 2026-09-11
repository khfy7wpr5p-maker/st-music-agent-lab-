from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from enum import Enum
from typing import Any

from .activation_receipt import (
    ActivationReceipt,
    ActivationReceiptBuilder,
    ActivationReceiptOutcome,
)

SHADOW_HEALTH_SCHEMA_VERSION = "1.0.0"
SHADOW_HEALTH_POLICY_VERSION = "2026-09-11.v1"


class ShadowHealthError(RuntimeError):
    pass


class RuntimeCheckKind(str, Enum):
    SERVING_IDENTITY = "serving_identity"
    HEALTH = "health"
    SHADOW_QUALITY = "shadow_quality"
    ROLLBACK_READINESS = "rollback_readiness"


class RuntimeCheckStatus(str, Enum):
    SUCCESS = "success"
    FAILURE = "failure"
    UNAVAILABLE = "unavailable"


class ShadowHealthDecision(str, Enum):
    ELIGIBLE_FOR_CANONICAL_REVIEW = "eligible_for_canonical_review"
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


@dataclass(frozen=True, slots=True)
class RuntimeCheck:
    kind: RuntimeCheckKind
    status: RuntimeCheckStatus
    evidence_refs: tuple[str, ...]

    def __post_init__(self) -> None:
        if not self.evidence_refs or any(not ref.strip() for ref in self.evidence_refs):
            raise ValueError("runtime check requires non-empty evidence references")

    def as_dict(self) -> dict[str, Any]:
        return {
            "kind": self.kind.value,
            "status": self.status.value,
            "evidence_refs": list(self.evidence_refs),
        }


@dataclass(frozen=True, slots=True)
class ShadowHealthReport:
    policy_version: str
    activation_receipt_fingerprint: str
    candidate_id: str
    checkpoint_sha256: str
    target_environment: str
    rollback_candidate_id: str
    rollback_checkpoint_sha256: str
    checks_fingerprint: str
    decision: ShadowHealthDecision
    reasons: tuple[str, ...]
    report_fingerprint: str
    human_review_required: bool = True
    canonicalization_authorized: bool = False
    auto_canonicalize: bool = False

    def as_dict(self) -> dict[str, Any]:
        return {
            "schema_version": SHADOW_HEALTH_SCHEMA_VERSION,
            "policy_version": self.policy_version,
            "activation_receipt_fingerprint": self.activation_receipt_fingerprint,
            "candidate_id": self.candidate_id,
            "checkpoint_sha256": self.checkpoint_sha256,
            "target_environment": self.target_environment,
            "rollback_candidate_id": self.rollback_candidate_id,
            "rollback_checkpoint_sha256": self.rollback_checkpoint_sha256,
            "checks_fingerprint": self.checks_fingerprint,
            "decision": self.decision.value,
            "reasons": list(self.reasons),
            "report_fingerprint": self.report_fingerprint,
            "human_review_required": self.human_review_required,
            "canonicalization_authorized": self.canonicalization_authorized,
            "auto_canonicalize": self.auto_canonicalize,
        }


class ShadowHealthGate:
    """Evaluates post-activation runtime evidence without canonicalizing a candidate."""

    _REQUIRED_KINDS = frozenset(RuntimeCheckKind)

    def evaluate(
        self,
        receipt: ActivationReceipt,
        checks: tuple[RuntimeCheck, ...],
    ) -> ShadowHealthReport:
        ActivationReceiptBuilder.verify(receipt)
        if receipt.outcome is not ActivationReceiptOutcome.ACTIVATED:
            raise ShadowHealthError("shadow health evaluation requires an activated receipt")
        if not receipt.shadow_health_required:
            raise ShadowHealthError("activated receipt must require shadow health evaluation")

        check_map: dict[RuntimeCheckKind, RuntimeCheck] = {}
        for check in checks:
            if check.kind in check_map:
                raise ShadowHealthError("runtime check kinds must be unique")
            check_map[check.kind] = check
        if set(check_map) != self._REQUIRED_KINDS:
            raise ShadowHealthError("runtime checks must cover the exact required check kinds")

        ordered_checks = tuple(check_map[kind] for kind in RuntimeCheckKind)
        checks_fingerprint = _canonical_hash([check.as_dict() for check in ordered_checks])

        reasons: list[str] = []
        for check in ordered_checks:
            if check.status is RuntimeCheckStatus.FAILURE:
                reasons.append(f"{check.kind.value} failed")
            elif check.status is RuntimeCheckStatus.UNAVAILABLE:
                reasons.append(f"{check.kind.value} unavailable")

        decision = (
            ShadowHealthDecision.ELIGIBLE_FOR_CANONICAL_REVIEW
            if not reasons
            else ShadowHealthDecision.REJECTED
        )
        base = {
            "schema_version": SHADOW_HEALTH_SCHEMA_VERSION,
            "policy_version": SHADOW_HEALTH_POLICY_VERSION,
            "activation_receipt_fingerprint": receipt.receipt_fingerprint,
            "candidate_id": receipt.candidate_id,
            "checkpoint_sha256": receipt.candidate_checkpoint_sha256,
            "target_environment": receipt.target_environment,
            "rollback_candidate_id": receipt.rollback_candidate_id,
            "rollback_checkpoint_sha256": receipt.rollback_checkpoint_sha256,
            "checks_fingerprint": checks_fingerprint,
            "decision": decision.value,
            "reasons": reasons,
            "human_review_required": True,
            "canonicalization_authorized": False,
            "auto_canonicalize": False,
        }
        return ShadowHealthReport(
            policy_version=SHADOW_HEALTH_POLICY_VERSION,
            activation_receipt_fingerprint=receipt.receipt_fingerprint,
            candidate_id=receipt.candidate_id,
            checkpoint_sha256=receipt.candidate_checkpoint_sha256,
            target_environment=receipt.target_environment,
            rollback_candidate_id=receipt.rollback_candidate_id,
            rollback_checkpoint_sha256=receipt.rollback_checkpoint_sha256,
            checks_fingerprint=checks_fingerprint,
            decision=decision,
            reasons=tuple(reasons),
            report_fingerprint=_canonical_hash(base),
            human_review_required=True,
            canonicalization_authorized=False,
            auto_canonicalize=False,
        )

    def verify(
        self,
        receipt: ActivationReceipt,
        checks: tuple[RuntimeCheck, ...],
        report: ShadowHealthReport,
    ) -> None:
        recomputed = self.evaluate(receipt, checks)
        if recomputed.as_dict() != report.as_dict():
            raise ShadowHealthError("shadow health report differs from recomputation")
        if not report.human_review_required:
            raise ShadowHealthError("shadow health report must require human review")
        if report.canonicalization_authorized or report.auto_canonicalize:
            raise ShadowHealthError("shadow health report cannot authorize canonicalization")
