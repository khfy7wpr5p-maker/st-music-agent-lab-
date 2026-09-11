from __future__ import annotations

from dataclasses import dataclass, field
from types import SimpleNamespace
from typing import Any

import pytest

from st_music_agent.agent_tools import ToolRegistry
from st_music_agent.music_adapters import MusicXmlTabEvidenceAdapter, ScoreRestoreEvidenceAdapter
from st_music_agent.music_adapters_extended import (
    FullMusicDomainToolset,
    ScoreEditorEvidenceAdapter,
    ScoreFollowingEvidenceAdapter,
)
from st_music_agent.music_evidence import MusicEvidenceError


@dataclass
class FakeReadClient:
    repository: str
    files: dict[str, dict[str, Any]]
    calls: list[tuple[str, str | None]] = field(default_factory=list)

    def __post_init__(self) -> None:
        self.config = SimpleNamespace(repository=self.repository)

    def read_file(self, path: str, ref: str | None = None) -> dict[str, Any]:
        self.calls.append((path, ref))
        return dict(self.files[path])


def _editor_roadmap() -> str:
    return """
## Current source of truth
Repository reality only; planned capability is not production capability.
- **APP-11F — COMPLETE / MERGED:** bounded triplet metadata.
- **Manual standalone release matrix — DEFERRED FOR CURRENT DEVELOPMENT / REQUIRED BEFORE RELEASE.**
- **SesliTab V4 product cutover — DEFERRED / NOT AUTHORIZED**
The project is now in **strong-editor semantic selection, relation authoring and timing-space expansion**
- `manualDeviceValidationRequired: true`
- `standaloneReleaseGatePassed: false`
- `seslitabCutoverAuthorized: false`
**APP-11G — Tuplet Retiming Admission Foundation.**
Do not open release or SesliTab gates as part of feature development.
"""


def _following_readme() -> str:
    return """
**SF-11 Mixed Ensemble is complete for repository-owned deterministic channel-separated heterogeneous evidence. SF-12 Orchestra Global Score Following is the next autonomous stage.**
Experimental evidence is not production or pedagogical authority.
SF-04 Solo Violin remains a narrow real-evidence rights gate and does not block independent stages.
"""


def _sf11_report() -> str:
    return """
Authority boundary: `mixed_ensemble_channel_separated_research_not_acoustic_mixture_authority`.
This evidence does **not** establish acoustic mono-mixture source separation, real-room generalization, or pedagogical grading.
Implementation head: `a694a4ff088ed7ef45192fca77032a283dc0410a`.
CI run `34529350858` passed all 9 jobs on that head.
Shared confidence unavailable.
The benchmark is synthetic, repository-owned, and channel-separated.
Asynchrony, divergence, quorum loss, and abstention are evidence states rather than quality grades.
SF-11 is complete for deterministic channel-separated mixed-ensemble provenance and fail-soft timing semantics.
"""


def _editor_client() -> FakeReadClient:
    return FakeReadClient(
        "khfy7wpr5p-maker/st-score-editor-core",
        {"ROADMAP.md": {"content": _editor_roadmap(), "truncated": False, "sha": "editor-sha"}},
    )


def _following_client() -> FakeReadClient:
    return FakeReadClient(
        "khfy7wpr5p-maker/st-real-time-score-following-lab",
        {
            "README.md": {"content": _following_readme(), "truncated": False, "sha": "readme-sha"},
            "benchmarks/reports/SF11_MIXED_ENSEMBLE.md": {
                "content": _sf11_report(),
                "truncated": False,
                "sha": "sf11-sha",
            },
        },
    )


def _unused_client(repository: str) -> FakeReadClient:
    return FakeReadClient(repository, {})


def test_score_editor_snapshot_keeps_release_and_cutover_gates_closed() -> None:
    payload = ScoreEditorEvidenceAdapter(_editor_client()).collect().as_dict()

    assert payload["schema_version"] == "1.1.0"
    assert payload["project"] == "score_editor"
    assert payload["authority"] == "repository_source_of_truth"
    assert payload["state"] == "DEVELOPMENT_ACTIVE_RELEASE_GATED"
    assert payload["claims"]["app_11f_complete_merged"] is True
    assert payload["claims"]["manual_device_validation_required"] is True
    assert payload["claims"]["standalone_release_gate_passed"] is False
    assert payload["claims"]["seslitab_cutover_authorized"] is False
    assert payload["claims"]["release_gate_may_open_during_feature_development"] is False
    assert payload["sources"][0]["blob_sha"] == "editor-sha"


def test_score_editor_snapshot_fails_closed_if_release_marker_drifts() -> None:
    client = _editor_client()
    client.files["ROADMAP.md"]["content"] = _editor_roadmap().replace(
        "standaloneReleaseGatePassed: false",
        "standaloneReleaseGatePassed: true",
    )

    with pytest.raises(MusicEvidenceError, match="roadmap marker is missing"):
        ScoreEditorEvidenceAdapter(client).collect()


def test_score_following_snapshot_preserves_research_authority_boundary() -> None:
    payload = ScoreFollowingEvidenceAdapter(_following_client()).collect().as_dict()

    assert payload["project"] == "real_time_score_following"
    assert payload["authority"] == "permanent_research_evidence"
    assert payload["claims"]["completed_stage"] == "SF-11"
    assert payload["claims"]["next_stage"] == "SF-12"
    assert payload["claims"]["research_evidence_is_production_authority"] is False
    assert payload["claims"]["research_evidence_is_pedagogical_authority"] is False
    assert payload["claims"]["acoustic_mono_mixture_authority"] is False
    assert payload["claims"]["shared_confidence_status"] == "unavailable"
    assert payload["claims"]["sf11_ci_jobs_passed"] == 9
    assert len(payload["sources"]) == 2


def test_score_following_snapshot_fails_closed_if_permanent_evidence_drifts() -> None:
    client = _following_client()
    client.files["benchmarks/reports/SF11_MIXED_ENSEMBLE.md"]["content"] = _sf11_report().replace(
        "Shared confidence unavailable.",
        "Shared confidence 0.99.",
    )

    with pytest.raises(MusicEvidenceError, match="SF-11 permanent evidence marker is missing"):
        ScoreFollowingEvidenceAdapter(client).collect()


def test_full_music_toolset_registers_four_snapshot_tools() -> None:
    registry = ToolRegistry()
    toolset = FullMusicDomainToolset(
        score_restore=ScoreRestoreEvidenceAdapter(
            _unused_client("khfy7wpr5p-maker/st-score-restore-engine")
        ),
        musicxml_tab=MusicXmlTabEvidenceAdapter(
            _unused_client("khfy7wpr5p-maker/musicxml-to-guitar-tab-engine")
        ),
        score_editor=ScoreEditorEvidenceAdapter(_editor_client()),
        score_following=ScoreFollowingEvidenceAdapter(_following_client()),
    )
    toolset.register_into(registry)

    assert registry.names() == (
        "music.score_editor.snapshot",
        "music.score_following.snapshot",
        "music.score_restore.snapshot",
        "music.tab_engine.capability_snapshot",
    )
