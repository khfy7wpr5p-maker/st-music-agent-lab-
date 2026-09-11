from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from typing import Any

from .model_candidate import (
    MODEL_CANDIDATE_SCHEMA_VERSION,
    PROMOTION_REVIEW_SCHEMA_VERSION,
    ModelCandidate,
    ModelCandidateError,
    PromotionReviewDecision,
    PromotionReviewRecord,
)

ACTIVATION_REQUEST_SCHEMA_VERSION = "1.0.0"
_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_MODEL_ID = re.compile(r"^model:[0-9a-f]{64}$")
_ENVIRONMENT = re.compile(r"^[a-z0-9][a-z0-9_.-]{0,63}$")


class ActivationRequestError(RuntimeError):
    pass


def _canonical_hash(value: Any) -> str:
    encoded = json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _verify_candidate(candidate: ModelCandidate) -> None:
    if not candidate.evaluation_required:
        raise ActivationRequestError("model candidate must require evaluation")
    if candidate.activation_authorized or candidate.auto_activate:
        raise ActivationRequestError("model candidate must not carry activation authority")
    if not _SHA256.fullmatch(candidate.checkpoint_sha256):
        raise ActivationRequestError("candidate checkpoint hash is invalid")

    base = candidate.as_dict()
    candidate_id = base.pop("candidate_id")
    lineage_fingerprint = base.pop("lineage_fingerprint")
    if base.get("schema_version") != MODEL_CANDIDATE_SCHEMA_VERSION:
        raise ActivationRequestError("model candidate schema is unsupported")
    if _canonical_hash(base) != lineage_fingerprint:
        raise ActivationRequestError("model candidate lineage fingerprint does not verify")
    if candidate_id != f"model:{lineage_fingerprint}":
        raise ActivationRequestError("model candidate id does not match lineage fingerprint")


def _verify_review(review: PromotionReviewRecord) -> None:
    if review.decision is not PromotionReviewDecision.ELIGIBLE_FOR_ACTIVATION_REVIEW:
        raise ActivationRequestError("promotion review is not eligible for activation review")
    if not review.human_review_required:
        raise ActivationRequestError("promotion review must require human review")
    if review.activation_authorized or review.auto_activate:
        raise ActivationRequestError("promotion review must not grant activation authority")

    base = review.as_dict()
    review_fingerprint = base.pop("review_fingerprint")
    if base.get("schema_version") != PROMOTION_REVIEW_SCHEMA_VERSION:
        raise ActivationRequestError("promotion review schema is unsupported")
    if _canonical_hash(base) != review_fingerprint:
        raise ActivationRequestError("promotion review fingerprint does not verify")


@dataclass(frozen=True, slots=True)
class ActivationRequest:
    request_id: str
    candidate_id: str
    candidate_checkpoint_sha256: str
    promotion_review_fingerprint: str
    current_baseline_id: str
    current_baseline_checkpoint_sha256: str
    rollback_candidate_id: str
    rollback_checkpoint_sha256: str
    target_environment: str
    request_fingerprint: str
    human_approval_required: bool = True
    activation_authorized: bool = False
    auto_activate: bool = False
    canonicalization_authorized: bool = False

    def as_dict(self) -> dict[str, Any]:
        return {
            "schema_version": ACTIVATION_REQUEST_SCHEMA_VERSION,
            "request_id": self.request_id,
            "candidate_id": self.candidate_id,
            "candidate_checkpoint_sha256": self.candidate_checkpoint_sha256,
            "promotion_review_fingerprint": self.promotion_review_fingerprint,
            "current_baseline_id": self.current_baseline_id,
            "current_baseline_checkpoint_sha256": self.current_baseline_checkpoint_sha256,
            "rollback_candidate_id": self.rollback_candidate_id,
            "rollback_checkpoint_sha256": self.rollback_checkpoint_sha256,
            "target_environment": self.target_environment,
            "request_fingerprint": self.request_fingerprint,
            "human_approval_required": self.human_approval_required,
            "activation_authorized": self.activation_authorized,
            "auto_activate": self.auto_activate,
            "canonicalization_authorized": self.canonicalization_authorized,
        }


