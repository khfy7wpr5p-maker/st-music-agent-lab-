from __future__ import annotations

import json
from pathlib import Path

import pytest

from st_music_agent.agent_tools import ToolCallRequest, ToolCallStatus, ToolRegistry
from st_music_agent.experience import (
    ExperienceAdvisor,
    ExperienceError,
    ExperienceObservation,
    ExperienceOutcome,
    ExperienceReadToolset,
    ExperienceStore,
    LearningDisposition,
)
from st_music_agent.journal import JournalIntegrityError
from st_music_agent.music_evidence import MusicProject
from st_music_agent.portfolio_planning import PlanVerificationReport, PlanVerificationStatus


def _verified_plan() -> tuple[str, PlanVerificationReport]:
    plan_id = "verified-plan-001"
    return plan_id, PlanVerificationReport(
        status=PlanVerificationStatus.PASS,
        plan_id=plan_id,
        recomputed_plan_id=plan_id,
        issues=(),
    )


def _observation(
    plan_id: str,
    outcome: ExperienceOutcome,
    *,
    playbook_key: str = "score_restore.consumer_validation",
) -> ExperienceObservation:
    return ExperienceObservation(
        plan_id=plan_id,
        project=MusicProject.SCORE_RESTORE,
        action="run non-training consumer integration checks",
        playbook_key=playbook_key,
        outcome=outcome,
        evidence_refs=("ci:run-123", "blob:score-sha"),
    )


def test_experience_store_accepts_only_exact_verified_plan(tmp_path: Path) -> None:
    plan_id, verification = _verified_plan()
    store = ExperienceStore(tmp_path / "experience.jsonl")

    record = store.record_verified(_observation(plan_id, ExperienceOutcome.SUCCESS), verification)
    assert record.plan_id == plan_id
    assert record.outcome is ExperienceOutcome.SUCCESS
    assert record.record_id

    reopened = ExperienceStore(tmp_path / "experience.jsonl")
    records = reopened.read_records()
    assert len(records) == 1
    assert records[0].record_id == record.record_id


def test_experience_store_rejects_failed_or_mismatched_verification(tmp_path: Path) -> None:
    plan_id, verification = _verified_plan()
    store = ExperienceStore(tmp_path / "experience.jsonl")

    failed = PlanVerificationReport(
        status=PlanVerificationStatus.FAIL,
        plan_id=plan_id,
        recomputed_plan_id=plan_id,
        issues=("forced failure",),
    )
    with pytest.raises(ExperienceError, match="failed verification"):
        store.record_verified(_observation(plan_id, ExperienceOutcome.FAILURE), failed)

    mismatched = PlanVerificationReport(
        status=PlanVerificationStatus.PASS,
        plan_id="other-plan",
        recomputed_plan_id="other-plan",
        issues=(),
    )
    with pytest.raises(ExperienceError, match="plan_id does not match"):
        store.record_verified(_observation(plan_id, ExperienceOutcome.SUCCESS), mismatched)

    non_exact = PlanVerificationReport(
        status=PlanVerificationStatus.PASS,
        plan_id=plan_id,
        recomputed_plan_id="different-recomputation",
        issues=(),
    )
    with pytest.raises(ExperienceError, match="exact deterministic plan recomputation"):
        store.record_verified(_observation(plan_id, ExperienceOutcome.SUCCESS), non_exact)

    assert verification.status is PlanVerificationStatus.PASS


def test_advisor_never_auto_applies_and_uses_minimum_sample_threshold(tmp_path: Path) -> None:
    plan_id, verification = _verified_plan()
    store = ExperienceStore(tmp_path / "experience.jsonl")
    advisor = ExperienceAdvisor()

    store.record_verified(_observation(plan_id, ExperienceOutcome.SUCCESS), verification)
    store.record_verified(_observation(plan_id, ExperienceOutcome.SUCCESS), verification)
    first = advisor.summarize(store.read_records())
    assert first[0].disposition is LearningDisposition.OBSERVE
    assert first[0].auto_apply is False

    store.record_verified(_observation(plan_id, ExperienceOutcome.SUCCESS), verification)
    second = advisor.summarize(store.read_records())
    assert second[0].disposition is LearningDisposition.PREFER
    assert second[0].success_rate == 1.0
    assert second[0].auto_apply is False


def test_advisor_flags_weak_playbook_for_review(tmp_path: Path) -> None:
    plan_id, verification = _verified_plan()
    store = ExperienceStore(tmp_path / "experience.jsonl")

    store.record_verified(_observation(plan_id, ExperienceOutcome.SUCCESS), verification)
    store.record_verified(_observation(plan_id, ExperienceOutcome.FAILURE), verification)
    store.record_verified(_observation(plan_id, ExperienceOutcome.FAILURE), verification)

    recommendation = ExperienceAdvisor().summarize(store.read_records())[0]
    assert recommendation.disposition is LearningDisposition.REVIEW
    assert recommendation.success_rate == pytest.approx(1 / 3)
    assert recommendation.auto_apply is False


def test_model_surface_is_read_only_summary_only(tmp_path: Path) -> None:
    plan_id, verification = _verified_plan()
    store = ExperienceStore(tmp_path / "experience.jsonl")
    store.record_verified(_observation(plan_id, ExperienceOutcome.SUCCESS), verification)
    registry = ToolRegistry()
    ExperienceReadToolset(store).register_into(registry)

    assert registry.names() == ("learning.experience.summary",)
    result = registry.dispatch(
        ToolCallRequest(
            call_id="experience-summary",
            tool_name="learning.experience.summary",
            arguments={"project": "score_restore"},
        )
    )
    assert result.status is ToolCallStatus.SUCCESS
    assert result.output["auto_apply"] is False
    assert result.output["recommendations"][0]["successful"] == 1

    rejected = registry.dispatch(
        ToolCallRequest(
            call_id="experience-write",
            tool_name="learning.experience.record",
            arguments={},
        )
    )
    assert rejected.status is ToolCallStatus.REJECTED


def test_experience_journal_tampering_is_detected_on_reopen(tmp_path: Path) -> None:
    plan_id, verification = _verified_plan()
    path = tmp_path / "experience.jsonl"
    store = ExperienceStore(path)
    store.record_verified(_observation(plan_id, ExperienceOutcome.SUCCESS), verification)

    record = json.loads(path.read_text(encoding="utf-8"))
    record["payload"]["outcome"] = "failure"
    path.write_text(json.dumps(record) + "\n", encoding="utf-8")

    with pytest.raises(JournalIntegrityError, match="event hash does not verify"):
        ExperienceStore(path)
