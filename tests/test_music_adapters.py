from __future__ import annotations

import json
from dataclasses import dataclass, field
from types import SimpleNamespace
from typing import Any

import pytest

from st_music_agent.agent_tools import ToolCallRequest, ToolCallStatus, ToolRegistry
from st_music_agent.music_adapters import (
    MusicDomainToolset,
    MusicXmlTabEvidenceAdapter,
    ScoreRestoreEvidenceAdapter,
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


def _score_truth() -> str:
    return json.dumps(
        {
            "schemaVersion": "1.2.0",
            "artifactType": "stage11_v2_symbol_preservation_current_truth",
            "generatedOn": "2026-09-08",
            "state": "V2A_HELDOUT_AND_STAGE9A_PASS_CANDIDATE_FROZEN",
            "v2aConfig": {"modelFamily": "Residual U-Net", "version": "V2a"},
            "v2aResult": {
                "trainingCompleted": True,
                "developmentStatus": "pass",
                "heldoutEvaluationStatus": "completed",
                "officialHeldOutImages": 352,
                "heldoutPreservationGatePassed": True,
                "stage9aStatus": "pass",
                "stage9aProxyOnly": True,
                "heldoutInkRecallDelta": -0.037,
                "heldoutPixelL1ImprovementPercent": 53.77,
                "heldoutEdgeL1ImprovementPercent": 7.46,
                "idealInkRecallTargetReached": False,
                "mseRegressionObserved": True,
            },
            "gates": {
                "candidateCheckpointFrozen": True,
                "finalModelSelected": False,
                "stage12EntryAuthorized": False,
                "productionInferenceAuthorized": False,
            },
            "safety": {
                "omrCorrectnessNotImplied": True,
                "musicalTruthNotImplied": True,
                "automaticProductionPromotionForbidden": True,
            },
            "nextSafeBoundary": "run non-training consumer integration checks",
        }
    )


def _tab_contract() -> str:
    return "\n".join(
        [
            "const REVIEW_REQUIRED_CAPABILITY_CONTRACT_VERSION = '1.0.0';",
            "const MUSICXML_UPLOAD_RESULT_SCHEMA_VERSION = '1.1.0';",
            "if (!renderScore || result.status === 'BLOCKED') return PLAYBACK_CAPABILITY.DISABLED;",
            "if (result.status === 'PASS') return PLAYBACK_CAPABILITY.FULL;",
            "return issues.some((issue) => issue.affects.includes('playback'))",
            "  ? PLAYBACK_CAPABILITY.APPROXIMATE",
            "  : PLAYBACK_CAPABILITY.FULL;",
            "generateTab: tabArtifactAvailable,",
            "editPitch: passed && tabArtifactAvailable,",
            "playback,",
            "export: passed && tabArtifactAvailable,",
            "provisionalTabAvailable: reviewable && tabArtifactAvailable,",
            "canonicalTabAvailable: passed && tabArtifactAvailable,",
        ]
    )


def _tab_test() -> str:
    return """
      renderScore: true,
      generateTab: true,
      playback: 'APPROXIMATE',
      export: false,
    """


def _score_client(*, truncated: bool = False) -> FakeReadClient:
    return FakeReadClient(
        "khfy7wpr5p-maker/st-score-restore-engine",
        {
            "docs/live/ST_SCORE_RESTORE_STAGE11_V2_SYMBOL_PRESERVATION_CURRENT_TRUTH.json": {
                "content": _score_truth(),
                "truncated": truncated,
                "sha": "score-blob-sha",
            }
        },
    )


def _tab_client() -> FakeReadClient:
    return FakeReadClient(
        "khfy7wpr5p-maker/musicxml-to-guitar-tab-engine",
        {
            "src/app/reviewRequiredCapabilityContract.js": {
                "content": _tab_contract(),
                "truncated": False,
                "sha": "contract-blob-sha",
            },
            "tests/workbenchCapabilityBridge.test.js": {
                "content": _tab_test(),
                "truncated": False,
                "sha": "test-blob-sha",
            },
        },
    )


def test_score_restore_snapshot_preserves_closed_production_boundary() -> None:
    snapshot = ScoreRestoreEvidenceAdapter(_score_client()).collect()
    payload = snapshot.as_dict()

    assert payload["schema_version"] == "1.0.0"
    assert payload["project"] == "score_restore"
    assert payload["authority"] == "repository_current_truth"
    assert payload["state"] == "V2A_HELDOUT_AND_STAGE9A_PASS_CANDIDATE_FROZEN"
    assert payload["claims"]["training_completed"] is True
    assert payload["claims"]["stage9a_status"] == "pass"
    assert payload["claims"]["candidate_checkpoint_frozen"] is True
    assert payload["claims"]["production_inference_authorized"] is False
    assert payload["claims"]["stage12_entry_authorized"] is False
    assert payload["claims"]["omr_correctness_implied"] is False
    assert payload["claims"]["musical_truth_implied"] is False
    assert "production inference remains unauthorized" in payload["warnings"]
    assert payload["sources"][0]["blob_sha"] == "score-blob-sha"


def test_score_restore_adapter_fails_closed_on_truncated_or_incomplete_truth() -> None:
    with pytest.raises(MusicEvidenceError, match="truncated"):
        ScoreRestoreEvidenceAdapter(_score_client(truncated=True)).collect()

    client = _score_client()
    payload = json.loads(client.files[next(iter(client.files))]["content"])
    del payload["safety"]["musicalTruthNotImplied"]
    client.files[next(iter(client.files))]["content"] = json.dumps(payload)

    with pytest.raises(MusicEvidenceError, match="musicalTruthNotImplied"):
        ScoreRestoreEvidenceAdapter(client).collect()


def test_tab_snapshot_preserves_review_required_capability_semantics() -> None:
    snapshot = MusicXmlTabEvidenceAdapter(_tab_client()).collect()
    payload = snapshot.as_dict()

    assert payload["project"] == "musicxml_guitar_tab"
    assert payload["authority"] == "executable_contract"
    assert payload["claims"]["capability_contract_version"] == "1.0.0"
    assert payload["claims"]["result_schema_version"] == "1.1.0"
    assert payload["claims"]["review_required_is_global_lock"] is False
    assert payload["claims"]["review_required_tab_is_provisional"] is True
    assert payload["claims"]["canonical_tab_requires_pass"] is True
    assert payload["claims"]["export_requires_pass"] is True
    assert payload["claims"]["review_required_playback_can_be_approximate"] is True
    assert len(payload["sources"]) == 2


def test_tab_adapter_fails_closed_when_contract_marker_disappears() -> None:
    client = _tab_client()
    contract = client.files["src/app/reviewRequiredCapabilityContract.js"]
    contract["content"] = contract["content"].replace(
        "export: passed && tabArtifactAvailable,",
        "export: true,",
    )

    with pytest.raises(MusicEvidenceError, match="contract marker missing"):
        MusicXmlTabEvidenceAdapter(client).collect()


def test_adapters_reject_wrong_repository_binding() -> None:
    client = FakeReadClient("other/repo", {})
    with pytest.raises(MusicEvidenceError, match="adapter requires repository"):
        ScoreRestoreEvidenceAdapter(client).collect()


def test_music_toolset_registers_only_read_only_snapshot_tools() -> None:
    registry = ToolRegistry()
    MusicDomainToolset(
        score_restore=ScoreRestoreEvidenceAdapter(_score_client()),
        musicxml_tab=MusicXmlTabEvidenceAdapter(_tab_client()),
    ).register_into(registry)

    assert registry.names() == (
        "music.score_restore.snapshot",
        "music.tab_engine.capability_snapshot",
    )

    result = registry.dispatch(
        ToolCallRequest(
            call_id="call-score",
            tool_name="music.score_restore.snapshot",
            arguments={},
        )
    )
    assert result.status is ToolCallStatus.SUCCESS
    assert result.output["project"] == "score_restore"
    assert result.output["claims"]["production_inference_authorized"] is False
