from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Mapping
from dataclasses import dataclass
from enum import Enum
from typing import Any

from .dataset_export import (
    DATASET_EXPORT_SCHEMA_VERSION,
    CuratedDatasetExport,
    DatasetPurpose,
)

TRAINING_RUN_SCHEMA_VERSION = "1.0.0"
_RUN_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}$")
_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_GIT_SHA = re.compile(r"^[0-9a-f]{40}$")


class TrainingRunContractError(RuntimeError):
    pass


class TrainingRunOutcome(str, Enum):
    COMPLETED = "completed"
    FAILED = "failed"
    ABSTAINED = "abstained"


def _canonical_hash(value: Any) -> str:
    try:
        encoded = json.dumps(
            value,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        ).encode("utf-8")
    except (TypeError, ValueError) as exc:
        raise TrainingRunContractError("value is not canonical JSON") from exc
    return hashlib.sha256(encoded).hexdigest()


def _dataset_manifest_hash(dataset: CuratedDatasetExport) -> str:
    manifest_base = {
        "schema_version": DATASET_EXPORT_SCHEMA_VERSION,
        "dataset_id": dataset.dataset_id,
        "purpose": dataset.purpose.value,
        "source_record_ids": list(dataset.source_record_ids),
        "rows": [dict(row) for row in dataset.rows],
        "training_authorized": False,
        "auto_train": False,
        "auto_promote": False,
    }
    return _canonical_hash(manifest_base)


@dataclass(frozen=True, slots=True)
class TrainingRunSpec:
    run_id: str
    dataset_id: str
    dataset_manifest_hash: str
    base_model_id: str
    base_model_revision: str
    base_model_sha256: str
    trainer_name: str
    trainer_version: str
    trainer_config: Mapping[str, Any]
    trainer_config_hash: str
    seed: int
    code_repository: str
    code_commit_sha: str
    input_fingerprint: str
    execution_authorized: bool = False
    auto_start: bool = False

    def as_dict(self) -> dict[str, Any]:
        return {
            "schema_version": TRAINING_RUN_SCHEMA_VERSION,
            "run_id": self.run_id,
            "dataset_id": self.dataset_id,
            "dataset_manifest_hash": self.dataset_manifest_hash,
            "base_model_id": self.base_model_id,
            "base_model_revision": self.base_model_revision,
            "base_model_sha256": self.base_model_sha256,
            "trainer_name": self.trainer_name,
            "trainer_version": self.trainer_version,
            "trainer_config": dict(self.trainer_config),
            "trainer_config_hash": self.trainer_config_hash,
            "seed": self.seed,
            "code_repository": self.code_repository,
            "code_commit_sha": self.code_commit_sha,
            "input_fingerprint": self.input_fingerprint,
            "execution_authorized": self.execution_authorized,
            "auto_start": self.auto_start,
        }


@dataclass(frozen=True, slots=True)
class TrainingRunCompletion:
    run_id: str
    input_fingerprint: str
    outcome: TrainingRunOutcome
    authorization_ref: str
    checkpoint_sha256: str | None
    evidence_refs: tuple[str, ...]
    completion_fingerprint: str
    evaluation_required: bool = True
    promotion_authorized: bool = False
    auto_promote: bool = False

    def as_dict(self) -> dict[str, Any]:
        return {
            "schema_version": TRAINING_RUN_SCHEMA_VERSION,
            "run_id": self.run_id,
            "input_fingerprint": self.input_fingerprint,
            "outcome": self.outcome.value,
            "authorization_ref": self.authorization_ref,
            "checkpoint_sha256": self.checkpoint_sha256,
            "evidence_refs": list(self.evidence_refs),
            "completion_fingerprint": self.completion_fingerprint,
            "evaluation_required": self.evaluation_required,
            "promotion_authorized": self.promotion_authorized,
            "auto_promote": self.auto_promote,
        }


