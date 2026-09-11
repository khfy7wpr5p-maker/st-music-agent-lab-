from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from enum import Enum
from typing import Any

from .activation_receipt import ActivationReceipt, ActivationReceiptBuilder, ActivationReceiptOutcome
from .shadow_health import (
    RuntimeCheck,
    ShadowHealthDecision,
    ShadowHealthGate,
    ShadowHealthReport,
)

CANONICAL_REVIEW_SCHEMA_VERSION = "1.0.0"
CANONICALIZATION_RECEIPT_SCHEMA_VERSION = "1.0.0"
_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_MODEL_ID = re.compile(r"^model:[0-9a-f]{64}$")


class CanonicalBaselineError(RuntimeError):
    pass


class CanonicalReviewDecision(str, Enum):
    ELIGIBLE_FOR_HOST_CANONICALIZATION = "eligible_for_host_canonicalization"
    REJECTED = "rejected"


class CanonicalizationOutcome(str, Enum):
    CANONICALIZED = "canonicalized"
    FAILED = "failed"
    ROLLED_BACK = "rolled_back"


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
        raise CanonicalBaselineError(f"{label} is invalid")


def _require_model(value: str, label: str) -> None:
    if not isinstance(value, str) or not _MODEL_ID.fullmatch(value):
        raise CanonicalBaselineError(f"{label} is invalid")


@dataclass(frozen=True, slots=True)
class CanonicalBaselineReview:
    activation_receipt_fingerprint: str
    shadow_health_report_fingerprint: str
    candidate_id: str
    candidate_checkpoint_sha256: str
    current_canonical_id: str
    current_canonical_checkpoint_sha256: str
    rollback_candidate_id: str
    rollback_checkpoint_sha256: str
    target_environment: str
    decision: CanonicalReviewDecision
    reasons: tuple[str, ...]
    review_fingerprint: str
    human_approval_required: bool = True
    canonicalization_authorized: bool = False
    auto_canonicalize: bool = False

    def as_dict(self) -> dict[str, Any]:
        return {
            "schema_version": CANONICAL_REVIEW_SCHEMA_VERSION,
            "activation_receipt_fingerprint": self.activation_receipt_fingerprint,
            "shadow_health_report_fingerprint": self.shadow_health_report_fingerprint,
            "candidate_id": self.candidate_id,
            "candidate_checkpoint_sha256": self.candidate_checkpoint_sha256,
            "current_canonical_id": self.current_canonical_id,
            "current_canonical_checkpoint_sha256": self.current_canonical_checkpoint_sha256,
            "rollback_candidate_id": self.rollback_candidate_id,
            "rollback_checkpoint_sha256": self.rollback_checkpoint_sha256,
            "target_environment": self.target_environment,
            "decision": self.decision.value,
            "reasons": list(self.reasons),
            "review_fingerprint": self.review_fingerprint,
            "human_approval_required": self.human_approval_required,
            "canonicalization_authorized": self.canonicalization_authorized,
            "auto_canonicalize": self.auto_canonicalize,
        }


