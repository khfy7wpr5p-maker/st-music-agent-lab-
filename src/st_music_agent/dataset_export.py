from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from enum import Enum
from typing import Any

from .execution_outcome import ExecutionRecord

DATASET_EXPORT_SCHEMA_VERSION = "1.0.0"
_DATASET_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}$")


class DatasetExportError(RuntimeError):
    pass


class DatasetPurpose(str, Enum):
    OFFLINE_EVALUATION = "offline_evaluation"
    FINE_TUNING_CANDIDATE = "fine_tuning_candidate"


@dataclass(frozen=True, slots=True)
class CuratedDatasetSelection:
    dataset_id: str
    purpose: DatasetPurpose
    record_ids: tuple[str, ...]

    def __post_init__(self) -> None:
        if not _DATASET_ID.fullmatch(self.dataset_id):
            raise ValueError("dataset_id has an invalid format")
        if not self.record_ids:
            raise ValueError("dataset selection must contain record ids")
        if len(self.record_ids) != len(set(self.record_ids)):
            raise ValueError("dataset record ids must be unique")
        if any(not re.fullmatch(r"[0-9a-f]{64}", record_id) for record_id in self.record_ids):
            raise ValueError("dataset record ids must be execution record SHA-256 ids")


@dataclass(frozen=True, slots=True)
class CuratedDatasetExport:
    dataset_id: str
    purpose: DatasetPurpose
    source_record_ids: tuple[str, ...]
    rows: tuple[dict[str, Any], ...]
    manifest_hash: str
    training_authorized: bool = False
    auto_train: bool = False
    auto_promote: bool = False

    def as_dict(self) -> dict[str, Any]:
        return {
            "schema_version": DATASET_EXPORT_SCHEMA_VERSION,
            "dataset_id": self.dataset_id,
            "purpose": self.purpose.value,
            "source_record_ids": list(self.source_record_ids),
            "rows": [dict(row) for row in self.rows],
            "manifest_hash": self.manifest_hash,
            "training_authorized": self.training_authorized,
            "auto_train": self.auto_train,
            "auto_promote": self.auto_promote,
        }


class CuratedDatasetBuilder:
    """Host-side deterministic exporter from verified execution records.

    The export contains structured outcome facts only. It deliberately excludes free-form notes,
    provider messages and hidden reasoning, and never grants training or promotion authority.
    """

    def build(
        self,
        records: tuple[ExecutionRecord, ...],
        selection: CuratedDatasetSelection,
    ) -> CuratedDatasetExport:
        by_id = {record.record_id: record for record in records}
        if len(by_id) != len(records):
            raise DatasetExportError("execution record ids are not unique")
        missing = [record_id for record_id in selection.record_ids if record_id not in by_id]
        if missing:
            raise DatasetExportError("dataset selection references unknown execution records")

        selected = tuple(by_id[record_id] for record_id in selection.record_ids)
        rows = tuple(self._row(record) for record in selected)
        manifest_base = {
            "schema_version": DATASET_EXPORT_SCHEMA_VERSION,
            "dataset_id": selection.dataset_id,
            "purpose": selection.purpose.value,
            "source_record_ids": list(selection.record_ids),
            "rows": rows,
            "training_authorized": False,
            "auto_train": False,
            "auto_promote": False,
        }
        encoded = json.dumps(
            manifest_base,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        ).encode("utf-8")
        return CuratedDatasetExport(
            dataset_id=selection.dataset_id,
            purpose=selection.purpose,
            source_record_ids=selection.record_ids,
            rows=rows,
            manifest_hash=hashlib.sha256(encoded).hexdigest(),
            training_authorized=False,
            auto_train=False,
            auto_promote=False,
        )

    @staticmethod
    def _row(record: ExecutionRecord) -> dict[str, Any]:
        return {
            "project": record.project.value,
            "plan_id": record.plan_id,
            "candidate_rank": record.candidate_rank,
            "action": record.action,
            "candidate_evidence_hash": record.candidate_evidence_hash,
            "repository": record.repository,
            "branch": record.branch,
            "commit_sha": record.commit_sha,
            "outcome": record.outcome.value,
            "ci": [check.as_dict() for check in record.ci_checks],
            "validators": [check.as_dict() for check in record.validator_checks],
        }
