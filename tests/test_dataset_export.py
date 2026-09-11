import pytest

from st_music_agent.dataset_export import (
    CuratedDatasetBuilder,
    CuratedDatasetSelection,
    DatasetExportError,
    DatasetPurpose,
)
from st_music_agent.execution_outcome import (
    EvidenceCheckStatus,
    ExecutionCheck,
    ExecutionOutcomeStatus,
    ExecutionRecord,
)
from st_music_agent.music_evidence import MusicProject


def _record(record_id: str, *, outcome: ExecutionOutcomeStatus) -> ExecutionRecord:
    return ExecutionRecord(
        record_id=record_id,
        sequence=1,
        timestamp="2026-09-11T08:00:00+00:00",
        plan_id="b" * 64,
        project=MusicProject.SCORE_RESTORE,
        candidate_rank=1,
        action="run non-training consumer integration checks",
        candidate_evidence_hash="a" * 64,
        repository="khfy7wpr5p-maker/st-score-restore-engine",
        branch="agent/integration-checks",
        commit_sha="d" * 40,
        outcome=outcome,
        ci_checks=(
            ExecutionCheck("core-ci", EvidenceCheckStatus.SUCCESS, "ci:123"),
        ),
        validator_checks=(
            ExecutionCheck(
                "restore-validator",
                EvidenceCheckStatus.SUCCESS,
                "validator:456",
            ),
        ),
        notes=("free form note that must not be exported",),
    )


def test_curated_export_contains_structured_facts_without_notes_or_training_authority() -> None:
    records = (
        _record("1" * 64, outcome=ExecutionOutcomeStatus.SUCCESS),
        _record("2" * 64, outcome=ExecutionOutcomeStatus.SUCCESS),
    )
    selection = CuratedDatasetSelection(
        dataset_id="restore.integration.v1",
        purpose=DatasetPurpose.FINE_TUNING_CANDIDATE,
        record_ids=("1" * 64, "2" * 64),
    )

    export = CuratedDatasetBuilder().build(records, selection)
    payload = export.as_dict()

    assert payload["training_authorized"] is False
    assert payload["auto_train"] is False
    assert payload["auto_promote"] is False
    assert payload["source_record_ids"] == ["1" * 64, "2" * 64]
    assert "notes" not in payload["rows"][0]
    assert "reasoning" not in payload["rows"][0]
    assert payload["rows"][0]["commit_sha"] == "d" * 40
    assert len(payload["manifest_hash"]) == 64


def test_selection_is_explicit_and_unknown_records_fail_closed() -> None:
    records = (_record("1" * 64, outcome=ExecutionOutcomeStatus.SUCCESS),)
    selection = CuratedDatasetSelection(
        dataset_id="offline.eval.v1",
        purpose=DatasetPurpose.OFFLINE_EVALUATION,
        record_ids=("2" * 64,),
    )

    with pytest.raises(DatasetExportError, match="unknown execution records"):
        CuratedDatasetBuilder().build(records, selection)


def test_manifest_changes_when_source_selection_changes() -> None:
    records = (
        _record("1" * 64, outcome=ExecutionOutcomeStatus.SUCCESS),
        _record("2" * 64, outcome=ExecutionOutcomeStatus.SUCCESS),
    )
    builder = CuratedDatasetBuilder()
    first = builder.build(
        records,
        CuratedDatasetSelection(
            dataset_id="dataset.v1",
            purpose=DatasetPurpose.OFFLINE_EVALUATION,
            record_ids=("1" * 64,),
        ),
    )
    second = builder.build(
        records,
        CuratedDatasetSelection(
            dataset_id="dataset.v1",
            purpose=DatasetPurpose.OFFLINE_EVALUATION,
            record_ids=("1" * 64, "2" * 64),
        ),
    )

    assert first.manifest_hash != second.manifest_hash


def test_duplicate_or_malformed_selection_ids_are_rejected() -> None:
    with pytest.raises(ValueError, match="unique"):
        CuratedDatasetSelection(
            dataset_id="dataset.v1",
            purpose=DatasetPurpose.OFFLINE_EVALUATION,
            record_ids=("1" * 64, "1" * 64),
        )

    with pytest.raises(ValueError, match="SHA-256"):
        CuratedDatasetSelection(
            dataset_id="dataset.v1",
            purpose=DatasetPurpose.OFFLINE_EVALUATION,
            record_ids=("not-a-record-id",),
        )
