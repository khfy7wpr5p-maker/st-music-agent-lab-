from __future__ import annotations

import hashlib
import json
from dataclasses import replace

import pytest

from st_music_agent.activation_receipt import ActivationReceiptBuilder, ActivationReceiptOutcome
from st_music_agent.activation_request import ActivationRequestBuilder
from st_music_agent.canonical_baseline import (
    CanonicalBaselineError,
    CanonicalBaselineReviewGate,
    CanonicalReviewDecision,
    CanonicalizationOutcome,
    CanonicalizationReceiptBuilder,
)
from st_music_agent.model_candidate import (
    MODEL_CANDIDATE_SCHEMA_VERSION,
    PROMOTION_REVIEW_SCHEMA_VERSION,
    ModelCandidate,
    PromotionReviewDecision,
    PromotionReviewRecord,
)
from st_music_agent.shadow_health import (
    RuntimeCheck,
    RuntimeCheckKind,
    RuntimeCheckStatus,
    ShadowHealthDecision,
    ShadowHealthGate,
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
    )


def _promotion_review(candidate: ModelCandidate) -> PromotionReviewRecord:
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
    )


def _activated_receipt():
    candidate = _candidate()
    promotion = _promotion_review(candidate)
    request = ActivationRequestBuilder().build(
        candidate,
        promotion,
        current_baseline_id=promotion.baseline_id,
        current_baseline_checkpoint_sha256="b" * 64,
        rollback_candidate_id=promotion.baseline_id,
        rollback_checkpoint_sha256="b" * 64,
        target_environment="shadow-prod",
    )
    receipt = ActivationReceiptBuilder().bind(
        request,
        outcome=ActivationReceiptOutcome.ACTIVATED,
        host_authorization_ref="host-approval:activation:1",
        deployment_ref="deployment:shadow-prod:42",
        evidence_refs=("deploy-log:42", "serving-probe:42"),
        observed_model_id=request.candidate_id,
        observed_checkpoint_sha256=request.candidate_checkpoint_sha256,
    )
    return receipt


def _checks(status: RuntimeCheckStatus = RuntimeCheckStatus.SUCCESS) -> tuple[RuntimeCheck, ...]:
    return tuple(
        RuntimeCheck(kind, status, (f"evidence:{kind.value}",)) for kind in RuntimeCheckKind
    )


def _eligible_review():
    receipt = _activated_receipt()
    checks = _checks()
    shadow = ShadowHealthGate().evaluate(receipt, checks)
    review = CanonicalBaselineReviewGate().review(
        receipt,
        checks,
        shadow,
        current_canonical_id=receipt.previous_baseline_id,
        current_canonical_checkpoint_sha256=receipt.previous_baseline_checkpoint_sha256,
    )
    return receipt, checks, shadow, review


def test_canonical_review_recomputes_a22_and_only_opens_host_review() -> None:
    receipt, checks, shadow, review = _eligible_review()

    assert shadow.decision is ShadowHealthDecision.ELIGIBLE_FOR_CANONICAL_REVIEW
    assert review.decision is CanonicalReviewDecision.ELIGIBLE_FOR_HOST_CANONICALIZATION
    assert review.candidate_id == receipt.candidate_id
    assert review.current_canonical_id == receipt.previous_baseline_id
    assert review.rollback_candidate_id == review.current_canonical_id
    assert review.human_approval_required is True
    assert review.canonicalization_authorized is False
    assert review.auto_canonicalize is False
    CanonicalBaselineReviewGate().verify_with_evidence(receipt, checks, shadow, review)


def test_shadow_failure_or_baseline_drift_rejects_canonical_review() -> None:
    receipt = _activated_receipt()
    checks = list(_checks())
    checks[1] = replace(checks[1], status=RuntimeCheckStatus.FAILURE)
    checks = tuple(checks)
    shadow = ShadowHealthGate().evaluate(receipt, checks)

    failed = CanonicalBaselineReviewGate().review(
        receipt,
        checks,
        shadow,
        current_canonical_id=receipt.previous_baseline_id,
        current_canonical_checkpoint_sha256=receipt.previous_baseline_checkpoint_sha256,
    )
    assert failed.decision is CanonicalReviewDecision.REJECTED
    assert "shadow health is not eligible for canonical review" in failed.reasons

    success_checks = _checks()
    success_shadow = ShadowHealthGate().evaluate(receipt, success_checks)
    drifted = CanonicalBaselineReviewGate().review(
        receipt,
        success_checks,
        success_shadow,
        current_canonical_id=f"model:{'c' * 64}",
        current_canonical_checkpoint_sha256="d" * 64,
    )
    assert drifted.decision is CanonicalReviewDecision.REJECTED
    assert any("differs from activation baseline" in reason for reason in drifted.reasons)