class ActivationRequestBuilder:
    """Creates reviewable activation requests without activating or deploying a model."""

    def build(
        self,
        candidate: ModelCandidate,
        review: PromotionReviewRecord,
        *,
        current_baseline_id: str,
        current_baseline_checkpoint_sha256: str,
        rollback_candidate_id: str,
        rollback_checkpoint_sha256: str,
        target_environment: str,
    ) -> ActivationRequest:
        _verify_candidate(candidate)
        _verify_review(review)

        if review.candidate_id != candidate.candidate_id:
            raise ActivationRequestError("promotion review candidate does not match model candidate")
        if review.checkpoint_sha256 != candidate.checkpoint_sha256:
            raise ActivationRequestError("promotion review checkpoint does not match model candidate")
        if review.baseline_id != current_baseline_id:
            raise ActivationRequestError("promotion review baseline is not the current baseline")
        if not _MODEL_ID.fullmatch(current_baseline_id):
            raise ValueError("current_baseline_id must be a model candidate id")
        if not _SHA256.fullmatch(current_baseline_checkpoint_sha256):
            raise ValueError("current baseline checkpoint hash is invalid")
        if rollback_candidate_id != current_baseline_id:
            raise ActivationRequestError("rollback candidate must equal the current baseline")
        if rollback_checkpoint_sha256 != current_baseline_checkpoint_sha256:
            raise ActivationRequestError("rollback checkpoint must equal the current baseline checkpoint")
        if not _SHA256.fullmatch(rollback_checkpoint_sha256):
            raise ValueError("rollback checkpoint hash is invalid")
        if not _ENVIRONMENT.fullmatch(target_environment):
            raise ValueError("target_environment has an invalid format")

        base = {
            "schema_version": ACTIVATION_REQUEST_SCHEMA_VERSION,
            "candidate_id": candidate.candidate_id,
            "candidate_checkpoint_sha256": candidate.checkpoint_sha256,
            "promotion_review_fingerprint": review.review_fingerprint,
            "current_baseline_id": current_baseline_id,
            "current_baseline_checkpoint_sha256": current_baseline_checkpoint_sha256,
            "rollback_candidate_id": rollback_candidate_id,
            "rollback_checkpoint_sha256": rollback_checkpoint_sha256,
            "target_environment": target_environment,
            "human_approval_required": True,
            "activation_authorized": False,
            "auto_activate": False,
            "canonicalization_authorized": False,
        }
        request_fingerprint = _canonical_hash(base)
        return ActivationRequest(
            request_id=f"activation:{request_fingerprint}",
            candidate_id=candidate.candidate_id,
            candidate_checkpoint_sha256=candidate.checkpoint_sha256,
            promotion_review_fingerprint=review.review_fingerprint,
            current_baseline_id=current_baseline_id,
            current_baseline_checkpoint_sha256=current_baseline_checkpoint_sha256,
            rollback_candidate_id=rollback_candidate_id,
            rollback_checkpoint_sha256=rollback_checkpoint_sha256,
            target_environment=target_environment,
            request_fingerprint=request_fingerprint,
            human_approval_required=True,
            activation_authorized=False,
            auto_activate=False,
            canonicalization_authorized=False,
        )

    @staticmethod
    def verify(request: ActivationRequest) -> None:
        if not request.human_approval_required:
            raise ActivationRequestError("activation request must require human approval")
        if request.activation_authorized or request.auto_activate:
            raise ActivationRequestError("activation request must not authorize activation")
        if request.canonicalization_authorized:
            raise ActivationRequestError("activation request must not authorize canonicalization")
        if request.rollback_candidate_id != request.current_baseline_id:
            raise ActivationRequestError("activation request rollback candidate is invalid")
        if request.rollback_checkpoint_sha256 != request.current_baseline_checkpoint_sha256:
            raise ActivationRequestError("activation request rollback checkpoint is invalid")

        base = request.as_dict()
        request_id = base.pop("request_id")
        request_fingerprint = base.pop("request_fingerprint")
        if _canonical_hash(base) != request_fingerprint:
            raise ActivationRequestError("activation request fingerprint does not verify")
        if request_id != f"activation:{request_fingerprint}":
            raise ActivationRequestError("activation request id does not match fingerprint")
