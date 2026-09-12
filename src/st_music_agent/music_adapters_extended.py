from __future__ import annotations

import re
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from .agent_tools import ToolRegistry
from .github_read import GitHubReadClient
from .music_adapters import MusicDomainToolset
from .music_evidence import (
    EvidenceAuthority,
    EvidenceSource,
    MusicEvidenceError,
    MusicEvidenceSnapshot,
    MusicProject,
)

_SCORE_EDITOR_REPOSITORY = "khfy7wpr5p-maker/st-score-editor-core"
_SCORE_EDITOR_ROADMAP_PATH = "ROADMAP.md"

_SCORE_FOLLOWING_REPOSITORY = "khfy7wpr5p-maker/st-real-time-score-following-lab"
_SCORE_FOLLOWING_README_PATH = "README.md"
_SCORE_FOLLOWING_SF12_PATH = "benchmarks/reports/SF12_ORCHESTRA_GLOBAL.md"

_EDITOR_NEXT = re.compile(
    r"\*\*(APP-11J — Triplet Removal / Unretiming Admission Foundation\.)\*\*"
)
_FOLLOWING_HEAD = re.compile(r"Implementation head: `([0-9a-f]{40})`")
_FOLLOWING_CI = re.compile(r"Implementation CI: `(\d+)`")
_FOLLOWING_AUTHORITY = re.compile(
    r"Authority boundary:\s*\n\s*`([^`]+)`",
    re.MULTILINE,
)


@dataclass(frozen=True, slots=True)
class _TextEvidence:
    content: str
    source: EvidenceSource


def _read_text(client: GitHubReadClient, path: str, ref: str) -> _TextEvidence:
    result = client.read_file(path, ref)
    if result.get("truncated") is True:
        raise MusicEvidenceError(f"evidence file is truncated: {path}")
    content = result.get("content")
    sha = result.get("sha")
    if not isinstance(content, str):
        raise MusicEvidenceError(f"evidence file is not text: {path}")
    if not isinstance(sha, str) or not sha:
        raise MusicEvidenceError(f"evidence file is missing blob SHA: {path}")
    return _TextEvidence(
        content=content,
        source=EvidenceSource(
            repository=client.config.repository,
            ref=ref,
            path=path,
            blob_sha=sha,
        ),
    )


def _require_repository(client: GitHubReadClient, expected: str) -> None:
    if client.config.repository != expected:
        raise MusicEvidenceError(
            f"adapter requires repository {expected}, got {client.config.repository}"
        )


def _require_marker(text: str, marker: str, label: str) -> None:
    if marker not in text:
        raise MusicEvidenceError(f"{label} marker is missing")


def _extract(pattern: re.Pattern[str], text: str, label: str) -> str:
    match = pattern.search(text)
    if match is None:
        raise MusicEvidenceError(f"{label} is missing")
    return match.group(1)


@dataclass(slots=True)
class ScoreEditorEvidenceAdapter:
    client: GitHubReadClient

    def collect(self, ref: str = "main") -> MusicEvidenceSnapshot:
        _require_repository(self.client, _SCORE_EDITOR_REPOSITORY)
        roadmap = _read_text(self.client, _SCORE_EDITOR_ROADMAP_PATH, ref)

        required_markers = (
            "Repository reality only. Planned capability is not production capability.",
            "APP-11I — Session + Browser Triplet Retiming",
            "COMPLETE / MERGED — PR #140 / merge `6b0e2cac572dfcfa570bfab2bb8eb47a9d7f68fc`.",
            "one user action / one history revision",
            "Triplet removal/unretiming until APP-11J or later explicitly admits it",
            "manualDeviceValidationRequired = true",
            "standaloneReleaseGatePassed = false",
            "seslitabCutoverAuthorized = false",
            "SesliTab is outside this core-development track and is not an architectural dependency.",
        )
        for marker in required_markers:
            _require_marker(roadmap.content, marker, "Score Editor roadmap")

        next_action = _extract(_EDITOR_NEXT, roadmap.content, "Score Editor next action")

        claims = {
            "repository_reality_is_source_of_truth": True,
            "planned_capability_is_production_capability": False,
            "app_11i_complete_merged": True,
            "triplet_retiming_productized": True,
            "one_user_action_one_history_revision": True,
            "triplet_removal_unretiming_authorized": False,
            "current_product_phase": "APP-11I complete / APP-11J analysis-first next",
            "manual_device_validation_required": True,
            "standalone_release_gate_passed": False,
            "seslitab_cutover_authorized": False,
            "next_development_action": next_action,
            "release_gate_may_open_during_feature_development": False,
        }
        return MusicEvidenceSnapshot(
            project=MusicProject.SCORE_EDITOR,
            authority=EvidenceAuthority.REPOSITORY_SOURCE_OF_TRUTH,
            state="APP11I_COMPLETE_APP11J_NEXT_RELEASE_GATED",
            summary=(
                "Score Editor has merged productized straight-three Triplet retiming through "
                "APP-11I with one user action / one history revision. Triplet removal/unretiming "
                "remains fail-closed pending APP-11J analysis, while physical release validation "
                "and product cutover remain closed."
            ),
            claims=claims,
            warnings=(
                "Triplet removal/unretiming remains unadmitted until APP-11J or later",
                "real-device/browser release matrix remains incomplete",
                "standalone release and SesliTab cutover remain unauthorized",
            ),
            next_safe_boundary=next_action,
            sources=(roadmap.source,),
        )


