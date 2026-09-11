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
_SCORE_FOLLOWING_SF11_PATH = "benchmarks/reports/SF11_MIXED_ENSEMBLE.md"

_EDITOR_PHASE = re.compile(r"The project is now in \*\*(.+?)\*\*")
_EDITOR_NEXT = re.compile(r"\*\*(APP-11G — Tuplet Retiming Admission Foundation\.)\*\*")
_FOLLOWING_HEAD = re.compile(r"Implementation head: `([0-9a-f]{40})`")
_FOLLOWING_CI = re.compile(r"CI run `(\d+)` passed all (\d+) jobs")
_FOLLOWING_AUTHORITY = re.compile(r"Authority boundary: `([^`]+)`")


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
            "Repository reality only; planned capability is not production capability.",
            "APP-11F — COMPLETE / MERGED",
            "Manual standalone release matrix — DEFERRED FOR CURRENT DEVELOPMENT / REQUIRED BEFORE RELEASE.",
            "SesliTab V4 product cutover — DEFERRED / NOT AUTHORIZED",
            "manualDeviceValidationRequired: true",
            "standaloneReleaseGatePassed: false",
            "seslitabCutoverAuthorized: false",
            "Do not open release or SesliTab gates as part of feature development.",
        )
        for marker in required_markers:
            _require_marker(roadmap.content, marker, "Score Editor roadmap")

        phase = _extract(_EDITOR_PHASE, roadmap.content, "Score Editor product phase")
        next_action = _extract(_EDITOR_NEXT, roadmap.content, "Score Editor next action")

        claims = {
            "repository_reality_is_source_of_truth": True,
            "planned_capability_is_production_capability": False,
            "app_11f_complete_merged": True,
            "current_product_phase": phase,
            "manual_device_validation_required": True,
            "standalone_release_gate_passed": False,
            "seslitab_cutover_authorized": False,
            "next_development_action": next_action,
            "release_gate_may_open_during_feature_development": False,
        }
        return MusicEvidenceSnapshot(
            project=MusicProject.SCORE_EDITOR,
            authority=EvidenceAuthority.REPOSITORY_SOURCE_OF_TRUTH,
            state="DEVELOPMENT_ACTIVE_RELEASE_GATED",
            summary=(
                "Score Editor has a strong merged authoring baseline through APP-11F, but the "
                "standalone release matrix is still required and SesliTab V4 cutover is not "
                "authorized."
            ),
            claims=claims,
            warnings=(
                "real-device/browser release matrix remains incomplete",
                "SesliTab V4 product cutover remains unauthorized",
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
        sf11 = _read_text(self.client, _SCORE_FOLLOWING_SF11_PATH, ref)

        readme_markers = (
            "SF-11 Mixed Ensemble is complete",
            "SF-12 Orchestra Global Score Following is the next autonomous stage",
            "Experimental evidence is not production or pedagogical authority.",
            "SF-04 Solo Violin remains a narrow real-evidence rights gate",
        )
        for marker in readme_markers:
            _require_marker(readme.content, marker, "score-following README")

        report_markers = (
            "This evidence does **not** establish acoustic mono-mixture source separation",
            "Shared confidence unavailable.",
            "The benchmark is synthetic, repository-owned, and channel-separated.",
            "Asynchrony, divergence, quorum loss, and abstention are evidence states rather than quality grades.",
            "SF-11 is complete for deterministic channel-separated mixed-ensemble provenance",
        )
        for marker in report_markers:
            _require_marker(sf11.content, marker, "SF-11 permanent evidence")

        implementation_head = _extract(_FOLLOWING_HEAD, sf11.content, "SF-11 implementation head")
        ci_match = _FOLLOWING_CI.search(sf11.content)
        if ci_match is None:
            raise MusicEvidenceError("SF-11 CI evidence is missing")
        ci_run = ci_match.group(1)
        ci_jobs = int(ci_match.group(2))
        authority_boundary = _extract(
            _FOLLOWING_AUTHORITY,
            sf11.content,
            "SF-11 authority boundary",
        )

        claims = {
            "completed_stage": "SF-11",
            "next_stage": "SF-12",
            "research_evidence_is_production_authority": False,
            "research_evidence_is_pedagogical_authority": False,
            "channel_separated_deterministic_evidence": True,
            "acoustic_mono_mixture_authority": False,
            "shared_confidence_status": "unavailable",
            "sf04_real_evidence_rights_gate_remains": True,
            "sf11_authority_boundary": authority_boundary,
            "sf11_implementation_head": implementation_head,
            "sf11_ci_run": ci_run,
            "sf11_ci_jobs_passed": ci_jobs,
        }
        return MusicEvidenceSnapshot(
            project=MusicProject.REAL_TIME_SCORE_FOLLOWING,
            authority=EvidenceAuthority.PERMANENT_RESEARCH_EVIDENCE,
            state="SF11_COMPLETE_SF12_NEXT_RESEARCH",
            summary=(
                "SF-11 provides validated deterministic channel-separated mixed-ensemble "
                "research evidence. Orchestra-scale global following is still the next research "
                "stage, and the evidence is not production or pedagogical authority."
            ),
            claims=claims,
            warnings=(
                "SF-11 evidence is synthetic and channel-separated, not acoustic mono-mixture authority",
                "SF-04 real violin evidence remains a separate rights-gated evidence path",
                "shared confidence remains unavailable rather than synthesized",
            ),
            next_safe_boundary="SF-12 Orchestra Global Score Following research",
            sources=(readme.source, sf11.source),
        )


@dataclass(slots=True)
class FullMusicDomainToolset(MusicDomainToolset):
    score_editor: ScoreEditorEvidenceAdapter
    score_following: ScoreFollowingEvidenceAdapter

    def register_into(self, registry: ToolRegistry) -> None:
        super().register_into(registry)
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
