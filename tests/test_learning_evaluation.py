from __future__ import annotations

import pytest

from st_music_agent.agent_tools import ToolCallRequest, ToolCallStatus, ToolRegistry
from st_music_agent.learning_evaluation import (
    BenchmarkCaseResult,
    BenchmarkOutcome,
    BenchmarkRun,
    BenchmarkSeverity,
    LearningEvaluationError,
    LearningEvaluationGate,
    LearningEvaluationPolicy,
    LearningEvaluationReadToolset,
    PromotionDecision,
)


def _result(
    case_id: str,
    outcome: BenchmarkOutcome,
    *,
    critical: bool = False,
    evidence_suffix: str = "v1",
) -> BenchmarkCaseResult:
    return BenchmarkCaseResult(
        case_id=case_id,
        severity=BenchmarkSeverity.CRITICAL if critical else BenchmarkSeverity.STANDARD,
        outcome=outcome,
        evidence_refs=(f"ci:{case_id}:{evidence_suffix}",),
    )


def _run(candidate_id: str, outcomes: list[BenchmarkOutcome]) -> BenchmarkRun:
    return BenchmarkRun(
        candidate_id=candidate_id,
        results=tuple(
            _result(
                f"case-{index + 1}",
                outcome,
                critical=index < 2,
            )
            for index, outcome in enumerate(outcomes)
        ),
    )


def test_candidate_is_only_eligible_after_non_regressing_real_improvement() -> None:
    baseline = _run(
        "playbook:baseline",
        [
            BenchmarkOutcome.SUCCESS,
            BenchmarkOutcome.SUCCESS,
            BenchmarkOutcome.FAILURE,
            BenchmarkOutcome.ABSTAINED,
            BenchmarkOutcome.SUCCESS,
            BenchmarkOutcome.SUCCESS,
            BenchmarkOutcome.ABSTAINED,
            BenchmarkOutcome.SUCCESS,
        ],
    )
    candidate = _run(
        "playbook:candidate",
        [
            BenchmarkOutcome.SUCCESS,
            BenchmarkOutcome.SUCCESS,
            BenchmarkOutcome.ABSTAINED,
            BenchmarkOutcome.SUCCESS,
            BenchmarkOutcome.SUCCESS,
            BenchmarkOutcome.SUCCESS,
            BenchmarkOutcome.SUCCESS,
            BenchmarkOutcome.SUCCESS,
        ],
    )

    report = LearningEvaluationGate().compare(baseline, candidate)

    assert report.decision is PromotionDecision.ELIGIBLE_FOR_HOST_REVIEW
    assert report.regressed_cases == ()
    assert report.candidate_critical_failures == ()
    assert set(report.improved_cases) == {"case-3", "case-4", "case-7"}
    assert report.compared_cases == 8
    assert report.critical_cases == 2
    assert report.auto_promote is False


def test_any_paired_regression_rejects_candidate() -> None:
    baseline = _run("baseline", [BenchmarkOutcome.SUCCESS] * 8)
    outcomes = [BenchmarkOutcome.SUCCESS] * 8
    outcomes[5] = BenchmarkOutcome.ABSTAINED
    candidate = _run("candidate", outcomes)

    report = LearningEvaluationGate().compare(baseline, candidate)

    assert report.decision is PromotionDecision.REJECTED
    assert report.regressed_cases == ("case-6",)
    assert "regresses" in report.reasons[0]
    assert report.auto_promote is False


def test_critical_failure_rejects_even_when_other_cases_improve() -> None:
    baseline = _run(
        "baseline",
        [BenchmarkOutcome.ABSTAINED] * 2 + [BenchmarkOutcome.FAILURE] * 6,
    )
    candidate = _run(
        "candidate",
        [
            BenchmarkOutcome.FAILURE,
            BenchmarkOutcome.SUCCESS,
            BenchmarkOutcome.SUCCESS,
            BenchmarkOutcome.SUCCESS,
            BenchmarkOutcome.SUCCESS,
            BenchmarkOutcome.SUCCESS,
            BenchmarkOutcome.SUCCESS,
            BenchmarkOutcome.SUCCESS,
        ],
    )

    report = LearningEvaluationGate().compare(baseline, candidate)

    assert report.decision is PromotionDecision.REJECTED
    assert report.candidate_critical_failures == ("case-1",)
    assert "case-1" in report.regressed_cases