@dataclass(slots=True)
class ScoreFollowingEvidenceAdapter:
    client: GitHubReadClient

    def collect(self, ref: str = "main") -> MusicEvidenceSnapshot:
        _require_repository(self.client, _SCORE_FOLLOWING_REPOSITORY)
        readme = _read_text(self.client, _SCORE_FOLLOWING_README_PATH, ref)
        sf12 = _read_text(self.client, _SCORE_FOLLOWING_SF12_PATH, ref)

        readme_markers = (
            "SF-12 Orchestra Global Score Following is complete",
            "SF-13 Orchestra Section Research is the next autonomous stage",
            "Experimental evidence is not production or pedagogical authority.",
            "SF-04 Solo Violin remains a narrow real-evidence rights gate",
            "Orchestra-global evidence is measure/beat authority only",
        )
        for marker in readme_markers:
            _require_marker(readme.content, marker, "score-following README")

        report_markers = (
            "global orchestra measure/beat tracking only",
            "It does not emit or infer per-instrument transcription",
            "Confidence unavailability remains explicit.",
            "Real orchestral audio validation remains dataset/license-gated.",
            "production readiness or pedagogical authority",
            "SF-12 is **complete for repository-owned deterministic global measure/beat structural evidence",
        )
        for marker in report_markers:
            _require_marker(sf12.content, marker, "SF-12 permanent evidence")

        implementation_head = _extract(_FOLLOWING_HEAD, sf12.content, "SF-12 implementation head")
        ci_run = _extract(_FOLLOWING_CI, sf12.content, "SF-12 CI evidence")
        authority_boundary = _extract(
            _FOLLOWING_AUTHORITY,
            sf12.content,
            "SF-12 authority boundary",
        )

        claims = {
            "completed_stage": "SF-12",
            "next_stage": "SF-13",
            "research_evidence_is_production_authority": False,
            "research_evidence_is_pedagogical_authority": False,
            "global_measure_beat_research_evidence": True,
            "per_instrument_transcription_authority": False,
            "real_orchestral_audio_authority": False,
            "acoustic_mono_mixture_authority": False,
            "calibrated_global_confidence_available": False,
            "shared_confidence_status": "unavailable",
            "sf04_real_evidence_rights_gate_remains": True,
            "sf12_authority_boundary": authority_boundary,
            "sf12_implementation_head": implementation_head,
            "sf12_ci_run": ci_run,
        }
        return MusicEvidenceSnapshot(
            project=MusicProject.REAL_TIME_SCORE_FOLLOWING,
            authority=EvidenceAuthority.PERMANENT_RESEARCH_EVIDENCE,
            state="SF12_COMPLETE_SF13_NEXT_RESEARCH",
            summary=(
                "SF-12 provides validated repository-owned deterministic orchestra-global "
                "measure/beat research evidence. It does not establish per-instrument "
                "transcription, real orchestral-audio robustness, production readiness or "
                "pedagogical authority."
            ),
            claims=claims,
            warnings=(
                "SF-12 evidence is synthetic aggregate-texture measure/beat research, not real orchestral-audio authority",
                "per-instrument and section transcription authority remains explicitly excluded",
                "SF-04 real violin evidence remains a separate rights-gated evidence path",
                "calibrated global confidence remains unavailable rather than synthesized",
            ),
            next_safe_boundary="SF-13 Orchestra Section Research",
            sources=(readme.source, sf12.source),
        )


@dataclass(slots=True)
class FullMusicDomainToolset(MusicDomainToolset):
    score_editor: ScoreEditorEvidenceAdapter
    score_following: ScoreFollowingEvidenceAdapter

    def register_into(self, registry: ToolRegistry) -> None:
        MusicDomainToolset.register_into(self, registry)
        registry.register(
            "music.score_editor.snapshot",
            self._score_editor_snapshot,
            description="Read the bounded Score Editor repository source-of-truth snapshot.",
            parameters=self._ref_schema(),
        )
        registry.register(
            "music.score_following.snapshot",
            self._score_following_snapshot,
            description="Read the bounded real-time score-following research evidence snapshot.",
            parameters=self._ref_schema(),
        )

    def _score_editor_snapshot(self, arguments: Mapping[str, Any]) -> Mapping[str, Any]:
        return self.score_editor.collect(self._ref(arguments)).as_dict()

    def _score_following_snapshot(self, arguments: Mapping[str, Any]) -> Mapping[str, Any]:
        return self.score_following.collect(self._ref(arguments)).as_dict()
