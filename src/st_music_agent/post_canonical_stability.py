from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from enum import Enum
from typing import Any

from .canonical_baseline import (
    CanonicalizationOutcome,
    CanonicalizationReceipt,
    CanonicalizationReceiptBuilder,
)

POST_CANONICAL_STABILITY_SCHEMA_VERSION = "1.0.0"
POST_CANONICAL_STABILITY_POLICY_VERSION = "2026-09-11.v1"
POST_CANONICAL_MIN_ROUNDS = 3
_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_MODEL_ID = re.compile(r"^model:[0-9a-f]{64}$")


class PostCanonicalStabilityError(RuntimeError):
    pass


class PostCanonicalCheckKind(str, Enum):
    SERVING_IDENTITY = "serving_identity"
    HEALTH = "health"
    QUALITY = "quality"
    ROLLBACK_READINESS = "rollback_readiness"


class PostCanonicalCheckStatus(str, Enum):
    SUCCESS = "success"
    FAILURE = "failure"
    UNAVAILABLE = "unavailable"


class PostCanonicalStabilityDecision(str, Enum):
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


@dataclass(frozen=True, slots=True)
class PostCanonicalCheck:
    kind: PostCanonicalCheckKind
    status: PostCanonicalCheckStatus
    evidence_refs: tuple[str, ...]

    def __post_init__(self) -> None:
        if not self.evidence_refs or any(not ref.strip() for ref in self.evidence_refs):
            raise ValueError("post-canonical check requires non-empty evidence references")

    def as_dict(self) -> dict[str, Any]:
        return {
            "kind": self.kind.value,
            "status": self.status.value,
            "evidence_refs": list(self.evidence_refs),
        }


@dataclass(frozen=True, slots=True)
class PostCanonicalObservationRound:
    sequence: int
    observation_ref: str
    observed_model_id: str
    observed_checkpoint_sha256: str
    checks: tuple[PostCanonicalCheck, ...]

    def __post_init__(self) -> None:
        if self.sequence < 1:
            raise ValueError("post-canonical observation sequence must be positive")
        if not self.observation_ref.strip():
            raise ValueError("post-canonical observation_ref must be non-empty")
        if not _MODEL_ID.fullmatch(self.observed_model_id):
            raise ValueError("post-canonical observed model id is invalid")
        if not _SHA256.fullmatch(self.observed_checkpoint_sha256):
            raise ValueError("post-canonical observed checkpoint hash is invalid")

    def as_dict(self) -> dict[str, Any]:
        return {
            "sequence": self.sequence,
            "observation_ref": self.observation_ref,
            "observed_model_id": self.observed_model_id,
            "observed_checkpoint_sha256": self.observed_checkpoint_sha256,
            "checks": [check.as_dict() for check in self.checks],
        }


@dataclass(frozen=True, slots=True)
class PostCanonicalStabilityReport:
    policy_version: str
    canonicalization_receipt_fingerprint: str
    candidate_id: str
    candidate_checkpoint_sha256: str
    previous_canonical_id: str
    previous_canonical_checkpoint_sha256: str
    rollback_candidate_id: str
    rollback_checkpoint_sha256: str
    target_environment: str
    observation_rounds_fingerprint: str
    observation_round_count: int
    decision: PostCanonicalStabilityDecision
    reasons: tuple[str, ...]
    report_fingerprint: str
    host_registration_required: bool = True
    auto_register_baseline: bool = False
    auto_rollback: bool = False

    def as_dict(self) -> dict[str, Any]:
        return {
            "schema_version": POST_CANONICAL_STABILITY_SCHEMA_VERSION,
            "policy_version": self.policy_version,
            "canonicalization_receipt_fingerprint": self.canonicalization_receipt_fingerprint,
            "candidate_id": self.candidate_id,
            "candidate_checkpoint_sha256": self.candidate_checkpoint_sha256,
            "previous_canonical_id": self.previous_canonical_id,
            "previous_canonical_checkpoint_sha256": self.previous_canonical_checkpoint_sha256,
            "rollback_candidate_id": self.rollback_candidate_id,
            "rollback_checkpoint_sha256": self.rollback_checkpoint_sha256,
            "target_environment": self.target_environment,
            "observation_rounds_fingerprint": self.observation_rounds_fingerprint,
            "observation_round_count": self.observation_round_count,
            "decision": self.decision.value,
            "reasons": list(self.reasons),
            "report_fingerprint": self.report_fingerprint,
            "host_registration_required": self.host_registration_required,
            "auto_register_baseline": self.auto_register_baseline,
            "auto_rollback": self.auto_rollback,
        }


