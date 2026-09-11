from __future__ import annotations

import hashlib
import json
from dataclasses import replace
from pathlib import Path

import pytest

from st_music_agent.baseline_registry import BaselineRegistry, BaselineRegistryError
from st_music_agent.canonical_baseline import (
    CANONICALIZATION_RECEIPT_SCHEMA_VERSION,
    CanonicalizationOutcome,
    CanonicalizationReceipt,
    CanonicalizationReceiptBuilder,
)
from st_music_agent.post_canonical_stability import (
    POST_CANONICAL_MIN_ROUNDS,
    PostCanonicalCheck,
    PostCanonicalCheckKind,
    PostCanonicalCheckStatus,
    PostCanonicalObservationRound,
    PostCanonicalStabilityDecision,
    PostCanonicalStabilityError,
    PostCanonicalStabilityGate,
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


def _canonicalized_receipt(*, environment: str = "prod") -> CanonicalizationReceipt:
    candidate_id = f"model:{'1' * 64}"
    candidate_checkpoint = "2" * 64
    previous_id = f"model:{'a' * 64}"
    previous_checkpoint = "b" * 64
    base = {
        "schema_version": CANONICALIZATION_RECEIPT_SCHEMA_VERSION,
        "canonical_review_fingerprint": "c" * 64,
        "candidate_id": candidate_id,
        "candidate_checkpoint_sha256": candidate_checkpoint,
        "previous_canonical_id": previous_id,
        "previous_canonical_checkpoint_sha256": previous_checkpoint,
        "rollback_candidate_id": previous_id,
        "rollback_checkpoint_sha256": previous_checkpoint,
        "target_environment": environment,
        "outcome": CanonicalizationOutcome.CANONICALIZED.value,
        "host_authorization_ref": "host-approval:canonicalization:1",
        "canonicalization_ref": "canonicalization:prod:1",
        "evidence_refs": ["canonical-switch-log:1"],
        "observed_canonical_id": candidate_id,
        "observed_canonical_checkpoint_sha256": candidate_checkpoint,
        "post_canonical_health_required": True,
        "auto_rollback": False,
        "auto_canonicalize": False,
    }
    receipt = CanonicalizationReceipt(
        canonical_review_fingerprint="c" * 64,
        candidate_id=candidate_id,
        candidate_checkpoint_sha256=candidate_checkpoint,
        previous_canonical_id=previous_id,
        previous_canonical_checkpoint_sha256=previous_checkpoint,
        rollback_candidate_id=previous_id,
        rollback_checkpoint_sha256=previous_checkpoint,
        target_environment=environment,
        outcome=CanonicalizationOutcome.CANONICALIZED,
        host_authorization_ref="host-approval:canonicalization:1",
        canonicalization_ref="canonicalization:prod:1",
        evidence_refs=("canonical-switch-log:1",),
        observed_canonical_id=candidate_id,
        observed_canonical_checkpoint_sha256=candidate_checkpoint,
        receipt_fingerprint=_hash(base),
        post_canonical_health_required=True,
        auto_rollback=False,
        auto_canonicalize=False,
    )
    CanonicalizationReceiptBuilder.verify(receipt)
    return receipt


def _success_rounds(receipt: CanonicalizationReceipt) -> tuple[PostCanonicalObservationRound, ...]:
    rounds: list[PostCanonicalObservationRound] = []
    for sequence in range(1, POST_CANONICAL_MIN_ROUNDS + 1):
        checks = tuple(
            PostCanonicalCheck(
                kind=kind,
                status=PostCanonicalCheckStatus.SUCCESS,
                evidence_refs=(f"evidence:round-{sequence}:{kind.value}",),
            )
            for kind in PostCanonicalCheckKind
        )
        rounds.append(
            PostCanonicalObservationRound(
                sequence=sequence,
                observation_ref=f"observation:round-{sequence}",
                observed_model_id=receipt.candidate_id,
                observed_checkpoint_sha256=receipt.candidate_checkpoint_sha256,
                checks=checks,
            )
        )
    return tuple(rounds)


def test_three_successful_rounds_are_only_eligible_for_registry() -> None:
    receipt = _canonicalized_receipt()
    rounds = _success_rounds(receipt)
    gate = PostCanonicalStabilityGate()
    report = gate.evaluate(receipt, rounds)

    assert report.observation_round_count == POST_CANONICAL_MIN_ROUNDS
    assert report.decision is PostCanonicalStabilityDecision.ELIGIBLE_FOR_BASELINE_REGISTRATION
    assert report.host_registration_required is True
    assert report.auto_register_baseline is False
    assert report.auto_rollback is False
    gate.verify(receipt, rounds, report)


def test_failure_unavailable_or_wrong_identity_rejects_stability() -> None:
    receipt = _canonicalized_receipt()
    rounds = list(_success_rounds(receipt))
    first_checks = list(rounds[0].checks)
    first_checks[1] = replace(first_checks[1], status=PostCanonicalCheckStatus.FAILURE)
    rounds[0] = replace(rounds[0], checks=tuple(first_checks))
    second_checks = list(rounds[1].checks)
    second_checks[2] = replace(second_checks[2], status=PostCanonicalCheckStatus.UNAVAILABLE)
    rounds[1] = replace(rounds[1], checks=tuple(second_checks))
    rounds[2] = replace(rounds[2], observed_model_id=f"model:{'9' * 64}")

    report = PostCanonicalStabilityGate().evaluate(receipt, tuple(rounds))
    assert report.decision is PostCanonicalStabilityDecision.REJECTED
    assert "round 1 health failed" in report.reasons
    assert "round 2 quality unavailable" in report.reasons
    assert "round 3 observed wrong model" in report.reasons


def test_stability_requires_minimum_unique_complete_rounds() -> None:
    receipt = _canonicalized_receipt()
    rounds = _success_rounds(receipt)
    gate = PostCanonicalStabilityGate()

    with pytest.raises(PostCanonicalStabilityError, match="at least"):
        gate.evaluate(receipt, rounds[:-1])
    with pytest.raises(PostCanonicalStabilityError, match="observation refs"):
        gate.evaluate(receipt, (rounds[0], replace(rounds[1], observation_ref=rounds[0].observation_ref), rounds[2]))
    with pytest.raises(PostCanonicalStabilityError, match="exact required"):
        gate.evaluate(receipt, (replace(rounds[0], checks=rounds[0].checks[:-1]), *rounds[1:]))


def test_stability_report_tampering_is_rejected() -> None:
    receipt = _canonicalized_receipt()
    rounds = _success_rounds(receipt)
    gate = PostCanonicalStabilityGate()
    report = gate.evaluate(receipt, rounds)

    with pytest.raises(PostCanonicalStabilityError, match="differs from recomputation"):
        gate.verify(receipt, rounds, replace(report, observation_rounds_fingerprint="f" * 64))


def test_baseline_registry_records_exact_lineage_and_reopens(tmp_path: Path) -> None:
    receipt = _canonicalized_receipt()
    rounds = _success_rounds(receipt)
    report = PostCanonicalStabilityGate().evaluate(receipt, rounds)
    path = tmp_path / "baseline-registry.jsonl"
    registry = BaselineRegistry(path, "prod")
    bootstrap = registry.bootstrap(
        model_id=receipt.previous_canonical_id,
        checkpoint_sha256=receipt.previous_canonical_checkpoint_sha256,
        host_registration_ref="host-registry:bootstrap",
        evidence_refs=("baseline-snapshot:before",),
    )
    record = registry.register_canonicalization(
        receipt,
        rounds,
        report,
        host_registration_ref="host-registry:canonical:1",
        evidence_refs=("baseline-snapshot:after",),
    )

    assert bootstrap.generation == 1
    assert record.generation == 2
    assert record.model_id == receipt.candidate_id
    assert record.previous_model_id == receipt.previous_canonical_id
    assert record.rollback_model_id == receipt.rollback_candidate_id
    assert record.canonicalization_receipt_fingerprint == receipt.receipt_fingerprint
    assert record.stability_report_fingerprint == report.report_fingerprint
    assert record.auto_switch is False
    assert record.auto_rollback is False
    assert registry.current() == record

    reopened = BaselineRegistry(path, "prod")
    assert reopened.current() == record
    assert reopened.history() == (bootstrap, record)


def test_registry_fails_closed_on_baseline_drift_or_forged_stability(tmp_path: Path) -> None:
    receipt = _canonicalized_receipt()
    rounds = _success_rounds(receipt)
    report = PostCanonicalStabilityGate().evaluate(receipt, rounds)

    drifted = BaselineRegistry(tmp_path / "drifted.jsonl", "prod")
    drifted.bootstrap(
        model_id=f"model:{'d' * 64}",
        checkpoint_sha256="e" * 64,
        host_registration_ref="host-registry:wrong",
        evidence_refs=("wrong-baseline",),
    )
    with pytest.raises(BaselineRegistryError, match="predecessor"):
        drifted.register_canonicalization(
            receipt,
            rounds,
            report,
            host_registration_ref="host-registry:canonical:1",
            evidence_refs=("baseline-snapshot:after",),
        )

    registry = BaselineRegistry(tmp_path / "forged.jsonl", "prod")
    registry.bootstrap(
        model_id=receipt.previous_canonical_id,
        checkpoint_sha256=receipt.previous_canonical_checkpoint_sha256,
        host_registration_ref="host-registry:bootstrap",
        evidence_refs=("baseline-snapshot:before",),
    )
    with pytest.raises(PostCanonicalStabilityError, match="differs from recomputation"):
        registry.register_canonicalization(
            receipt,
            rounds,
            replace(report, report_fingerprint="0" * 64),
            host_registration_ref="host-registry:canonical:1",
            evidence_refs=("baseline-snapshot:after",),
        )