def test_forged_review_cannot_create_canonicalization_receipt() -> None:
    receipt, checks, shadow, review = _eligible_review()
    forged = replace(review, shadow_health_report_fingerprint="f" * 64)

    with pytest.raises(CanonicalBaselineError, match="recomputation"):
        CanonicalizationReceiptBuilder().bind(
            receipt,
            checks,
            shadow,
            forged,
            outcome=CanonicalizationOutcome.CANONICALIZED,
            host_authorization_ref="host-approval:canonical:1",
            canonicalization_ref="baseline-switch:1",
            evidence_refs=("baseline-registry:1",),
            observed_canonical_id=review.candidate_id,
            observed_canonical_checkpoint_sha256=review.candidate_checkpoint_sha256,
        )


def test_canonicalized_receipt_binds_old_new_baselines_and_requires_post_health() -> None:
    receipt, checks, shadow, review = _eligible_review()
    result = CanonicalizationReceiptBuilder().bind(
        receipt,
        checks,
        shadow,
        review,
        outcome=CanonicalizationOutcome.CANONICALIZED,
        host_authorization_ref="host-approval:canonical:1",
        canonicalization_ref="baseline-switch:1",
        evidence_refs=("baseline-registry:1", "serving-registry:1"),
        observed_canonical_id=review.candidate_id,
        observed_canonical_checkpoint_sha256=review.candidate_checkpoint_sha256,
    )

    assert result.previous_canonical_id == review.current_canonical_id
    assert result.candidate_id == review.candidate_id
    assert result.observed_canonical_id == review.candidate_id
    assert result.rollback_candidate_id == result.previous_canonical_id
    assert result.post_canonical_health_required is True
    assert result.auto_rollback is False
    assert result.auto_canonicalize is False
    CanonicalizationReceiptBuilder.verify(result)


def test_rejected_review_or_wrong_observation_fails_closed() -> None:
    receipt, checks, shadow, review = _eligible_review()
    rejected = replace(review, decision=CanonicalReviewDecision.REJECTED)

    with pytest.raises(CanonicalBaselineError):
        CanonicalizationReceiptBuilder().bind(
            receipt,
            checks,
            shadow,
            rejected,
            outcome=CanonicalizationOutcome.CANONICALIZED,
            host_authorization_ref="host-approval:canonical:2",
            canonicalization_ref="baseline-switch:2",
            evidence_refs=("registry:2",),
            observed_canonical_id=review.candidate_id,
            observed_canonical_checkpoint_sha256=review.candidate_checkpoint_sha256,
        )

    with pytest.raises(CanonicalBaselineError, match="does not match candidate"):
        CanonicalizationReceiptBuilder().bind(
            receipt,
            checks,
            shadow,
            review,
            outcome=CanonicalizationOutcome.CANONICALIZED,
            host_authorization_ref="host-approval:canonical:3",
            canonicalization_ref="baseline-switch:3",
            evidence_refs=("registry:3",),
            observed_canonical_id=review.current_canonical_id,
            observed_canonical_checkpoint_sha256=review.current_canonical_checkpoint_sha256,
        )


def test_failed_or_rolled_back_receipts_preserve_previous_baseline() -> None:
    receipt, checks, shadow, review = _eligible_review()
    builder = CanonicalizationReceiptBuilder()

    failed = builder.bind(
        receipt,
        checks,
        shadow,
        review,
        outcome=CanonicalizationOutcome.FAILED,
        host_authorization_ref="host-approval:canonical:4",
        canonicalization_ref="baseline-switch:failed",
        evidence_refs=("registry:failed",),
        observed_canonical_id=review.current_canonical_id,
        observed_canonical_checkpoint_sha256=review.current_canonical_checkpoint_sha256,
    )
    assert failed.post_canonical_health_required is False
    builder.verify(failed)

    rolled_back = builder.bind(
        receipt,
        checks,
        shadow,
        review,
        outcome=CanonicalizationOutcome.ROLLED_BACK,
        host_authorization_ref="host-approval:canonical:5",
        canonicalization_ref="baseline-switch:rollback",
        evidence_refs=("registry:rollback",),
        observed_canonical_id=review.rollback_candidate_id,
        observed_canonical_checkpoint_sha256=review.rollback_checkpoint_sha256,
    )
    assert rolled_back.observed_canonical_id == review.current_canonical_id
    assert rolled_back.post_canonical_health_required is False
    builder.verify(rolled_back)


def test_receipt_tampering_or_automatic_authority_is_rejected() -> None:
    receipt, checks, shadow, review = _eligible_review()
    result = CanonicalizationReceiptBuilder().bind(
        receipt,
        checks,
        shadow,
        review,
        outcome=CanonicalizationOutcome.CANONICALIZED,
        host_authorization_ref="host-approval:canonical:6",
        canonicalization_ref="baseline-switch:6",
        evidence_refs=("registry:6",),
        observed_canonical_id=review.candidate_id,
        observed_canonical_checkpoint_sha256=review.candidate_checkpoint_sha256,
    )

    with pytest.raises(CanonicalBaselineError, match="automatic actions"):
        CanonicalizationReceiptBuilder.verify(replace(result, auto_canonicalize=True))
    with pytest.raises(CanonicalBaselineError, match="fingerprint"):
        CanonicalizationReceiptBuilder.verify(replace(result, canonicalization_ref="changed"))
