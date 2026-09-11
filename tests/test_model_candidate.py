from __future__ import annotations

import hashlib
import json
from dataclasses import replace

import pytest

from st_music_agent.dataset_export import (
    DATASET_EXPORT_SCHEMA_VERSION,
    CuratedDatasetExport,
    DatasetPurpose,
)
from st_music_agent.learning_evaluation import (
    BenchmarkCaseResult,
    BenchmarkOutcome,
    BenchmarkRun,
    BenchmarkSeverity,
    LearningEvaluationGate,
)
from st_music_agent.model_candidate import (
    ModelCandidateError,
    ModelCandidateRegistry,
    ModelPromotionReviewGate,
    PromotionReviewDecision,
)
from st_music_agent.training_run import (
    TrainingRunContractBuilder,
    TrainingRunOutcome,
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


def _dataset() -> CuratedDatasetExport:
    rows = (
        {
            "project": "score_restore",
            "plan_id": "b" * 64,
            "candidate_rank": 1,
            "action": "run non-training consumer integration checks",
            "candidate_evidence_hash": "c" * 64,
            "repository": "khfy7wpr5p-maker/st-score-restore-engine",
            "branch": "agent/integration-checks",
            "commit_sha": "d" * 40,
            "outcome": "success",
            "ci": [{"name": "core-ci", "status": "success", "evidence_ref": "ci:1"}],
            "validators": [
                {"name": "restore-validator", "status": "success", "evidence_ref": "val:1"}
            ],
        },
    )
    record_ids = ("a" * 64,)
    manifest = {
        "schema_version": DATASET_EXPORT_SCHEMA_VERSION,
        "dataset_id": "candidate-data",
        "purpose": DatasetPurpose.FINE_TUNING_CANDIDATE.value,
        "source_record_ids": list(record_ids),
        "rows": [dict(row) for row in rows],
        "training_authorized": False,
        "auto_train": False,
        "auto_promote": False,
    }
    return CuratedDatasetExport(
        dataset_id="candidate-data",
        purpose=DatasetPurpose.FINE_TUNING_CANDIDATE,
        source_record_ids=record_ids,
        rows=rows,
        manifest_hash=_hash(manifest),
        training_authorized=False,
        auto_train=False,
        auto_promote=False,
    )


def _training_lineage():
    builder = TrainingRunContractBuilder()
    spec = builder.create_spec(
        _dataset(),
        run_id="train:model:v1",
        base_model_id="open-model/base",
        base_model_revision="v1.2.3",
        base_model_sha256="e" * 64,
        trainer_name="st-trainer",
        trainer_version="1.0.0",
        trainer_config={"epochs": 3, "learning_rate": 0.0001},
        seed=11,
        code_repository="khfy7wpr5p-maker/st-music-agent-lab-",
        code_commit_sha="f" * 40,
    )
    completion = builder.bind_completion(
        spec,
        authorization_ref="host-approval:training:1",
        checkpoint_sha256="1" * 64,
        evidence_refs=("trainer-log:1", "artifact:checkpoint:1"),
    )
    return spec, completion


def _benchmark_run(candidate_id: str, outcomes: tuple[BenchmarkOutcome, ...]) -> BenchmarkRun:
    return BenchmarkRun(
        candidate_id=candidate_id,
        results=tuple(
            BenchmarkCaseResult(
                case_id=f"case-{index + 1}",
                severity=(
                    BenchmarkSeverity.CRITICAL
                    if index < 2
                    else BenchmarkSeverity.STANDARD
                ),
                outcome=outcome,
                evidence_refs=(f"benchmark:{candidate_id}:{index + 1}",),
            )
            for index, outcome in enumerate(outcomes)
        ),
    )


def test_registry_derives_deterministic_candidate_from_verified_training_lineage() -> None:
    spec, completion = _training_lineage()
    registry = ModelCandidateRegistry()

    first = registry.register(spec, completion)
    second = registry.register(spec, completion)

    assert first == second
    assert first.candidate_id.startswith("model:")
    assert first.checkpoint_sha256 == "1" * 64
    assert first.training_input_fingerprint == spec.input_fingerprint
    assert first.evaluation_required is True
    assert first.activation_authorized is False
    assert first.auto_activate is False
    assert registry.get(first.candidate_id) == first
    assert registry.candidates() == (first,)


def test_failed_training_run_cannot_enter_model_candidate_registry() -> None:
    spec, _ = _training_lineage()
    failed = TrainingRunContractBuilder().bind_noncompletion(
        spec,
        outcome=TrainingRunOutcome.FAILED,
        authorization_ref="host-approval:training:failed",
        evidence_refs=("trainer-log:failed",),
    )

    with pytest.raises(ModelCandidateError, match="only completed"):
        ModelCandidateRegistry().register(spec, failed)


def test_valid_a16_recomputation_reaches_activation_review_but_not_activation() -> None:
    spec, completion = _training_lineage()
    candidate = ModelCandidateRegistry().register(spec, completion)
    baseline = _benchmark_run(
        "model:baseline",
        (
            BenchmarkOutcome.SUCCESS,
            BenchmarkOutcome.SUCCESS,
            BenchmarkOutcome.FAILURE,
            BenchmarkOutcome.ABSTAINED,
            BenchmarkOutcome.SUCCESS,
            BenchmarkOutcome.SUCCESS,
            BenchmarkOutcome.ABSTAINED,
            BenchmarkOutcome.SUCCESS,
        ),
    )
    candidate_run = _benchmark_run(
        candidate.candidate_id,
        (
            BenchmarkOutcome.SUCCESS,
            BenchmarkOutcome.SUCCESS,
            BenchmarkOutcome.ABSTAINED,
            BenchmarkOutcome.SUCCESS,
            BenchmarkOutcome.SUCCESS,
            BenchmarkOutcome.SUCCESS,
            BenchmarkOutcome.SUCCESS,
            BenchmarkOutcome.SUCCESS,
        ),
    )
    report = LearningEvaluationGate().compare(baseline, candidate_run)

    review = ModelPromotionReviewGate().review(candidate, baseline, candidate_run, report)

    assert review.decision is PromotionReviewDecision.ELIGIBLE_FOR_ACTIVATION_REVIEW
    assert review.candidate_id == candidate.candidate_id
    assert review.checkpoint_sha256 == candidate.checkpoint_sha256
    assert review.human_review_required is True
    assert review.activation_authorized is False
    assert review.auto_activate is False


def test_rejected_a16_result_stays_rejected_at_promotion_review() -> None:
    spec, completion = _training_lineage()
    candidate = ModelCandidateRegistry().register(spec, completion)
    baseline = _benchmark_run("model:baseline", (BenchmarkOutcome.SUCCESS,) * 8)
    candidate_run = _benchmark_run(candidate.candidate_id, (BenchmarkOutcome.SUCCESS,) * 8)
    report = LearningEvaluationGate().compare(baseline, candidate_run)

    review = ModelPromotionReviewGate().review(candidate, baseline, candidate_run, report)

    assert review.decision is PromotionReviewDecision.REJECTED
    assert review.activation_authorized is False
    assert review.auto_activate is False


def test_forged_or_mismatched_evaluation_report_fails_closed() -> None:
    spec, completion = _training_lineage()
    candidate = ModelCandidateRegistry().register(spec, completion)
    baseline = _benchmark_run(
        "model:baseline",
        (BenchmarkOutcome.ABSTAINED,) * 2 + (BenchmarkOutcome.FAILURE,) * 6,
    )
    candidate_run = _benchmark_run(candidate.candidate_id, (BenchmarkOutcome.SUCCESS,) * 8)
    report = LearningEvaluationGate().compare(baseline, candidate_run)
    forged = replace(report, candidate_fingerprint="0" * 64)

    with pytest.raises(ModelCandidateError, match="differs from recomputation"):
        ModelPromotionReviewGate().review(candidate, baseline, candidate_run, forged)

    wrong_run = _benchmark_run("model:different", (BenchmarkOutcome.SUCCESS,) * 8)
    wrong_report = LearningEvaluationGate().compare(baseline, wrong_run)
    with pytest.raises(ModelCandidateError, match="does not match registered"):
        ModelPromotionReviewGate().review(candidate, baseline, wrong_run, wrong_report)


def test_tampered_candidate_lineage_or_activation_flag_fails_closed() -> None:
    spec, completion = _training_lineage()
    candidate = ModelCandidateRegistry().register(spec, completion)
    baseline = _benchmark_run(
        "model:baseline",
        (BenchmarkOutcome.ABSTAINED,) * 2 + (BenchmarkOutcome.FAILURE,) * 6,
    )
    run = _benchmark_run(candidate.candidate_id, (BenchmarkOutcome.SUCCESS,) * 8)
    report = LearningEvaluationGate().compare(baseline, run)

    elevated = replace(candidate, activation_authorized=True)
    with pytest.raises(ModelCandidateError, match="must not grant activation"):
        ModelPromotionReviewGate().review(elevated, baseline, run, report)

    tampered = replace(candidate, checkpoint_sha256="2" * 64)
    with pytest.raises(ModelCandidateError, match="lineage fingerprint"):
        ModelPromotionReviewGate().review(tampered, baseline, run, report)
