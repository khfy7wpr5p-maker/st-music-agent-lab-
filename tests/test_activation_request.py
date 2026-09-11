from __future__ import annotations

import hashlib
import json
from dataclasses import replace

import pytest

from st_music_agent.activation_request import (
    ACTIVATION_REQUEST_SCHEMA_VERSION,
    ActivationRequestBuilder,
    ActivationRequestError,
)
from st_music_agent.model_candidate import (
    MODEL_CANDIDATE_SCHEMA_VERSION,
    PROMOTION_REVIEW_SCHEMA_VERSION,
    ModelCandidate,
    PromotionReviewDecision,
    PromotionReviewRecord,
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


def _candidate() -> ModelCandidate:
    base = {
        "schema_version": MODEL_CANDIDATE_SCHEMA_VERSION,
        "checkpoint_sha256": "1" * 64,
        "training_run_id": "train:model:v1",
        "training_input_fingerprint": "2" * 64,
        "training_completion_fingerprint": "3" * 64,
        "dataset_id": "dataset-v1",
        "dataset_manifest_hash": "4" * 64,
        "base_model_id": "open-model/base",
        "base_model_revision": "v1",
        "base_model_sha256": "5" * 64,
        "evaluation_required": True,
        "activation_authorized": False,
        "auto_activate": False,
    }
    lineage = _hash(base)
    return ModelCandidate(
        candidate_id=f"model:{lineage}",
        checkpoint_sha256="1" * 64,
        training_run_id="train:model:v1",
        training_input_fingerprint="2" * 64,
        training_completion_fingerprint="3" * 64,
        dataset_id="dataset-v1",
        dataset_manifest_hash="4" * 64,
        base_model_id="open-model/base",
        base_model_revision="v1",
        base_model_sha256="5" * 64,
        lineage_fingerprint=lineage,
        evaluation_required=True,
        activation_authorized=False,
        auto_activate=False,
    )


def _review(candidate: ModelCandidate) -> PromotionReviewRecord:
    baseline_id = f"model:{'a' * 64}"
    base = {
        "schema_version": PROMOTION_REVIEW_SCHEMA_VERSION,
        "candidate_id": candidate.candidate_id,
        "checkpoint_sha256": candidate.checkpoint_sha256,
        "baseline_id": baseline_id,
        "evaluation_report_hash": "6" * 64,
        "decision": PromotionReviewDecision.ELIGIBLE_FOR_ACTIVATION_REVIEW.value,
        "reasons": [],
        "human_review_required": True,
        "activation_authorized": False,
        "auto_activate": False,
    }
    return PromotionReviewRecord(
        candidate_id=candidate.candidate_id,
        checkpoint_sha256=candidate.checkpoint_sha256,
        baseline_id=baseline_id,
        evaluation_report_hash="6" * 64,
        decision=PromotionReviewDecision.ELIGIBLE_FOR_ACTIVATION_REVIEW,
        reasons=(),
        review_fingerprint=_hash(base),
        human_review_required=True,
        activation_authorized=False,
        auto_activate=False,
    )


def test_activation_request_binds_candidate_review_baseline_and_rollback() -> None:
    candidate = _candidate()
    review = _review(candidate)
    baseline_checkpoint = "b" * 64

    request = ActivationRequestBuilder().build(
        candidate,
        review,
        current_baseline_id=review.baseline_id,
        current_baseline_checkpoint_sha256=baseline_checkpoint,
        rollback_candidate_id=review.baseline_id,
        rollback_checkpoint_sha256=baseline_checkpoint,
        target_environment="shadow-prod",
    )

    assert request.request_id == f"activation:{request.request_fingerprint}"
    assert request.candidate_id == candidate.candidate_id
    assert request.rollback_candidate_id == request.current_baseline_id
    assert request.rollback_checkpoint_sha256 == request.current_baseline_checkpoint_sha256
    assert request.human_approval_required is True
    assert request.activation_authorized is False
    assert request.auto_activate is False
    assert request.canonicalization_authorized is False
    assert request.as_dict()["schema_version"] == ACTIVATION_REQUEST_SCHEMA_VERSION
    ActivationRequestBuilder.verify(request)


def test_rejected_review_or_mismatched_baseline_fails_closed() -> None:
    candidate = _candidate()
    review = _review(candidate)
    rejected = replace(review, decision=PromotionReviewDecision.REJECTED)

    with pytest.raises(ActivationRequestError, match="not eligible"):
        ActivationRequestBuilder().build(
            candidate,
            rejected,
            current_baseline_id=review.baseline_id,
            current_baseline_checkpoint_sha256="b" * 64,
            rollback_candidate_id=review.baseline_id,
            rollback_checkpoint_sha256="b" * 64,
            target_environment="shadow",
        )

    with pytest.raises(ActivationRequestError, match="not the current baseline"):
        ActivationRequestBuilder().build(
            candidate,
            review,
            current_baseline_id=f"model:{'c' * 64}",
            current_baseline_checkpoint_sha256="b" * 64,
            rollback_candidate_id=f"model:{'c' * 64}",
            rollback_checkpoint_sha256="b" * 64,
            target_environment="shadow",
        )


def test_rollback_must_be_exact_current_baseline() -> None:
    candidate = _candidate()
    review = _review(candidate)

    with pytest.raises(ActivationRequestError, match="rollback candidate"):
        ActivationRequestBuilder().build(
            candidate,
            review,
            current_baseline_id=review.baseline_id,
            current_baseline_checkpoint_sha256="b" * 64,
            rollback_candidate_id=f"model:{'c' * 64}",
            rollback_checkpoint_sha256="b" * 64,
            target_environment="shadow",
        )

    with pytest.raises(ActivationRequestError, match="rollback checkpoint"):
        ActivationRequestBuilder().build(
            candidate,
            review,
            current_baseline_id=review.baseline_id,
            current_baseline_checkpoint_sha256="b" * 64,
            rollback_candidate_id=review.baseline_id,
            rollback_checkpoint_sha256="c" * 64,
            target_environment="shadow",
        )


def test_tampered_candidate_review_or_request_fails_closed() -> None:
    candidate = _candidate()
    review = _review(candidate)
    builder = ActivationRequestBuilder()

    with pytest.raises(ActivationRequestError, match="lineage fingerprint"):
        builder.build(
            replace(candidate, checkpoint_sha256="9" * 64),
            review,
            current_baseline_id=review.baseline_id,
            current_baseline_checkpoint_sha256="b" * 64,
            rollback_candidate_id=review.baseline_id,
            rollback_checkpoint_sha256="b" * 64,
            target_environment="shadow",
        )

    with pytest.raises(ActivationRequestError, match="fingerprint"):
        builder.build(
            candidate,
            replace(review, evaluation_report_hash="8" * 64),
            current_baseline_id=review.baseline_id,
            current_baseline_checkpoint_sha256="b" * 64,
            rollback_candidate_id=review.baseline_id,
            rollback_checkpoint_sha256="b" * 64,
            target_environment="shadow",
        )

    request = builder.build(
        candidate,
        review,
        current_baseline_id=review.baseline_id,
        current_baseline_checkpoint_sha256="b" * 64,
        rollback_candidate_id=review.baseline_id,
        rollback_checkpoint_sha256="b" * 64,
        target_environment="shadow",
    )
    with pytest.raises(ActivationRequestError, match="must not authorize activation"):
        builder.verify(replace(request, activation_authorized=True))
    with pytest.raises(ActivationRequestError, match="fingerprint"):
        builder.verify(replace(request, target_environment="different"))