class TrainingRunContractBuilder:
    """Creates reproducible host-side training specs and binds completed outcomes.

    This contract never starts training. A completion requires a host-supplied authorization
    reference and still does not authorize model promotion.
    """

    def create_spec(
        self,
        dataset: CuratedDatasetExport,
        *,
        run_id: str,
        base_model_id: str,
        base_model_revision: str,
        base_model_sha256: str,
        trainer_name: str,
        trainer_version: str,
        trainer_config: Mapping[str, Any],
        seed: int,
        code_repository: str,
        code_commit_sha: str,
    ) -> TrainingRunSpec:
        self._validate_dataset(dataset)
        self._require_text(run_id, "run_id")
        if not _RUN_ID.fullmatch(run_id):
            raise ValueError("run_id has an invalid format")
        for label, value in (
            ("base_model_id", base_model_id),
            ("base_model_revision", base_model_revision),
            ("trainer_name", trainer_name),
            ("trainer_version", trainer_version),
            ("code_repository", code_repository),
        ):
            self._require_text(value, label)
        if not _SHA256.fullmatch(base_model_sha256):
            raise ValueError("base_model_sha256 must be a lowercase SHA-256 digest")
        if not _GIT_SHA.fullmatch(code_commit_sha):
            raise ValueError("code_commit_sha must be a full lowercase Git commit SHA")
        if not isinstance(seed, int) or isinstance(seed, bool) or not 0 <= seed <= 2**32 - 1:
            raise ValueError("seed must be an integer between 0 and 2^32-1")
        if not isinstance(trainer_config, Mapping) or not trainer_config:
            raise ValueError("trainer_config must be a non-empty mapping")

        config = dict(trainer_config)
        config_hash = _canonical_hash(config)
        fingerprint_base = {
            "schema_version": TRAINING_RUN_SCHEMA_VERSION,
            "run_id": run_id,
            "dataset_id": dataset.dataset_id,
            "dataset_manifest_hash": dataset.manifest_hash,
            "base_model_id": base_model_id,
            "base_model_revision": base_model_revision,
            "base_model_sha256": base_model_sha256,
            "trainer_name": trainer_name,
            "trainer_version": trainer_version,
            "trainer_config": config,
            "trainer_config_hash": config_hash,
            "seed": seed,
            "code_repository": code_repository,
            "code_commit_sha": code_commit_sha,
            "execution_authorized": False,
            "auto_start": False,
        }
        return TrainingRunSpec(
            run_id=run_id,
            dataset_id=dataset.dataset_id,
            dataset_manifest_hash=dataset.manifest_hash,
            base_model_id=base_model_id,
            base_model_revision=base_model_revision,
            base_model_sha256=base_model_sha256,
            trainer_name=trainer_name,
            trainer_version=trainer_version,
            trainer_config=config,
            trainer_config_hash=config_hash,
            seed=seed,
            code_repository=code_repository,
            code_commit_sha=code_commit_sha,
            input_fingerprint=_canonical_hash(fingerprint_base),
            execution_authorized=False,
            auto_start=False,
        )

    def bind_completion(
        self,
        spec: TrainingRunSpec,
        *,
        authorization_ref: str,
        checkpoint_sha256: str,
        evidence_refs: tuple[str, ...],
    ) -> TrainingRunCompletion:
        self._validate_spec(spec)
        self._require_evidence(authorization_ref, evidence_refs)
        if not _SHA256.fullmatch(checkpoint_sha256):
            raise ValueError("checkpoint_sha256 must be a lowercase SHA-256 digest")
        return self._completion(
            spec,
            outcome=TrainingRunOutcome.COMPLETED,
            authorization_ref=authorization_ref,
            checkpoint_sha256=checkpoint_sha256,
            evidence_refs=evidence_refs,
        )

    def bind_noncompletion(
        self,
        spec: TrainingRunSpec,
        *,
        outcome: TrainingRunOutcome,
        authorization_ref: str,
        evidence_refs: tuple[str, ...],
    ) -> TrainingRunCompletion:
        self._validate_spec(spec)
        if outcome is TrainingRunOutcome.COMPLETED:
            raise ValueError("completed runs must use bind_completion")
        self._require_evidence(authorization_ref, evidence_refs)
        return self._completion(
            spec,
            outcome=outcome,
            authorization_ref=authorization_ref,
            checkpoint_sha256=None,
            evidence_refs=evidence_refs,
        )

    @staticmethod
    def _validate_dataset(dataset: CuratedDatasetExport) -> None:
        if dataset.purpose is not DatasetPurpose.FINE_TUNING_CANDIDATE:
            raise TrainingRunContractError("training spec requires a fine-tuning-candidate dataset")
        if dataset.training_authorized or dataset.auto_train or dataset.auto_promote:
            raise TrainingRunContractError("dataset authority flags must remain false")
        if not _SHA256.fullmatch(dataset.manifest_hash):
            raise TrainingRunContractError("dataset manifest hash is invalid")
        if _dataset_manifest_hash(dataset) != dataset.manifest_hash:
            raise TrainingRunContractError("dataset manifest hash does not verify")

    @staticmethod
    def _validate_spec(spec: TrainingRunSpec) -> None:
        if spec.execution_authorized or spec.auto_start:
            raise TrainingRunContractError("training spec must not authorize or auto-start training")
        current_config_hash = _canonical_hash(dict(spec.trainer_config))
        if current_config_hash != spec.trainer_config_hash:
            raise TrainingRunContractError("trainer configuration hash does not verify")
        fingerprint_base = spec.as_dict()
        fingerprint_base.pop("input_fingerprint")
        if _canonical_hash(fingerprint_base) != spec.input_fingerprint:
            raise TrainingRunContractError("training input fingerprint does not verify")

    @staticmethod
    def _require_evidence(authorization_ref: str, evidence_refs: tuple[str, ...]) -> None:
        if not isinstance(authorization_ref, str) or not authorization_ref.strip():
            raise ValueError("authorization_ref must be non-empty text")
        if not evidence_refs or any(not ref.strip() for ref in evidence_refs):
            raise ValueError("training completion requires non-empty evidence references")

    @staticmethod
    def _require_text(value: str, label: str) -> None:
        if not isinstance(value, str) or not value.strip():
            raise ValueError(f"{label} must be non-empty text")

    @staticmethod
    def _completion(
        spec: TrainingRunSpec,
        *,
        outcome: TrainingRunOutcome,
        authorization_ref: str,
        checkpoint_sha256: str | None,
        evidence_refs: tuple[str, ...],
    ) -> TrainingRunCompletion:
        base = {
            "schema_version": TRAINING_RUN_SCHEMA_VERSION,
            "run_id": spec.run_id,
            "input_fingerprint": spec.input_fingerprint,
            "outcome": outcome.value,
            "authorization_ref": authorization_ref,
            "checkpoint_sha256": checkpoint_sha256,
            "evidence_refs": list(evidence_refs),
            "evaluation_required": True,
            "promotion_authorized": False,
            "auto_promote": False,
        }
        return TrainingRunCompletion(
            run_id=spec.run_id,
            input_fingerprint=spec.input_fingerprint,
            outcome=outcome,
            authorization_ref=authorization_ref,
            checkpoint_sha256=checkpoint_sha256,
            evidence_refs=evidence_refs,
            completion_fingerprint=_canonical_hash(base),
            evaluation_required=True,
            promotion_authorized=False,
            auto_promote=False,
        )