class CanonicalBaselineReviewGate:
    """Recomputes A22 runtime evidence before host canonicalization may be reviewed."""

    def review(
        self,
        receipt: ActivationReceipt,
        checks: tuple[RuntimeCheck, ...],
        shadow_report: ShadowHealthReport,
        *,
        current_canonical_id: str,
        current_canonical_checkpoint_sha256: str,
    ) -> CanonicalBaselineReview:
        ActivationReceiptBuilder.verify(receipt)
        ShadowHealthGate().verify(receipt, checks, shadow_report)
        if receipt.outcome is not ActivationReceiptOutcome.ACTIVATED:
            raise CanonicalBaselineError("canonical review requires an activated receipt")
        _require_model(current_canonical_id, "current canonical id")
        _require_sha(current_canonical_checkpoint_sha256, "current canonical checkpoint")

        reasons: list[str] = []
        if shadow_report.decision is not ShadowHealthDecision.ELIGIBLE_FOR_CANONICAL_REVIEW:
            reasons.append("shadow health is not eligible for canonical review")
        if current_canonical_id != receipt.previous_baseline_id:
            reasons.append("current canonical model differs from activation baseline")
        if current_canonical_checkpoint_sha256 != receipt.previous_baseline_checkpoint_sha256:
            reasons.append("current canonical checkpoint differs from activation baseline")
        if receipt.rollback_candidate_id != current_canonical_id:
            reasons.append("rollback model is not the current canonical baseline")
        if receipt.rollback_checkpoint_sha256 != current_canonical_checkpoint_sha256:
            reasons.append("rollback checkpoint is not the current canonical checkpoint")

        decision = (
            CanonicalReviewDecision.ELIGIBLE_FOR_HOST_CANONICALIZATION
            if not reasons
            else CanonicalReviewDecision.REJECTED
        )
        base = {
            "schema_version": CANONICAL_REVIEW_SCHEMA_VERSION,
            "activation_receipt_fingerprint": receipt.receipt_fingerprint,
            "shadow_health_report_fingerprint": shadow_report.report_fingerprint,
            "candidate_id": receipt.candidate_id,
            "candidate_checkpoint_sha256": receipt.candidate_checkpoint_sha256,
            "current_canonical_id": current_canonical_id,
            "current_canonical_checkpoint_sha256": current_canonical_checkpoint_sha256,
            "rollback_candidate_id": receipt.rollback_candidate_id,
            "rollback_checkpoint_sha256": receipt.rollback_checkpoint_sha256,
            "target_environment": receipt.target_environment,
            "decision": decision.value,
            "reasons": reasons,
            "human_approval_required": True,
            "canonicalization_authorized": False,
            "auto_canonicalize": False,
        }
        return CanonicalBaselineReview(
            activation_receipt_fingerprint=receipt.receipt_fingerprint,
            shadow_health_report_fingerprint=shadow_report.report_fingerprint,
            candidate_id=receipt.candidate_id,
            candidate_checkpoint_sha256=receipt.candidate_checkpoint_sha256,
            current_canonical_id=current_canonical_id,
            current_canonical_checkpoint_sha256=current_canonical_checkpoint_sha256,
            rollback_candidate_id=receipt.rollback_candidate_id,
            rollback_checkpoint_sha256=receipt.rollback_checkpoint_sha256,
            target_environment=receipt.target_environment,
            decision=decision,
            reasons=tuple(reasons),
            review_fingerprint=_canonical_hash(base),
        )

    def verify_with_evidence(
        self,
        receipt: ActivationReceipt,
        checks: tuple[RuntimeCheck, ...],
        shadow_report: ShadowHealthReport,
        review: CanonicalBaselineReview,
    ) -> None:
        recomputed = self.review(
            receipt,
            checks,
            shadow_report,
            current_canonical_id=review.current_canonical_id,
            current_canonical_checkpoint_sha256=review.current_canonical_checkpoint_sha256,
        )
        if recomputed.as_dict() != review.as_dict():
            raise CanonicalBaselineError("canonical review differs from source-evidence recomputation")

    @staticmethod
    def verify_record(review: CanonicalBaselineReview) -> None:
        if not review.human_approval_required:
            raise CanonicalBaselineError("canonical review must require human approval")
        if review.canonicalization_authorized or review.auto_canonicalize:
            raise CanonicalBaselineError("canonical review cannot authorize canonicalization")
        _require_model(review.candidate_id, "canonical review candidate id")
        _require_model(review.current_canonical_id, "canonical review current baseline id")
        _require_model(review.rollback_candidate_id, "canonical review rollback id")
        for label, value in (
            ("candidate checkpoint", review.candidate_checkpoint_sha256),
            ("current canonical checkpoint", review.current_canonical_checkpoint_sha256),
            ("rollback checkpoint", review.rollback_checkpoint_sha256),
            ("activation receipt fingerprint", review.activation_receipt_fingerprint),
            ("shadow health report fingerprint", review.shadow_health_report_fingerprint),
        ):
            _require_sha(value, label)
        if review.rollback_candidate_id != review.current_canonical_id:
            raise CanonicalBaselineError("canonical review rollback model is invalid")
        if review.rollback_checkpoint_sha256 != review.current_canonical_checkpoint_sha256:
            raise CanonicalBaselineError("canonical review rollback checkpoint is invalid")

        base = review.as_dict()
        fingerprint = base.pop("review_fingerprint")
        _require_sha(fingerprint, "canonical review fingerprint")
        if _canonical_hash(base) != fingerprint:
            raise CanonicalBaselineError("canonical review fingerprint does not verify")