def test_equal_candidate_is_not_promotable() -> None:
    baseline = _run("baseline", [BenchmarkOutcome.SUCCESS] * 8)
    candidate = _run("candidate", [BenchmarkOutcome.SUCCESS] * 8)

    report = LearningEvaluationGate().compare(baseline, candidate)

    assert report.decision is PromotionDecision.REJECTED
    assert report.improved_cases == ()
    assert "does not improve" in report.reasons[-1]


def test_case_set_and_severity_drift_fail_closed() -> None:
    baseline = _run("baseline", [BenchmarkOutcome.SUCCESS] * 8)
    candidate_results = list(_run("candidate", [BenchmarkOutcome.SUCCESS] * 8).results)
    candidate_results[-1] = _result("different-case", BenchmarkOutcome.SUCCESS)

    with pytest.raises(LearningEvaluationError, match="exact same cases"):
        LearningEvaluationGate().compare(
            baseline,
            BenchmarkRun("candidate", tuple(candidate_results)),
        )

    severity_results = list(_run("candidate", [BenchmarkOutcome.SUCCESS] * 8).results)
    severity_results[4] = _result("case-5", BenchmarkOutcome.SUCCESS, critical=True)
    with pytest.raises(LearningEvaluationError, match="severities differ"):
        LearningEvaluationGate().compare(
            baseline,
            BenchmarkRun("candidate", tuple(severity_results)),
        )


def test_minimum_case_and_critical_coverage_are_enforced() -> None:
    short_policy = LearningEvaluationPolicy(minimum_cases=4, minimum_critical_cases=2)
    gate = LearningEvaluationGate(short_policy)
    baseline = BenchmarkRun(
        "baseline",
        tuple(
            _result(f"case-{index + 1}", BenchmarkOutcome.FAILURE, critical=index == 0)
            for index in range(4)
        ),
    )
    candidate = BenchmarkRun(
        "candidate",
        tuple(
            _result(f"case-{index + 1}", BenchmarkOutcome.SUCCESS, critical=index == 0)
            for index in range(4)
        ),
    )

    with pytest.raises(LearningEvaluationError, match="minimum critical"):
        gate.compare(baseline, candidate)

    default_gate = LearningEvaluationGate()
    with pytest.raises(LearningEvaluationError, match="minimum case count"):
        default_gate.compare(baseline, candidate)


def test_evidence_change_changes_run_fingerprint() -> None:
    run_one = BenchmarkRun(
        "candidate",
        tuple(
            _result(f"case-{index + 1}", BenchmarkOutcome.SUCCESS, critical=index < 2)
            for index in range(8)
        ),
    )
    changed_results = list(run_one.results)
    changed_results[3] = _result(
        "case-4",
        BenchmarkOutcome.SUCCESS,
        evidence_suffix="different-evidence",
    )
    run_two = BenchmarkRun("candidate", tuple(changed_results))

    assert run_one.fingerprint() != run_two.fingerprint()


def test_policy_snapshot_never_authorizes_automatic_promotion() -> None:
    snapshot = LearningEvaluationGate().policy_snapshot()

    assert snapshot["minimum_cases"] == 8
    assert snapshot["minimum_critical_cases"] == 2
    assert snapshot["regression_allowed"] is False
    assert snapshot["critical_failure_allowed"] is False
    assert snapshot["auto_promote"] is False


def test_model_surface_can_only_read_evaluation_policy() -> None:
    registry = ToolRegistry()
    LearningEvaluationReadToolset().register_into(registry)

    assert registry.names() == ("learning.evaluation.policy",)
    result = registry.dispatch(
        ToolCallRequest(
            call_id="read-evaluation-policy",
            tool_name="learning.evaluation.policy",
            arguments={},
        )
    )
    assert result.status is ToolCallStatus.SUCCESS
    assert result.output["auto_promote"] is False
    assert result.output["regression_allowed"] is False

    rejected = registry.dispatch(
        ToolCallRequest(
            call_id="try-promote",
            tool_name="learning.evaluation.promote",
            arguments={},
        )
    )
    assert rejected.status is ToolCallStatus.REJECTED
