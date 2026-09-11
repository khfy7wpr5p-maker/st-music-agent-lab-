from dataclasses import replace
from pathlib import Path

import pytest

from st_music_agent.execution_outcome import (
    EvidenceCheckStatus,
    ExecutionCheck,
    ExecutionObservation,
    ExecutionOutcomeError,
    ExecutionOutcomeStatus,
    ExecutionOutcomeStore,
)
from st_music_agent.journal import JournalIntegrityError
from st_music_agent.music_evidence import MusicProject
from st_music_agent.portfolio_planning import (
    CrossProjectPlan,
    PlanCandidate,
    PlanVerificationReport,
    PlanVerificationStatus,
)


def _plan() -> tuple[CrossProjectPlan, PlanVerificationReport, PlanCandidate]:
    candidate = PlanCandidate(
        rank=1,
        project=MusicProject.SCORE_RESTORE,
        category="validated_candidate_integration",
        action="run non-training consumer integration checks",
        rationale="test",
        constraints=("production inference remains unauthorized",),
        evidence_hash="a" * 64,
    )
    plan = CrossProjectPlan(
        plan_id="b" * 64,
        policy_version="2026-09-11.v1",
        evidence_set_hash="c" * 64,
        candidates=(candidate,),
        execution_authorized=False,
    )
    verification = PlanVerificationReport(
        status=PlanVerificationStatus.PASS,
        plan_id=plan.plan_id,
        recomputed_plan_id=plan.plan_id,
        issues=(),
    )
    return plan, verification, candidate


def _observation(
    candidate: PlanCandidate,
    *,
    outcome: ExecutionOutcomeStatus = ExecutionOutcomeStatus.SUCCESS,
    ci_status: EvidenceCheckStatus = EvidenceCheckStatus.SUCCESS,
    validator_status: EvidenceCheckStatus = EvidenceCheckStatus.SUCCESS,
) -> ExecutionObservation:
    return ExecutionObservation(
        plan_id="b" * 64,
        project=MusicProject.SCORE_RESTORE,
        candidate_rank=1,
        action=candidate.action,
        candidate_evidence_hash=candidate.evidence_hash,
        repository="khfy7wpr5p-maker/st-score-restore-engine",
        branch="agent/integration-checks",
        commit_sha="d" * 40,
        outcome=outcome,
        ci_checks=(ExecutionCheck("core-ci", ci_status, "ci:123"),),
        validator_checks=(
            ExecutionCheck("restore-validator", validator_status, "validator:456"),
        ),
    )


def test_success_record_requires_exact_verified_plan_and_green_evidence(tmp_path: Path) -> None:
    plan, verification, candidate = _plan()
    store = ExecutionOutcomeStore(tmp_path / "execution.jsonl")

    record = store.record_verified(_observation(candidate), plan, verification)

    assert record.plan_id == plan.plan_id
    assert record.commit_sha == "d" * 40
    assert record.outcome is ExecutionOutcomeStatus.SUCCESS
    assert ExecutionOutcomeStore(tmp_path / "execution.jsonl").read_records()[0] == record


def test_wrong_plan_action_evidence_or_repository_fails_closed(tmp_path: Path) -> None:
    plan, verification, candidate = _plan()
    store = ExecutionOutcomeStore(tmp_path / "execution.jsonl")
    base = _observation(candidate)

    with pytest.raises(ExecutionOutcomeError, match="action does not match"):
        store.record_verified(replace(base, action="different action"), plan, verification)

    with pytest.raises(ExecutionOutcomeError, match="evidence hash"):
        store.record_verified(
            replace(base, candidate_evidence_hash="e" * 64), plan, verification
        )

    with pytest.raises(ExecutionOutcomeError, match="repository"):
        store.record_verified(replace(base, repository="owner/wrong"), plan, verification)


def test_success_cannot_hide_failed_or_skipped_checks(tmp_path: Path) -> None:
    plan, verification, candidate = _plan()
    store = ExecutionOutcomeStore(tmp_path / "execution.jsonl")

    with pytest.raises(ExecutionOutcomeError, match="every CI/validator"):
        store.record_verified(
            _observation(candidate, ci_status=EvidenceCheckStatus.FAILURE),
            plan,
            verification,
        )

    with pytest.raises(ExecutionOutcomeError, match="every CI/validator"):
        store.record_verified(
            _observation(candidate, validator_status=EvidenceCheckStatus.SKIPPED),
            plan,
            verification,
        )


def test_failure_and_abstention_require_non_green_evidence(tmp_path: Path) -> None:
    plan, verification, candidate = _plan()
    store = ExecutionOutcomeStore(tmp_path / "execution.jsonl")

    failure = _observation(
        candidate,
        outcome=ExecutionOutcomeStatus.FAILURE,
        ci_status=EvidenceCheckStatus.FAILURE,
    )
    record = store.record_verified(failure, plan, verification)
    assert record.outcome is ExecutionOutcomeStatus.FAILURE

    with pytest.raises(ExecutionOutcomeError, match="abstained"):
        store.record_verified(
            _observation(candidate, outcome=ExecutionOutcomeStatus.ABSTAINED),
            plan,
            verification,
        )


def test_failed_plan_verification_cannot_record_execution(tmp_path: Path) -> None:
    plan, _, candidate = _plan()
    failed = PlanVerificationReport(
        status=PlanVerificationStatus.FAIL,
        plan_id=plan.plan_id,
        recomputed_plan_id=plan.plan_id,
        issues=("drift",),
    )
    with pytest.raises(ExecutionOutcomeError, match="PASS"):
        ExecutionOutcomeStore(tmp_path / "execution.jsonl").record_verified(
            _observation(candidate), plan, failed
        )


def test_execution_journal_tampering_is_detected(tmp_path: Path) -> None:
    plan, verification, candidate = _plan()
    path = tmp_path / "execution.jsonl"
    ExecutionOutcomeStore(path).record_verified(_observation(candidate), plan, verification)
    text = path.read_text(encoding="utf-8").replace(
        '"outcome":"success"', '"outcome":"failure"'
    )
    path.write_text(text, encoding="utf-8")

    with pytest.raises(JournalIntegrityError, match="event hash does not verify"):
        ExecutionOutcomeStore(path)
