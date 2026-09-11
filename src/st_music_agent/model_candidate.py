from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from enum import Enum
from typing import Any

from .learning_evaluation import (
    BenchmarkRun,
    LearningEvaluationGate,
    LearningEvaluationReport,
    PromotionDecision,
)
from .training_run import (
    TrainingRunCompletion,
    TrainingRunContractError,
    TrainingRunOutcome,
    TrainingRunSpec,
)

MODEL_CANDIDATE_SCHEMA_VERSION = "1.0.0"
PROMOTION_REVIEW_SCHEMA_VERSION = "1.0.0"
_SHA256 = re.compile(r"^[0-9a-f]{64}$")


class ModelCandidateError(RuntimeError):
    pass


class PromotionReviewDecision(str, Enum):
    ELIGIBLE_FOR_ACTIVATION_REVIEW = "eligible_for_activation_review"
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


def _verify_training_spec(spec: TrainingRunSpec) -> None:
    if spec.execution_authorized or spec.auto_start:
        raise TrainingRunContractError("training spec must not authorize or auto-start training")
    config_hash = _canonical_hash(dict(spec.trainer_config))
    if config_hash != spec.trainer_config_hash:
        raise TrainingRunContractError("trainer configuration hash does not verify")
    base = spec.as_dict()
    base.pop("input_fingerprint")
    if _canonical_hash(base) != spec.input_fingerprint:
        raise TrainingRunContractError("training input fingerprint does not verify")


def _verify_training_completion(
    spec: TrainingRunSpec,
    completion: TrainingRunCompletion,
) -> None:
    _verify_training_spec(spec)
    if completion.run_id != spec.run_id:
        raise ModelCandidateError("training completion run id does not match spec")
    if completion.input_fingerprint != spec.input_fingerprint:
        raise ModelCandidateError("training completion input fingerprint does not match spec")
    if completion.outcome is not TrainingRunOutcome.COMPLETED:
        raise ModelCandidateError("only completed training runs can register model candidates")
    if completion.checkpoint_sha256 is None or not _SHA256.fullmatch(
        completion.checkpoint_sha256
    ):
        raise ModelCandidateError("completed training run requires a valid checkpoint SHA-256")
    if not completion.authorization_ref.strip():
        raise ModelCandidateError("training completion requires an authorization reference")
    if not completion.evidence_refs or any(not ref.strip() for ref in completion.evidence_refs):
        raise ModelCandidateError("training completion requires evidence references")
    if not completion.evaluation_required:
        raise ModelCandidateError("training completion must require evaluation")
    if completion.promotion_authorized or completion.auto_promote:
        raise ModelCandidateError("training completion must not grant promotion authority")

    base = completion.as_dict()
    base.pop("completion_fingerprint")
    if _canonical_hash(base) != completion.completion_fingerprint:
        raise ModelCandidateError("training completion fingerprint does not verify")


@dataclass(frozen=True, slots=True)
class ModelCandidate:
    candidate_id: str
    checkpoint_sha256: str
    training_run_id: str
    training_input_fingerprint: str
    training_completion_fingerprint: str
    dataset_id: str
    dataset_manifest_hash: str
    base_model_id: str
    base_model_revision: str
    base_model_sha256: str
    lineage_fingerprint: str
    evaluation_required: bool = True
    activation_authorized: bool = False
    auto_activate: bool = False

    def as_dict(self) -> dict[str, Any]:
        return {
            "schema_version": MODEL_CANDIDATE_SCHEMA_VERSION,
            "candidate_id": self.candidate_id,
            "checkpoint_sha256": self.checkpoint_sha256,
            "training_run_id": self.training_run_id,
            "training_input_fingerprint": self.training_input_fingerprint,
            "training_completion_fingerprint": self.training_completion_fingerprint,
            "dataset_id": self.dataset_id,
            "dataset_manifest_hash": self.dataset_manifest_hash,
            "base_model_id": self.base_model_id,
            "base_model_revision": self.base_model_revision,
            "base_model_sha256": self.base_model_sha256,
            "lineage_fingerprint": self.lineage_fingerprint,
            "evaluation_required": self.evaluation_required,
            "activation_authorized": self.activation_authorized,
            "auto_activate": self.auto_activate,
        }