@dataclass(frozen=True, slots=True)
class CanonicalizationReceipt:
    canonical_review_fingerprint: str
    candidate_id: str
    candidate_checkpoint_sha256: str
    previous_canonical_id: str
    previous_canonical_checkpoint_sha256: str
    rollback_candidate_id: str
    rollback_checkpoint_sha256: str
    target_environment: str
    outcome: CanonicalizationOutcome
    host_authorization_ref: str
    canonicalization_ref: str
    evidence_refs: tuple[str, ...]
    observed_canonical_id: str | None
    observed_canonical_checkpoint_sha256: str | None
    receipt_fingerprint: str
    post_canonical_health_required: bool
    auto_rollback: bool = False
    auto_canonicalize: bool = False

    def as_dict(self) -> dict[str, Any]:
        return {
            "schema_version": CANONICALIZATION_RECEIPT_SCHEMA_VERSION,
            "canonical_review_fingerprint": self.canonical_review_fingerprint,
            "candidate_id": self.candidate_id,
            "candidate_checkpoint_sha256": self.candidate_checkpoint_sha256,
            "previous_canonical_id": self.previous_canonical_id,
            "previous_canonical_checkpoint_sha256": self.previous_canonical_checkpoint_sha256,
            "rollback_candidate_id": self.rollback_candidate_id,
            "rollback_checkpoint_sha256": self.rollback_checkpoint_sha256,
            "target_environment": self.target_environment,
            "outcome": self.outcome.value,
            "host_authorization_ref": self.host_authorization_ref,
            "canonicalization_ref": self.canonicalization_ref,
            "evidence_refs": list(self.evidence_refs),
            "observed_canonical_id": self.observed_canonical_id,
            "observed_canonical_checkpoint_sha256": self.observed_canonical_checkpoint_sha256,
            "receipt_fingerprint": self.receipt_fingerprint,
            "post_canonical_health_required": self.post_canonical_health_required,
            "auto_rollback": self.auto_rollback,
            "auto_canonicalize": self.auto_canonicalize,
        }