class PostCanonicalStabilityGate:
    """Revalidates an A23 canonicalization across repeated runtime evidence rounds."""

    _REQUIRED_KINDS = frozenset(PostCanonicalCheckKind)

    def evaluate(
        self,
        receipt: CanonicalizationReceipt,
        rounds: tuple[PostCanonicalObservationRound, ...],
    ) -> PostCanonicalStabilityReport:
        CanonicalizationReceiptBuilder.verify(receipt)
        if receipt.outcome is not CanonicalizationOutcome.CANONICALIZED:
            raise PostCanonicalStabilityError(
                "post-canonical stability requires a canonicalized receipt"
            )
        if not receipt.post_canonical_health_required:
            raise PostCanonicalStabilityError(
                "canonicalized receipt must require post-canonical health"
            )
        if len(rounds) < POST_CANONICAL_MIN_ROUNDS:
            raise PostCanonicalStabilityError(
                f"post-canonical stability requires at least {POST_CANONICAL_MIN_ROUNDS} rounds"
            )

        ordered_rounds = tuple(sorted(rounds, key=lambda item: item.sequence))
        expected_sequences = tuple(range(1, len(ordered_rounds) + 1))
        if tuple(item.sequence for item in ordered_rounds) != expected_sequences:
            raise PostCanonicalStabilityError(
                "post-canonical observation sequences must be contiguous from one"
            )
        observation_refs = tuple(item.observation_ref for item in ordered_rounds)
        if len(set(observation_refs)) != len(observation_refs):
            raise PostCanonicalStabilityError("post-canonical observation refs must be unique")

        reasons: list[str] = []
        normalized_rounds: list[dict[str, Any]] = []
        for observation in ordered_rounds:
            check_map: dict[PostCanonicalCheckKind, PostCanonicalCheck] = {}
            for check in observation.checks:
                if check.kind in check_map:
                    raise PostCanonicalStabilityError(
                        "post-canonical check kinds must be unique within each round"
                    )
                check_map[check.kind] = check
            if set(check_map) != self._REQUIRED_KINDS:
                raise PostCanonicalStabilityError(
                    "post-canonical rounds must cover the exact required check kinds"
                )
            ordered_checks = tuple(check_map[kind] for kind in PostCanonicalCheckKind)
            if observation.observed_model_id != receipt.candidate_id:
                reasons.append(f"round {observation.sequence} observed wrong model")
            if observation.observed_checkpoint_sha256 != receipt.candidate_checkpoint_sha256:
                reasons.append(f"round {observation.sequence} observed wrong checkpoint")
            for check in ordered_checks:
                if check.status is PostCanonicalCheckStatus.FAILURE:
                    reasons.append(
                        f"round {observation.sequence} {check.kind.value} failed"
                    )
                elif check.status is PostCanonicalCheckStatus.UNAVAILABLE:
                    reasons.append(
                        f"round {observation.sequence} {check.kind.value} unavailable"
                    )
            normalized_rounds.append(
                {
                    "sequence": observation.sequence,
                    "observation_ref": observation.observation_ref,
                    "observed_model_id": observation.observed_model_id,
                    "observed_checkpoint_sha256": observation.observed_checkpoint_sha256,
                    "checks": [check.as_dict() for check in ordered_checks],
                }
            )

        rounds_fingerprint = _canonical_hash(normalized_rounds)
        decision = (
            PostCanonicalStabilityDecision.ELIGIBLE_FOR_BASELINE_REGISTRATION
            if not reasons
            else PostCanonicalStabilityDecision.REJECTED
        )
        base = {
            "schema_version": POST_CANONICAL_STABILITY_SCHEMA_VERSION,
            "policy_version": POST_CANONICAL_STABILITY_POLICY_VERSION,
            "canonicalization_receipt_fingerprint": receipt.receipt_fingerprint,
            "candidate_id": receipt.candidate_id,
            "candidate_checkpoint_sha256": receipt.candidate_checkpoint_sha256,
            "previous_canonical_id": receipt.previous_canonical_id,
            "previous_canonical_checkpoint_sha256": (
                receipt.previous_canonical_checkpoint_sha256
            ),
            "rollback_candidate_id": receipt.rollback_candidate_id,
            "rollback_checkpoint_sha256": receipt.rollback_checkpoint_sha256,
            "target_environment": receipt.target_environment,
            "observation_rounds_fingerprint": rounds_fingerprint,
            "observation_round_count": len(ordered_rounds),
            "decision": decision.value,
            "reasons": reasons,
            "host_registration_required": True,
            "auto_register_baseline": False,
            "auto_rollback": False,
        }
        return PostCanonicalStabilityReport(
            policy_version=POST_CANONICAL_STABILITY_POLICY_VERSION,
            canonicalization_receipt_fingerprint=receipt.receipt_fingerprint,
            candidate_id=receipt.candidate_id,
            candidate_checkpoint_sha256=receipt.candidate_checkpoint_sha256,
            previous_canonical_id=receipt.previous_canonical_id,
            previous_canonical_checkpoint_sha256=receipt.previous_canonical_checkpoint_sha256,
            rollback_candidate_id=receipt.rollback_candidate_id,
            rollback_checkpoint_sha256=receipt.rollback_checkpoint_sha256,
            target_environment=receipt.target_environment,
            observation_rounds_fingerprint=rounds_fingerprint,
            observation_round_count=len(ordered_rounds),
            decision=decision,
            reasons=tuple(reasons),
            report_fingerprint=_canonical_hash(base),
            host_registration_required=True,
            auto_register_baseline=False,
            auto_rollback=False,
        )

    def verify(
        self,
        receipt: CanonicalizationReceipt,
        rounds: tuple[PostCanonicalObservationRound, ...],
        report: PostCanonicalStabilityReport,
    ) -> None:
        recomputed = self.evaluate(receipt, rounds)
        if recomputed.as_dict() != report.as_dict():
            raise PostCanonicalStabilityError(
                "post-canonical stability report differs from recomputation"
            )
        if not report.host_registration_required:
            raise PostCanonicalStabilityError("post-canonical report must require host registration")
        if report.auto_register_baseline or report.auto_rollback:
            raise PostCanonicalStabilityError(
                "post-canonical report cannot authorize automatic registry or rollback actions"
            )
