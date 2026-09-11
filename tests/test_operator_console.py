from __future__ import annotations

import json
from types import SimpleNamespace

from st_music_agent.music_evidence import (
    EvidenceAuthority,
    EvidenceSource,
    MusicEvidenceSnapshot,
    MusicProject,
)
from st_music_agent.operator_console import OperatorConsoleService
from st_music_agent.web_app import OperatorConsoleApplication


class _Adapter:
    def __init__(self, snapshot: MusicEvidenceSnapshot) -> None:
        self.snapshot = snapshot

    def collect(self, ref: str = "main") -> MusicEvidenceSnapshot:
        assert ref
        return self.snapshot


class _BrokenAdapter:
    def collect(self, ref: str = "main") -> MusicEvidenceSnapshot:
        raise RuntimeError("repository unavailable")


def _snapshot(project: MusicProject) -> MusicEvidenceSnapshot:
    claims: dict[str, object]
    authority = EvidenceAuthority.REPOSITORY_SOURCE_OF_TRUTH
    if project is MusicProject.SCORE_RESTORE:
        authority = EvidenceAuthority.REPOSITORY_CURRENT_TRUTH
        claims = {
            "candidate_checkpoint_frozen": True,
            "production_inference_authorized": False,
            "stage12_entry_authorized": False,
        }
    elif project is MusicProject.MUSICXML_GUITAR_TAB:
        authority = EvidenceAuthority.EXECUTABLE_CONTRACT
        claims = {
            "review_required_is_global_lock": False,
            "canonical_tab_requires_pass": True,
            "export_requires_pass": True,
        }
    elif project is MusicProject.SCORE_EDITOR:
        claims = {
            "manual_device_validation_required": True,
            "standalone_release_gate_passed": False,
            "seslitab_cutover_authorized": False,
        }
    else:
        authority = EvidenceAuthority.PERMANENT_RESEARCH_EVIDENCE
        claims = {
            "research_evidence_is_production_authority": False,
            "research_evidence_is_pedagogical_authority": False,
            "acoustic_mono_mixture_authority": False,
        }
    return MusicEvidenceSnapshot(
        project=project,
        authority=authority,
        state="READY_FOR_TEST",
        summary=f"{project.value} summary",
        claims=claims,
        warnings=(),
        next_safe_boundary=f"next {project.value}",
        sources=(
            EvidenceSource(
                repository=f"example/{project.value}",
                ref="main",
                path="evidence.json",
                blob_sha="a" * 40,
            ),
        ),
    )


def _tools(*, broken_editor: bool = False) -> SimpleNamespace:
    return SimpleNamespace(
        score_restore=_Adapter(_snapshot(MusicProject.SCORE_RESTORE)),
        musicxml_tab=_Adapter(_snapshot(MusicProject.MUSICXML_GUITAR_TAB)),
        score_editor=(
            _BrokenAdapter()
            if broken_editor
            else _Adapter(_snapshot(MusicProject.SCORE_EDITOR))
        ),
        score_following=_Adapter(_snapshot(MusicProject.REAL_TIME_SCORE_FOLLOWING)),
    )


def test_operator_console_lists_four_projects_and_keeps_mutation_closed() -> None:
    service = OperatorConsoleService(music_tools=_tools())
    health = service.health()
    result = service.list_projects()
    capabilities = service.action_capabilities()

    assert health["status"] == "ok"
    assert health["execution_authorized"] is False
    assert len(result["projects"]) == 4
    assert all(item["availability"] == "ok" for item in result["projects"])
    assert capabilities["write"]["feature_branch_task_execution"] is False
    assert capabilities["write"]["rollback_execution"] is False


def test_project_failure_is_isolated_to_its_card() -> None:
    service = OperatorConsoleService(music_tools=_tools(broken_editor=True))
    result = service.list_projects()
    by_project = {item["project"]: item for item in result["projects"]}

    assert by_project["score_editor"]["availability"] == "error"
    assert "repository unavailable" in by_project["score_editor"]["error"]
    assert by_project["score_restore"]["availability"] == "ok"


def test_verified_plan_is_recomputed_and_execution_remains_closed() -> None:
    service = OperatorConsoleService(music_tools=_tools())
    result = service.verified_plan()

    assert result["verification"]["status"] == "pass"
    assert result["plan"]["execution_authorized"] is False
    assert result["execution_authorized"] is False
    assert [item["rank"] for item in result["plan"]["candidates"]] == [1, 2, 3, 4]


def test_http_application_serves_ui_and_json_without_write_methods() -> None:
    app = OperatorConsoleApplication(OperatorConsoleService(music_tools=_tools()))

    index = app.dispatch("GET", "/")
    health = app.dispatch("GET", "/api/health")
    projects = app.dispatch("GET", "/api/projects?ref=main")
    plan = app.dispatch("GET", "/api/plan")
    post = app.dispatch("POST", "/api/projects")
    missing = app.dispatch("GET", "/api/nope")

    assert index.status == 200
    assert b"Operator Console" in index.body
    assert json.loads(health.body)["status"] == "ok"
    assert len(json.loads(projects.body)["projects"]) == 4
    assert json.loads(plan.body)["verification"]["status"] == "pass"
    assert post.status == 405
    assert missing.status == 404
