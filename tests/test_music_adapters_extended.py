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
Repository reality only. Planned capability is not production capability.
### APP-11I — Session + Browser Triplet Retiming
**COMPLETE / MERGED — PR #140 / merge `6b0e2cac572dfcfa570bfab2bb8eb47a9d7f68fc`.**
APP-11H is productized through EditorSessionV4 and the standalone browser runtime.
-> EditorSessionV4 one user action / one history revision
**APP-11J — Triplet Removal / Unretiming Admission Foundation.**
Triplet removal/unretiming until APP-11J or later explicitly admits it;
manualDeviceValidationRequired = true
standaloneReleaseGatePassed = false
seslitabCutoverAuthorized = false
SesliTab is outside this core-development track and is not an architectural dependency.
"""


def _following_readme() -> str:
    return """
Orchestra-global evidence is measure/beat authority only; aggregate texture matching must not be presented as per-instrument transcription.
Experimental evidence is not production or pedagogical authority.
**SF-12 Orchestra Global Score Following is complete for repository-owned deterministic global measure/beat structural evidence with explicit real-audio limitations. SF-13 Orchestra Section Research is the next autonomous stage.**
SF-04 Solo Violin remains a narrow real-evidence rights gate and does not block independent stages.
"""


def _sf12_report() -> str:
    return """
SF-12 establishes a repository-owned deterministic baseline for **global orchestra measure/beat tracking only**.
It does not emit or infer per-instrument transcription, section identity, source separation, conductor intent, or pedagogical judgment.
Authority boundary:
`global_measure_beat_research_not_per_instrument_transcription_authority`
Implementation CI: `34678255101`
Implementation head: `7f023613697a3ae999bb0f2ebc6fd86d5adbde72`
Confidence unavailability remains explicit.
Real orchestral audio validation remains dataset/license-gated.
The evidence does not support production readiness or pedagogical authority.
SF-12 is **complete for repository-owned deterministic global measure/beat structural evidence with a well-characterized real-audio limitation**.
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
            "benchmarks/reports/SF12_ORCHESTRA_GLOBAL.md": {
                "content": _sf12_report(),
                "truncated": False,
                "sha": "sf12-sha",
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
    assert payload["state"] == "APP11I_COMPLETE_APP11J_NEXT_RELEASE_GATED"
    assert payload["claims"]["app_11i_complete_merged"] is True
    assert payload["claims"]["triplet_retiming_productized"] is True
    assert payload["claims"]["one_user_action_one_history_revision"] is True
    assert payload["claims"]["triplet_removal_unretiming_authorized"] is False
    assert payload["claims"]["manual_device_validation_required"] is True
    assert payload["claims"]["standalone_release_gate_passed"] is False
    assert payload["claims"]["seslitab_cutover_authorized"] is False
    assert payload["claims"]["release_gate_may_open_during_feature_development"] is False
    assert payload["claims"]["next_development_action"] == (
        "APP-11J — Triplet Removal / Unretiming Admission Foundation."
    )
    assert payload["sources"][0]["blob_sha"] == "editor-sha"


def test_score_editor_snapshot_fails_closed_if_release_marker_drifts() -> None:
    client = _editor_client()
    client.files["ROADMAP.md"]["content"] = _editor_roadmap().replace(
        "standaloneReleaseGatePassed = false",
        "standaloneReleaseGatePassed = true",
    )

    with pytest.raises(MusicEvidenceError, match="roadmap marker is missing"):
        ScoreEditorEvidenceAdapter(client).collect()


def test_score_editor_snapshot_fails_closed_if_next_stage_drift_is_unreviewed() -> None:
    client = _editor_client()
    client.files["ROADMAP.md"]["content"] = _editor_roadmap().replace(
        "APP-11J — Triplet Removal / Unretiming Admission Foundation.",
        "APP-11K — Unreviewed future stage.",
    )

    with pytest.raises(MusicEvidenceError, match="next action is missing"):
        ScoreEditorEvidenceAdapter(client).collect()


def test_score_following_snapshot_preserves_research_authority_boundary() -> None:
    payload = ScoreFollowingEvidenceAdapter(_following_client()).collect().as_dict()

    assert payload["project"] == "real_time_score_following"
    assert payload["authority"] == "permanent_research_evidence"
    assert payload["state"] == "SF12_COMPLETE_SF13_NEXT_RESEARCH"
    assert payload["claims"]["completed_stage"] == "SF-12"
    assert payload["claims"]["next_stage"] == "SF-13"
    assert payload["claims"]["research_evidence_is_production_authority"] is False
    assert payload["claims"]["research_evidence_is_pedagogical_authority"] is False
    assert payload["claims"]["global_measure_beat_research_evidence"] is True
    assert payload["claims"]["per_instrument_transcription_authority"] is False
    assert payload["claims"]["real_orchestral_audio_authority"] is False
    assert payload["claims"]["acoustic_mono_mixture_authority"] is False
    assert payload["claims"]["calibrated_global_confidence_available"] is False
    assert payload["claims"]["shared_confidence_status"] == "unavailable"
    assert payload["claims"]["sf12_ci_run"] == "34678255101"
    assert payload["claims"]["sf12_implementation_head"] == (
        "7f023613697a3ae999bb0f2ebc6fd86d5adbde72"
    )
    assert len(payload["sources"]) == 2


def test_score_following_snapshot_fails_closed_if_permanent_evidence_drifts() -> None:
    client = _following_client()
    client.files["benchmarks/reports/SF12_ORCHESTRA_GLOBAL.md"]["content"] = _sf12_report().replace(
        "Confidence unavailability remains explicit.",
        "Calibrated confidence is available.",
    )

    with pytest.raises(MusicEvidenceError, match="SF-12 permanent evidence marker is missing"):
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
