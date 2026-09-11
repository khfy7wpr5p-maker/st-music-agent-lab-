from __future__ import annotations

from dataclasses import replace
from types import SimpleNamespace
from typing import Any

import pytest

from st_music_agent.agent_tools import ToolCallRequest, ToolCallStatus, ToolRegistry
from st_music_agent.portfolio_planning import (
    CrossProjectPlanner,
    CrossProjectVerifier,
    PlanVerificationStatus,
    PortfolioPlanningError,
    PortfolioPlanningService,
)


def _source(repository: str, path: str, sha: str) -> dict[str, str]:
    return {
        "repository": repository,
        "ref": "main",
        "path": path,
        "blob_sha": sha,
    }


def _snapshots() -> dict[str, dict[str, Any]]:
    return {
        "score_restore": {
            "schema_version": "1.1.0",
            "project": "score_restore",
            "authority": "repository_current_truth",
            "state": "V2A_HELDOUT_AND_STAGE9A_PASS_CANDIDATE_FROZEN",
            "summary": "frozen candidate",
            "claims": {
                "candidate_checkpoint_frozen": True,
                "production_inference_authorized": False,
                "stage12_entry_authorized": False,
            },
            "warnings": ["production inference remains unauthorized"],
            "next_safe_boundary": "run non-training consumer integration checks",
            "sources": [
                _source(
                    "khfy7wpr5p-maker/st-score-restore-engine",
                    "docs/live/truth.json",
                    "score-sha",
                )
            ],
        },
        "musicxml_guitar_tab": {
            "schema_version": "1.1.0",
            "project": "musicxml_guitar_tab",
            "authority": "executable_contract",
            "state": "CAPABILITY_CONTRACT_ACTIVE",
            "summary": "review capability contract",
            "claims": {
                "review_required_is_global_lock": False,
                "canonical_tab_requires_pass": True,
                "export_requires_pass": True,
            },
            "warnings": [],
            "next_safe_boundary": "connect teacher-revision runtime",
            "sources": [
                _source(
                    "khfy7wpr5p-maker/musicxml-to-guitar-tab-engine",
                    "src/app/reviewRequiredCapabilityContract.js",
                    "tab-sha",
                )
            ],
        },
        "score_editor": {
            "schema_version": "1.1.0",
            "project": "score_editor",
            "authority": "repository_source_of_truth",
            "state": "DEVELOPMENT_ACTIVE_RELEASE_GATED",
            "summary": "editor development active",
            "claims": {
                "manual_device_validation_required": True,
                "standalone_release_gate_passed": False,
                "seslitab_cutover_authorized": False,
            },
            "warnings": [],
            "next_safe_boundary": "APP-11G Tuplet Retiming Admission Foundation.",
            "sources": [
                _source(
                    "khfy7wpr5p-maker/st-score-editor-core",
                    "ROADMAP.md",
                    "editor-sha",
                )
            ],
        },
        "real_time_score_following": {
            "schema_version": "1.1.0",
            "project": "real_time_score_following",
            "authority": "permanent_research_evidence",
            "state": "SF11_COMPLETE_SF12_NEXT_RESEARCH",
            "summary": "SF-11 complete",
            "claims": {
                "research_evidence_is_production_authority": False,
                "research_evidence_is_pedagogical_authority": False,
                "acoustic_mono_mixture_authority": False,
            },
            "warnings": [],
            "next_safe_boundary": "SF-12 Orchestra Global Score Following research",
            "sources": [
                _source(
                    "khfy7wpr5p-maker/st-real-time-score-following-lab",
                    "benchmarks/reports/SF11_MIXED_ENSEMBLE.md",
                    "follow-sha",
                )
            ],
        },
    }


def test_planner_ranks_current_safe_boundaries_deterministically() -> None:
    planner = CrossProjectPlanner()
    plan = planner.plan(_snapshots())

    assert plan.execution_authorized is False
    assert [candidate.project.value for candidate in plan.candidates] == [
        "score_restore",
        "musicxml_guitar_tab",
        "score_editor",
        "real_time_score_following",
    ]
    assert [candidate.rank for candidate in plan.candidates] == [1, 2, 3, 4]
    assert plan.candidates[0].action == "run non-training consumer integration checks"
    assert plan.candidates[1].action == "connect teacher-revision runtime"
    assert plan.candidates[2].action.startswith("APP-11G")
    assert plan.candidates[3].action.startswith("SF-12")


def test_verifier_passes_exact_recomputation_and_rejects_tampering() -> None:
    snapshots = _snapshots()
    planner = CrossProjectPlanner()
    verifier = CrossProjectVerifier(planner)
    plan = planner.plan(snapshots)

    verified = verifier.verify(plan, snapshots)
    assert verified.status is PlanVerificationStatus.PASS
    assert verified.recomputed_plan_id == plan.plan_id

    tampered_candidate = replace(plan.candidates[0], action="promote directly to production")
    tampered = replace(plan, candidates=(tampered_candidate, *plan.candidates[1:]))
    rejected = verifier.verify(tampered, snapshots)
    assert rejected.status is PlanVerificationStatus.FAIL
    assert "plan differs from deterministic recomputation" in rejected.issues


def test_verifier_detects_evidence_change_after_plan_creation() -> None:
    snapshots = _snapshots()
    planner = CrossProjectPlanner()
    verifier = CrossProjectVerifier(planner)
    plan = planner.plan(snapshots)

    snapshots["score_editor"]["sources"][0]["blob_sha"] = "new-editor-sha"
    result = verifier.verify(plan, snapshots)

    assert result.status is PlanVerificationStatus.FAIL
    assert result.recomputed_plan_id != plan.plan_id


def test_planner_fails_closed_on_missing_project_or_opened_protected_gate() -> None:
    snapshots = _snapshots()
    del snapshots["real_time_score_following"]
    with pytest.raises(PortfolioPlanningError, match="snapshot set mismatch"):
        CrossProjectPlanner().plan(snapshots)

    snapshots = _snapshots()
    snapshots["score_restore"]["claims"]["production_inference_authorized"] = True
    with pytest.raises(PortfolioPlanningError, match="required planning claim changed"):
        CrossProjectPlanner().plan(snapshots)


class FakeAdapter:
    def __init__(self, snapshot: dict[str, Any]) -> None:
        self.snapshot = snapshot

    def collect(self, ref: str = "main") -> Any:
        assert ref == "main"
        return SimpleNamespace(as_dict=lambda: self.snapshot)


def test_portfolio_service_registers_one_read_only_plan_tool() -> None:
    snapshots = _snapshots()
    toolset = SimpleNamespace(
        score_restore=FakeAdapter(snapshots["score_restore"]),
        musicxml_tab=FakeAdapter(snapshots["musicxml_guitar_tab"]),
        score_editor=FakeAdapter(snapshots["score_editor"]),
        score_following=FakeAdapter(snapshots["real_time_score_following"]),
    )
    service = PortfolioPlanningService(toolset)  # type: ignore[arg-type]
    registry = ToolRegistry()
    service.register_into(registry)

    assert registry.names() == ("music.portfolio.plan",)
    result = registry.dispatch(
        ToolCallRequest(call_id="portfolio-1", tool_name="music.portfolio.plan", arguments={})
    )
    assert result.status is ToolCallStatus.SUCCESS
    assert result.output["plan"]["execution_authorized"] is False
    assert result.output["verification"]["status"] == "pass"
    assert len(result.output["snapshots"]) == 4