class CanonicalizationReceiptBuilder:
    """Records an externally authorized canonical-baseline change; never performs the switch."""

    def bind(
        self,
        receipt: ActivationReceipt,
        checks: tuple[RuntimeCheck, ...],
        shadow_report: ShadowHealthReport,
        review: CanonicalBaselineReview,
        *,
        outcome: CanonicalizationOutcome,
        host_authorization_ref: str,
        canonicalization_ref: str,
        evidence_refs: tuple[str, ...],
        observed_canonical_id: str | None,
        observed_canonical_checkpoint_sha256: str | None,
    ) -> CanonicalizationReceipt:
        gate = CanonicalBaselineReviewGate()
        gate.verify_with_evidence(receipt, checks, shadow_report, review)
        gate.verify_record(review)
        if review.decision is not CanonicalReviewDecision.ELIGIBLE_FOR_HOST_CANONICALIZATION:
            raise CanonicalBaselineError("canonical review is not eligible for host canonicalization")
        self._require_text(host_authorization_ref, "host_authorization_ref")
        self._require_text(canonicalization_ref, "canonicalization_ref")
        if not evidence_refs or any(not ref.strip() for ref in evidence_refs):
            raise ValueError("canonicalization receipt requires evidence references")

        if outcome is CanonicalizationOutcome.CANONICALIZED:
            if observed_canonical_id != review.candidate_id:
                raise CanonicalBaselineError("observed canonical model does not match candidate")
            if observed_canonical_checkpoint_sha256 != review.candidate_checkpoint_sha256:
                raise CanonicalBaselineError("observed canonical checkpoint does not match candidate")
            post_canonical_health_required = True
        elif outcome is CanonicalizationOutcome.ROLLED_BACK:
            if observed_canonical_id != review.rollback_candidate_id:
                raise CanonicalBaselineError("rolled-back canonical model does not match rollback target")
            if observed_canonical_checkpoint_sha256 != review.rollback_checkpoint_sha256:
                raise CanonicalBaselineError(
                    "rolled-back canonical checkpoint does not match rollback target"
                )
            post_canonical_health_required = False
        else:
            if (observed_canonical_id is None) != (observed_canonical_checkpoint_sha256 is None):
                raise CanonicalBaselineError("failed canonicalization observation must be complete or absent")
            if observed_canonical_id is not None:
                if observed_canonical_id != review.current_canonical_id:
                    raise CanonicalBaselineError("failed canonicalization can only observe prior baseline")
                if observed_canonical_checkpoint_sha256 != review.current_canonical_checkpoint_sha256:
                    raise CanonicalBaselineError(
                        "failed canonicalization can only observe prior baseline checkpoint"
                    )
            post_canonical_health_required = False

        if observed_canonical_id is not None:
            _require_model(observed_canonical_id, "observed canonical id")
        if observed_canonical_checkpoint_sha256 is not None:
            _require_sha(observed_canonical_checkpoint_sha256, "observed canonical checkpoint")

        base = {
            "schema_version": CANONICALIZATION_RECEIPT_SCHEMA_VERSION,
            "canonical_review_fingerprint": review.review_fingerprint,
            "candidate_id": review.candidate_id,
            "candidate_checkpoint_sha256": review.candidate_checkpoint_sha256,
            "previous_canonical_id": review.current_canonical_id,
            "previous_canonical_checkpoint_sha256": review.current_canonical_checkpoint_sha256,
            "rollback_candidate_id": review.rollback_candidate_id,
            "rollback_checkpoint_sha256": review.rollback_checkpoint_sha256,
            "target_environment": review.target_environment,
            "outcome": outcome.value,
            "host_authorization_ref": host_authorization_ref,
            "canonicalization_ref": canonicalization_ref,
            "evidence_refs": list(evidence_refs),
            "observed_canonical_id": observed_canonical_id,
            "observed_canonical_checkpoint_sha256": observed_canonical_checkpoint_sha256,
            "post_canonical_health_required": post_canonical_health_required,
            "auto_rollback": False,
            "auto_canonicalize": False,
        }
        return CanonicalizationReceipt(
            canonical_review_fingerprint=review.review_fingerprint,
            candidate_id=review.candidate_id,
            candidate_checkpoint_sha256=review.candidate_checkpoint_sha256,
            previous_canonical_id=review.current_canonical_id,
            previous_canonical_checkpoint_sha256=review.current_canonical_checkpoint_sha256,
            rollback_candidate_id=review.rollback_candidate_id,
            rollback_checkpoint_sha256=review.rollback_checkpoint_sha256,
            target_environment=review.target_environment,
            outcome=outcome,
            host_authorization_ref=host_authorization_ref,
            canonicalization_ref=canonicalization_ref,
            evidence_refs=evidence_refs,
            observed_canonical_id=observed_canonical_id,
            observed_canonical_checkpoint_sha256=observed_canonical_checkpoint_sha256,
            receipt_fingerprint=_canonical_hash(base),
            post_canonical_health_required=post_canonical_health_required,
        )

    @staticmethod
    def verify(receipt: CanonicalizationReceipt) -> None:
        if receipt.auto_rollback or receipt.auto_canonicalize:
            raise CanonicalBaselineError("canonicalization receipt cannot authorize automatic actions")
        if receipt.rollback_candidate_id != receipt.previous_canonical_id:
            raise CanonicalBaselineError("canonicalization receipt rollback model is invalid")
        if receipt.rollback_checkpoint_sha256 != receipt.previous_canonical_checkpoint_sha256:
            raise CanonicalBaselineError("canonicalization receipt rollback checkpoint is invalid")
        if not receipt.host_authorization_ref.strip() or not receipt.canonicalization_ref.strip():
            raise CanonicalBaselineError("canonicalization receipt is missing host evidence")
        if not receipt.evidence_refs or any(not ref.strip() for ref in receipt.evidence_refs):
            raise CanonicalBaselineError("canonicalization receipt is missing evidence references")

        if receipt.outcome is CanonicalizationOutcome.CANONICALIZED:
            if not receipt.post_canonical_health_required:
                raise CanonicalBaselineError("canonicalized receipt must require post-canonical health")
            if receipt.observed_canonical_id != receipt.candidate_id:
                raise CanonicalBaselineError("canonicalized receipt observed model is invalid")
            if receipt.observed_canonical_checkpoint_sha256 != receipt.candidate_checkpoint_sha256:
                raise CanonicalBaselineError("canonicalized receipt observed checkpoint is invalid")
        elif receipt.outcome is CanonicalizationOutcome.ROLLED_BACK:
            if receipt.post_canonical_health_required:
                raise CanonicalBaselineError("rolled-back receipt cannot require candidate health")
            if receipt.observed_canonical_id != receipt.rollback_candidate_id:
                raise CanonicalBaselineError("rolled-back receipt observed model is invalid")
            if receipt.observed_canonical_checkpoint_sha256 != receipt.rollback_checkpoint_sha256:
                raise CanonicalBaselineError("rolled-back receipt observed checkpoint is invalid")
        else:
            if receipt.post_canonical_health_required:
                raise CanonicalBaselineError("failed receipt cannot require candidate health")
            if (receipt.observed_canonical_id is None) != (
                receipt.observed_canonical_checkpoint_sha256 is None
            ):
                raise CanonicalBaselineError("failed receipt observation is incomplete")
            if receipt.observed_canonical_id is not None:
                if receipt.observed_canonical_id != receipt.previous_canonical_id:
                    raise CanonicalBaselineError("failed receipt observed model is invalid")
                if (
                    receipt.observed_canonical_checkpoint_sha256
                    != receipt.previous_canonical_checkpoint_sha256
                ):
                    raise CanonicalBaselineError("failed receipt observed checkpoint is invalid")

        base = receipt.as_dict()
        fingerprint = base.pop("receipt_fingerprint")
        _require_sha(fingerprint, "canonicalization receipt fingerprint")
        if _canonical_hash(base) != fingerprint:
            raise CanonicalBaselineError("canonicalization receipt fingerprint does not verify")

    @staticmethod
    def _require_text(value: str, label: str) -> None:
        if not isinstance(value, str) or not value.strip():
            raise ValueError(f"{label} must be non-empty text")