class ModelCandidateRegistry:
    """Host-side registry of immutable trained model candidate lineage."""

    def __init__(self) -> None:
        self._candidates: dict[str, ModelCandidate] = {}

    def register(
        self,
        spec: TrainingRunSpec,
        completion: TrainingRunCompletion,
    ) -> ModelCandidate:
        _verify_training_completion(spec, completion)
        checkpoint_sha256 = completion.checkpoint_sha256
        if checkpoint_sha256 is None:
            raise ModelCandidateError("completed training run has no checkpoint hash")

        lineage_base = {
            "schema_version": MODEL_CANDIDATE_SCHEMA_VERSION,
            "checkpoint_sha256": checkpoint_sha256,
            "training_run_id": spec.run_id,
            "training_input_fingerprint": spec.input_fingerprint,
            "training_completion_fingerprint": completion.completion_fingerprint,
            "dataset_id": spec.dataset_id,
            "dataset_manifest_hash": spec.dataset_manifest_hash,
            "base_model_id": spec.base_model_id,
            "base_model_revision": spec.base_model_revision,
            "base_model_sha256": spec.base_model_sha256,
            "evaluation_required": True,
            "activation_authorized": False,
            "auto_activate": False,
        }
        lineage_fingerprint = _canonical_hash(lineage_base)
        candidate_id = f"model:{lineage_fingerprint}"
        candidate = ModelCandidate(
            candidate_id=candidate_id,
            checkpoint_sha256=checkpoint_sha256,
            training_run_id=spec.run_id,
            training_input_fingerprint=spec.input_fingerprint,
            training_completion_fingerprint=completion.completion_fingerprint,
            dataset_id=spec.dataset_id,
            dataset_manifest_hash=spec.dataset_manifest_hash,
            base_model_id=spec.base_model_id,
            base_model_revision=spec.base_model_revision,
            base_model_sha256=spec.base_model_sha256,
            lineage_fingerprint=lineage_fingerprint,
            evaluation_required=True,
            activation_authorized=False,
            auto_activate=False,
        )

        existing = self._candidates.get(candidate_id)
        if existing is not None:
            if existing.as_dict() != candidate.as_dict():
                raise ModelCandidateError("model candidate id collision")
            return existing
        self._candidates[candidate_id] = candidate
        return candidate

    def get(self, candidate_id: str) -> ModelCandidate | None:
        return self._candidates.get(candidate_id)

    def candidates(self) -> tuple[ModelCandidate, ...]:
        return tuple(self._candidates[key] for key in sorted(self._candidates))


@dataclass(frozen=True, slots=True)
class PromotionReviewRecord:
    candidate_id: str
    checkpoint_sha256: str
    baseline_id: str
    evaluation_report_hash: str
    decision: PromotionReviewDecision
    reasons: tuple[str, ...]
    review_fingerprint: str
    human_review_required: bool = True
    activation_authorized: bool = False
    auto_activate: bool = False

    def as_dict(self) -> dict[str, Any]:
        return {
            "schema_version": PROMOTION_REVIEW_SCHEMA_VERSION,
            "candidate_id": self.candidate_id,
            "checkpoint_sha256": self.checkpoint_sha256,
            "baseline_id": self.baseline_id,
            "evaluation_report_hash": self.evaluation_report_hash,
            "decision": self.decision.value,
            "reasons": list(self.reasons),
            "review_fingerprint": self.review_fingerprint,
            "human_review_required": self.human_review_required,
            "activation_authorized": self.activation_authorized,
            "auto_activate": self.auto_activate,
        }


class ModelPromotionReviewGate:
    """Recomputes A16 evaluation before a trained candidate may reach activation review."""

    def __init__(self, evaluation_gate: LearningEvaluationGate | None = None) -> None:
        self.evaluation_gate = evaluation_gate or LearningEvaluationGate()

    def review(
        self,
        candidate: ModelCandidate,
        baseline_run: BenchmarkRun,
        candidate_run: BenchmarkRun,
        claimed_report: LearningEvaluationReport,
    ) -> PromotionReviewRecord:
        self._validate_candidate(candidate)
        if candidate_run.candidate_id != candidate.candidate_id:
            raise ModelCandidateError("benchmark candidate id does not match registered model")

        recomputed = self.evaluation_gate.compare(baseline_run, candidate_run)
        if claimed_report.as_dict() != recomputed.as_dict():
            raise ModelCandidateError("claimed evaluation report differs from recomputation")

        report_hash = _canonical_hash(recomputed.as_dict())
        decision = (
            PromotionReviewDecision.ELIGIBLE_FOR_ACTIVATION_REVIEW
            if recomputed.decision is PromotionDecision.ELIGIBLE_FOR_HOST_REVIEW
            else PromotionReviewDecision.REJECTED
        )
        reasons = recomputed.reasons
        review_base = {
            "schema_version": PROMOTION_REVIEW_SCHEMA_VERSION,
            "candidate_id": candidate.candidate_id,
            "checkpoint_sha256": candidate.checkpoint_sha256,
            "baseline_id": recomputed.baseline_id,
            "evaluation_report_hash": report_hash,
            "decision": decision.value,
            "reasons": list(reasons),
            "human_review_required": True,
            "activation_authorized": False,
            "auto_activate": False,
        }
        return PromotionReviewRecord(
            candidate_id=candidate.candidate_id,
            checkpoint_sha256=candidate.checkpoint_sha256,
            baseline_id=recomputed.baseline_id,
            evaluation_report_hash=report_hash,
            decision=decision,
            reasons=reasons,
            review_fingerprint=_canonical_hash(review_base),
            human_review_required=True,
            activation_authorized=False,
            auto_activate=False,
        )

    @staticmethod
    def _validate_candidate(candidate: ModelCandidate) -> None:
        if not candidate.evaluation_required:
            raise ModelCandidateError("model candidate must require evaluation")
        if candidate.activation_authorized or candidate.auto_activate:
            raise ModelCandidateError("model candidate must not grant activation authority")
        if not _SHA256.fullmatch(candidate.checkpoint_sha256):
            raise ModelCandidateError("model candidate checkpoint hash is invalid")

        base = candidate.as_dict()
        candidate_id = base.pop("candidate_id")
        lineage_fingerprint = base.pop("lineage_fingerprint")
        if _canonical_hash(base) != lineage_fingerprint:
            raise ModelCandidateError("model candidate lineage fingerprint does not verify")
        if candidate_id != f"model:{lineage_fingerprint}":
            raise ModelCandidateError("model candidate id does not match lineage fingerprint")
