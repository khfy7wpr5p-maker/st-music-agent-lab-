from __future__ import annotations

import hashlib
import json
from dataclasses import replace

import pytest

from st_music_agent.activation_receipt import (
    ActivationReceiptBuilder,
    ActivationReceiptError,
    ActivationReceiptOutcome,
)
from st_music_agent.activation_request import ActivationRequestBuilder
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
    ShadowHealthError,
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


def _request():
    candidate = _candidate()
    review = _review(candidate)
    request = ActivationRequestBuilder().build(
        candidate,
        review,
        current_baseline_id=review.baseline_id,
        current_baseline_checkpoint_sha256="b" * 64,
        rollback_candidate_id=review.baseline_id,
        rollback_checkpoint_sha256="b" * 64,
        target_environment="shadow-prod",
    )
    return request


def _activated_receipt():
    request = _request()
    return ActivationReceiptBuilder().bind(
        request,
        outcome=ActivationReceiptOutcome.ACTIVATED,
        host_authorization_ref="host-approval:activation:1",
        deployment_ref="deployment:shadow-prod:42",
        evidence_refs=("deploy-log:42", "serving-probe:42"),
        observed_model_id=request.candidate_id,
        observed_checkpoint_sha256=request.candidate_checkpoint_sha256,
    )


def _success_checks() -> tuple[RuntimeCheck, ...]:
    return tuple(
        RuntimeCheck(kind, RuntimeCheckStatus.SUCCESS, (f"evidence:{kind.value}",))
        for kind in RuntimeCheckKind
    )


def test_activation_receipt_binds_exact_request_serving_identity_and_rollback() -> None:
    request = _request()
    receipt = _activated_receipt()

    assert receipt.request_fingerprint == request.request_fingerprint
    assert receipt.candidate_id == request.candidate_id
    assert receipt.observed_model_id == request.candidate_id
    assert receipt.observed_checkpoint_sha256 == request.candidate_checkpoint_sha256
    assert receipt.rollback_candidate_id == request.current_baseline_id
    assert receipt.rollback_checkpoint_sha256 == request.current_baseline_checkpoint_sha256
    assert receipt.shadow_health_required is True
    assert receipt.canonicalization_authorized is False
    assert receipt.auto_canonicalize is False
    ActivationReceiptBuilder.verify(receipt)


def test_failed_and_rolled_back_activation_receipts_fail_closed_on_false_serving_claims() -> None:
    request = _request()
    builder = ActivationReceiptBuilder()

    with pytest.raises(ActivationReceiptError, match="failed activation"):
        builder.bind(
            request,
            outcome=ActivationReceiptOutcome.FAILED,
            host_authorization_ref="host-approval:activation:2",
            deployment_ref="deployment:failed:2",
            evidence_refs=("deploy-log:failed",),
            observed_model_id=request.candidate_id,
            observed_checkpoint_sha256=request.candidate_checkpoint_sha256,
        )

    rolled_back = builder.bind(
        request,
        outcome=ActivationReceiptOutcome.ROLLED_BACK,
        host_authorization_ref="host-approval:activation:3",
        deployment_ref="deployment:rollback:3",
        evidence_refs=("rollback-log:3",),
        observed_model_id=request.rollback_candidate_id,
        observed_checkpoint_sha256=request.rollback_checkpoint_sha256,
    )
    assert rolled_back.shadow_health_required is False
    builder.verify(rolled_back)


def test_activation_receipt_tampering_or_authority_escalation_is_rejected() -> None:
    receipt = _activated_receipt()
    builder = ActivationReceiptBuilder()

    with pytest.raises(ActivationReceiptError, match="cannot authorize canonicalization"):
        builder.verify(replace(receipt, canonicalization_authorized=True))
    with pytest.raises(ActivationReceiptError, match="fingerprint"):
        builder.verify(replace(receipt, deployment_ref="deployment:changed"))


def test_shadow_health_all_success_is_only_eligible_for_canonical_review() -> None:
    receipt = _activated_receipt()
    checks = _success_checks()
    gate = ShadowHealthGate()
    report = gate.evaluate(receipt, checks)

    assert report.decision is ShadowHealthDecision.ELIGIBLE_FOR_CANONICAL_REVIEW
    assert report.reasons == ()
    assert report.human_review_required is True
    assert report.canonicalization_authorized is False
    assert report.auto_canonicalize is False
    assert report.rollback_candidate_id == receipt.rollback_candidate_id
    gate.verify(receipt, checks, report)


def test_shadow_health_failure_or_unavailable_rejects_candidate() -> None:
    receipt = _activated_receipt()
    checks = list(_success_checks())
    checks[1] = replace(checks[1], status=RuntimeCheckStatus.FAILURE)
    checks[2] = replace(checks[2], status=RuntimeCheckStatus.UNAVAILABLE)

    report = ShadowHealthGate().evaluate(receipt, tuple(checks))
    assert report.decision is ShadowHealthDecision.REJECTED
    assert "health failed" in report.reasons
    assert "shadow_quality unavailable" in report.reasons


def test_shadow_health_requires_exact_checks_and_activated_receipt() -> None:
    receipt = _activated_receipt()
    checks = _success_checks()
    gate = ShadowHealthGate()

    with pytest.raises(ShadowHealthError, match="exact required"):
        gate.evaluate(receipt, checks[:-1])
    with pytest.raises(ShadowHealthError, match="unique"):
        gate.evaluate(receipt, checks + (checks[0],))

    request = _request()
    rolled_back = ActivationReceiptBuilder().bind(
        request,
        outcome=ActivationReceiptOutcome.ROLLED_BACK,
        host_authorization_ref="host-approval:rollback",
        deployment_ref="deployment:rollback",
        evidence_refs=("rollback-log",),
        observed_model_id=request.rollback_candidate_id,
        observed_checkpoint_sha256=request.rollback_checkpoint_sha256,
    )
    with pytest.raises(ShadowHealthError, match="activated receipt"):
        gate.evaluate(rolled_back, checks)


def test_shadow_health_report_tampering_is_rejected_by_recomputation() -> None:
    receipt = _activated_receipt()
    checks = _success_checks()
    gate = ShadowHealthGate()
    report = gate.evaluate(receipt, checks)

    with pytest.raises(ShadowHealthError, match="differs from recomputation"):
        gate.verify(receipt, checks, replace(report, checks_fingerprint="f" * 64))
