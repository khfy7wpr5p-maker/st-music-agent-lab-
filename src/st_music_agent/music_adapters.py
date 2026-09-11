from __future__ import annotations

import json
import re
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from .agent_tools import ToolRegistry
from .github_read import GitHubReadClient
from .music_evidence import (
    EvidenceAuthority,
    EvidenceSource,
    MusicEvidenceError,
    MusicEvidenceSnapshot,
    MusicProject,
)

_SCORE_RESTORE_REPOSITORY = "khfy7wpr5p-maker/st-score-restore-engine"
_SCORE_RESTORE_TRUTH_PATH = (
    "docs/live/ST_SCORE_RESTORE_STAGE11_V2_SYMBOL_PRESERVATION_CURRENT_TRUTH.json"
)
_SCORE_RESTORE_ARTIFACT_TYPE = "stage11_v2_symbol_preservation_current_truth"
_SCORE_RESTORE_SCHEMA = "1.2.0"

_TAB_REPOSITORY = "khfy7wpr5p-maker/musicxml-to-guitar-tab-engine"
_TAB_CONTRACT_PATH = "src/app/reviewRequiredCapabilityContract.js"
_TAB_TEST_PATH = "tests/workbenchCapabilityBridge.test.js"

_CONTRACT_VERSION = re.compile(
    r"REVIEW_REQUIRED_CAPABILITY_CONTRACT_VERSION\s*=\s*'([^']+)'"
)
_RESULT_SCHEMA_VERSION = re.compile(
    r"MUSICXML_UPLOAD_RESULT_SCHEMA_VERSION\s*=\s*'([^']+)'"
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


def _bool_field(section: Mapping[str, Any], key: str, label: str) -> bool:
    value = section.get(key)
    if not isinstance(value, bool):
        raise MusicEvidenceError(f"{label} must be a boolean")
    return value


@dataclass(slots=True)
class ScoreRestoreEvidenceAdapter:
    client: GitHubReadClient

    def collect(self, ref: str = "main") -> MusicEvidenceSnapshot:
        _require_repository(self.client, _SCORE_RESTORE_REPOSITORY)
        evidence = _read_text(self.client, _SCORE_RESTORE_TRUTH_PATH, ref)
        try:
            payload = json.loads(evidence.content)
        except json.JSONDecodeError as exc:
            raise MusicEvidenceError("Score Restore current-truth JSON is invalid") from exc
        if not isinstance(payload, Mapping):
            raise MusicEvidenceError("Score Restore current-truth must be a JSON object")
        if payload.get("artifactType") != _SCORE_RESTORE_ARTIFACT_TYPE:
            raise MusicEvidenceError("unexpected Score Restore artifact type")
        if payload.get("schemaVersion") != _SCORE_RESTORE_SCHEMA:
            raise MusicEvidenceError("unsupported Score Restore current-truth schema")

        v2a = payload.get("v2aResult")
        gates = payload.get("gates")
        safety = payload.get("safety")
        config = payload.get("v2aConfig")
        if not all(isinstance(value, Mapping) for value in (v2a, gates, safety, config)):
            raise MusicEvidenceError("Score Restore current-truth sections are incomplete")

        production_authorized = _bool_field(
            gates,
            "productionInferenceAuthorized",
            "productionInferenceAuthorized",
        )
        stage12_authorized = _bool_field(
            gates,
            "stage12EntryAuthorized",
            "stage12EntryAuthorized",
        )
        final_model_selected = _bool_field(gates, "finalModelSelected", "finalModelSelected")
        candidate_frozen = _bool_field(
            gates,
            "candidateCheckpointFrozen",
            "candidateCheckpointFrozen",
        )
        omr_not_implied = _bool_field(
            safety,
            "omrCorrectnessNotImplied",
            "omrCorrectnessNotImplied",
        )
        musical_truth_not_implied = _bool_field(
            safety,
            "musicalTruthNotImplied",
            "musicalTruthNotImplied",
        )
        automatic_promotion_forbidden = _bool_field(
            safety,
            "automaticProductionPromotionForbidden",
            "automaticProductionPromotionForbidden",
        )

        claims = {
            "schema_version": payload.get("schemaVersion"),
            "generated_on": payload.get("generatedOn"),
            "model_family": config.get("modelFamily"),
            "model_version": config.get("version"),
            "training_completed": v2a.get("trainingCompleted"),
            "development_status": v2a.get("developmentStatus"),
            "heldout_evaluation_status": v2a.get("heldoutEvaluationStatus"),
            "official_heldout_images": v2a.get("officialHeldOutImages"),
            "heldout_preservation_gate_passed": v2a.get("heldoutPreservationGatePassed"),
            "stage9a_status": v2a.get("stage9aStatus"),
            "stage9a_proxy_only": v2a.get("stage9aProxyOnly"),
            "candidate_checkpoint_frozen": candidate_frozen,
            "final_model_selected": final_model_selected,
            "stage12_entry_authorized": stage12_authorized,
            "production_inference_authorized": production_authorized,
            "heldout_ink_recall_delta": v2a.get("heldoutInkRecallDelta"),
            "heldout_pixel_l1_improvement_percent": v2a.get(
                "heldoutPixelL1ImprovementPercent"
            ),
            "heldout_edge_l1_improvement_percent": v2a.get(
                "heldoutEdgeL1ImprovementPercent"
            ),
            "ideal_ink_recall_target_reached": v2a.get("idealInkRecallTargetReached"),
            "mse_regression_observed": v2a.get("mseRegressionObserved"),
            "omr_correctness_implied": not omr_not_implied,
            "musical_truth_implied": not musical_truth_not_implied,
            "automatic_production_promotion_forbidden": automatic_promotion_forbidden,
        }

        warnings: list[str] = []
        if claims["ideal_ink_recall_target_reached"] is False:
            warnings.append("ideal ink-recall target has not been reached")
        if claims["mse_regression_observed"] is True:
            warnings.append("MSE regression remains explicitly recorded")
        if production_authorized is not True:
            warnings.append("production inference remains unauthorized")
        if stage12_authorized is not True:
            warnings.append("Stage 12 entry remains unauthorized")

        next_boundary = payload.get("nextSafeBoundary")
        if next_boundary is not None and not isinstance(next_boundary, str):
            raise MusicEvidenceError("Score Restore nextSafeBoundary must be text")

        return MusicEvidenceSnapshot(
            project=MusicProject.SCORE_RESTORE,
            authority=EvidenceAuthority.REPOSITORY_CURRENT_TRUTH,
            state=str(payload.get("state") or "UNKNOWN"),
            summary=(
                "Stage 11 V2a is a frozen candidate with held-out and Stage 9A preservation "
                "passes recorded, while production inference and Stage 12 remain closed."
            ),
            claims=claims,
            warnings=tuple(warnings),
            next_safe_boundary=next_boundary,
            sources=(evidence.source,),
        )


@dataclass(slots=True)
class MusicXmlTabEvidenceAdapter:
    client: GitHubReadClient

    def collect(self, ref: str = "main") -> MusicEvidenceSnapshot:
        _require_repository(self.client, _TAB_REPOSITORY)
        contract = _read_text(self.client, _TAB_CONTRACT_PATH, ref)
        test_evidence = _read_text(self.client, _TAB_TEST_PATH, ref)

        contract_version = self._extract(_CONTRACT_VERSION, contract.content, "contract version")
        result_schema = self._extract(
            _RESULT_SCHEMA_VERSION,
            contract.content,
            "result schema version",
        )
        required_contract_markers = (
            "generateTab: tabArtifactAvailable",
            "editPitch: passed && tabArtifactAvailable",
            "playback,",
            "export: passed && tabArtifactAvailable",
            "provisionalTabAvailable: reviewable && tabArtifactAvailable",
            "canonicalTabAvailable: passed && tabArtifactAvailable",
            "if (!renderScore || result.status === 'BLOCKED')",
            "if (result.status === 'PASS') return PLAYBACK_CAPABILITY.FULL",
            "? PLAYBACK_CAPABILITY.APPROXIMATE",
        )
        for marker in required_contract_markers:
            if marker not in contract.content:
                raise MusicEvidenceError(f"TAB capability contract marker missing: {marker}")

        required_test_markers = (
            "renderScore: true",
            "generateTab: true",
            "playback: 'APPROXIMATE'",
            "export: false",
        )
        for marker in required_test_markers:
            if marker not in test_evidence.content:
                raise MusicEvidenceError(f"TAB workbench evidence marker missing: {marker}")

        claims = {
            "capability_contract_version": contract_version,
            "result_schema_version": result_schema,
            "review_required_is_global_lock": False,
            "review_required_score_can_render_when_musicxml_available": True,
            "review_required_tab_can_be_generated_when_tab_artifact_available": True,
            "review_required_tab_is_provisional": True,
            "canonical_tab_requires_pass": True,
            "export_requires_pass": True,
            "review_required_playback_can_be_approximate": True,
            "blocked_playback_is_disabled": True,
            "review_required_edit_pitch_advertised": False,
            "review_required_edit_rhythm_advertised": False,
            "review_required_edit_voice_advertised": False,
            "review_required_edit_structure_advertised": False,
        }
        return MusicEvidenceSnapshot(
            project=MusicProject.MUSICXML_GUITAR_TAB,
            authority=EvidenceAuthority.EXECUTABLE_CONTRACT,
            state="CAPABILITY_CONTRACT_ACTIVE",
            summary=(
                "REVIEW_REQUIRED is capability-driven rather than a global lock: readable scores "
                "and available TAB artifacts may remain usable, while canonical export stays "
                "PASS-only and uncertain playback may be approximate."
            ),
            claims=claims,
            warnings=(
                "teacher revision/edit capabilities remain deliberately narrower than score/TAB visibility",
            ),
            next_safe_boundary=(
                "connect teacher-revision runtime without weakening PASS-only canonical export or "
                "BLOCKED safety behavior"
            ),
            sources=(contract.source, test_evidence.source),
        )

    @staticmethod
    def _extract(pattern: re.Pattern[str], text: str, label: str) -> str:
        match = pattern.search(text)
        if match is None:
            raise MusicEvidenceError(f"TAB capability {label} is missing")
        return match.group(1)


@dataclass(slots=True)
class MusicDomainToolset:
    score_restore: ScoreRestoreEvidenceAdapter
    musicxml_tab: MusicXmlTabEvidenceAdapter

    def register_into(self, registry: ToolRegistry) -> None:
        registry.register(
            "music.score_restore.snapshot",
            self._score_restore_snapshot,
            description=(
                "Read the bounded authoritative Stage 11 Score Restore current-truth snapshot."
            ),
            parameters=self._ref_schema(),
        )
        registry.register(
            "music.tab_engine.capability_snapshot",
            self._tab_snapshot,
            description=(
                "Read the bounded MusicXML-to-Guitar-TAB REVIEW_REQUIRED capability contract snapshot."
            ),
            parameters=self._ref_schema(),
        )

    def _score_restore_snapshot(self, arguments: Mapping[str, Any]) -> Mapping[str, Any]:
        return self.score_restore.collect(self._ref(arguments)).as_dict()

    def _tab_snapshot(self, arguments: Mapping[str, Any]) -> Mapping[str, Any]:
        return self.musicxml_tab.collect(self._ref(arguments)).as_dict()

    @staticmethod
    def _ref(arguments: Mapping[str, Any]) -> str:
        extras = set(arguments) - {"ref"}
        if extras:
            raise ValueError("tool arguments contain unsupported fields")
        ref = arguments.get("ref", "main")
        if not isinstance(ref, str) or not ref.strip():
            raise TypeError("ref must be non-empty text")
        return ref

    @staticmethod
    def _ref_schema() -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {"ref": {"type": "string", "default": "main"}},
            "additionalProperties": False,
        }
