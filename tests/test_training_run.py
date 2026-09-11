from __future__ import annotations

import hashlib
import json
from dataclasses import replace

import pytest

from st_music_agent.dataset_export import (
    DATASET_EXPORT_SCHEMA_VERSION,
    CuratedDatasetExport,
    DatasetPurpose,
)
from st_music_agent.training_run import (
    TrainingRunContractBuilder,
    TrainingRunContractError,
    TrainingRunOutcome,
)


def _hash(value: object) -> str:
    encoded = json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _dataset(
    *,
    purpose: DatasetPurpose = DatasetPurpose.FINE_TUNING_CANDIDATE,
) -> CuratedDatasetExport:
    record_ids = ("a" * 64,)
    rows = (
        {
            "project": "score_restore",
            "plan_id": "b" * 64,
            "candidate_rank": 1,
            "action": "run non-training consumer integration checks",
            "candidate_evidence_hash": "c" * 64,
            "repository": "khfy7wpr5p-maker/st-score-restore-engine",
            "branch": "agent/integration-checks",
            "commit_sha": "d" * 40,
            "outcome": "success",
            "ci": [{"name": "core-ci", "status": "success", "evidence_ref": "ci:123"}],
            "validators": [
                {
                    "name": "restore-validator",
                    "status": "success",
                    "evidence_ref": "validator:456",
                }
            ],
        },
    )
    manifest_base = {
        "schema_version": DATASET_EXPORT_SCHEMA_VERSION,
        "dataset_id": "training-candidate-1",
        "purpose": purpose.value,
        "source_record_ids": list(record_ids),
        "rows": [dict(row) for row in rows],
        "training_authorized": False,
        "auto_train": False,
        "auto_promote": False,
    }
    return CuratedDatasetExport(
        dataset_id="training-candidate-1",
        purpose=purpose,
        source_record_ids=record_ids,
        rows=rows,
        manifest_hash=_hash(manifest_base),
        training_authorized=False,
        auto_train=False,
        auto_promote=False,
    )


def _spec():
    return TrainingRunContractBuilder().create_spec(
        _dataset(),
        run_id="train:restore:v1",
        base_model_id="open-model/base",
        base_model_revision="refs/tags/v1.2.3",
        base_model_sha256="e" * 64,
        trainer_name="st-trainer",
        trainer_version="1.0.0",
        trainer_config={
            "learning_rate": 0.0001,
            "epochs": 3,
            "gradient_accumulation": 4,
        },
        seed=20260911,
        code_repository="khfy7wpr5p-maker/st-music-agent-lab-",
        code_commit_sha="f" * 40,
    )


def test_training_spec_binds_all_reproducibility_inputs_without_authority() -> None:
    spec = _spec()

    assert spec.dataset_manifest_hash == _dataset().manifest_hash
    assert spec.base_model_sha256 == "e" * 64
    assert spec.trainer_config_hash
    assert spec.input_fingerprint
    assert spec.seed == 20260911
    assert spec.execution_authorized is False
    assert spec.auto_start is False


def test_identical_inputs_are_deterministic_and_material_changes_rehash() -> None:
    first = _spec()
    second = _spec()
    assert first.input_fingerprint == second.input_fingerprint

    changed = TrainingRunContractBuilder().create_spec(
        _dataset(),
        run_id="train:restore:v1",
        base_model_id="open-model/base",
        base_model_revision="refs/tags/v1.2.3",
        base_model_sha256="e" * 64,
        trainer_name="st-trainer",
        trainer_version="1.0.0",
        trainer_config={
            "learning_rate": 0.0002,
            "epochs": 3,
            "gradient_accumulation": 4,
        },
        seed=20260911,
        code_repository="khfy7wpr5p-maker/st-music-agent-lab-",
        code_commit_sha="f" * 40,
    )
    assert changed.input_fingerprint != first.input_fingerprint
    assert changed.trainer_config_hash != first.trainer_config_hash


def test_only_verified_fine_tuning_candidate_dataset_is_accepted() -> None:
    builder = TrainingRunContractBuilder()
    with pytest.raises(TrainingRunContractError, match="fine-tuning-candidate"):
        builder.create_spec(
            _dataset(purpose=DatasetPurpose.OFFLINE_EVALUATION),
            run_id="train:restore:v1",
            base_model_id="open-model/base",
            base_model_revision="v1",
            base_model_sha256="e" * 64,
            trainer_name="trainer",
            trainer_version="1",
            trainer_config={"epochs": 1},
            seed=1,
            code_repository="owner/repo",
            code_commit_sha="f" * 40,
        )

    forged = replace(_dataset(), manifest_hash="0" * 64)
    with pytest.raises(TrainingRunContractError, match="does not verify"):
        builder.create_spec(
            forged,
            run_id="train:restore:v1",
            base_model_id="open-model/base",
            base_model_revision="v1",
            base_model_sha256="e" * 64,
            trainer_name="trainer",
            trainer_version="1",
            trainer_config={"epochs": 1},
            seed=1,
            code_repository="owner/repo",
            code_commit_sha="f" * 40,
        )


def test_dataset_cannot_smuggle_training_or_promotion_authority() -> None:
    builder = TrainingRunContractBuilder()
    elevated = replace(_dataset(), training_authorized=True)

    with pytest.raises(TrainingRunContractError, match="authority flags"):
        builder.create_spec(
            elevated,
            run_id="train:restore:v1",
            base_model_id="open-model/base",
            base_model_revision="v1",
            base_model_sha256="e" * 64,
            trainer_name="trainer",
            trainer_version="1",
            trainer_config={"epochs": 1},
            seed=1,
            code_repository="owner/repo",
            code_commit_sha="f" * 40,
        )


def test_completion_binds_checkpoint_to_exact_input_fingerprint() -> None:
    builder = TrainingRunContractBuilder()
    spec = _spec()
    completion = builder.bind_completion(
        spec,
        authorization_ref="host-approval:training:001",
        checkpoint_sha256="1" * 64,
        evidence_refs=("trainer-log:run-001", "artifact:checkpoint-001"),
    )

    assert completion.run_id == spec.run_id
    assert completion.input_fingerprint == spec.input_fingerprint
    assert completion.outcome is TrainingRunOutcome.COMPLETED
    assert completion.checkpoint_sha256 == "1" * 64
    assert completion.evaluation_required is True
    assert completion.promotion_authorized is False
    assert completion.auto_promote is False
    assert completion.completion_fingerprint


def test_completion_rejects_tampered_spec_and_invalid_checkpoint() -> None:
    builder = TrainingRunContractBuilder()
    spec = _spec()
    tampered_config = dict(spec.trainer_config)
    tampered_config["epochs"] = 99
    tampered = replace(spec, trainer_config=tampered_config)

    with pytest.raises(TrainingRunContractError, match="configuration hash"):
        builder.bind_completion(
            tampered,
            authorization_ref="host-approval:1",
            checkpoint_sha256="1" * 64,
            evidence_refs=("trainer-log:1",),
        )

    with pytest.raises(ValueError, match="checkpoint_sha256"):
        builder.bind_completion(
            spec,
            authorization_ref="host-approval:1",
            checkpoint_sha256="short",
            evidence_refs=("trainer-log:1",),
        )


def test_failed_or_abstained_run_has_no_checkpoint_and_still_requires_evidence() -> None:
    builder = TrainingRunContractBuilder()
    spec = _spec()

    failed = builder.bind_noncompletion(
        spec,
        outcome=TrainingRunOutcome.FAILED,
        authorization_ref="host-approval:training:002",
        evidence_refs=("trainer-log:failed",),
    )
    assert failed.checkpoint_sha256 is None
    assert failed.outcome is TrainingRunOutcome.FAILED
    assert failed.evaluation_required is True
    assert failed.promotion_authorized is False

    with pytest.raises(ValueError, match="bind_completion"):
        builder.bind_noncompletion(
            spec,
            outcome=TrainingRunOutcome.COMPLETED,
            authorization_ref="host-approval:training:003",
            evidence_refs=("trainer-log:unexpected",),
        )

    with pytest.raises(ValueError, match="evidence"):
        builder.bind_noncompletion(
            spec,
            outcome=TrainingRunOutcome.ABSTAINED,
            authorization_ref="host-approval:training:004",
            evidence_refs=(),
        )


def test_invalid_seed_model_hash_and_code_commit_fail_closed() -> None:
    builder = TrainingRunContractBuilder()
    common = {
        "dataset": _dataset(),
        "run_id": "train:restore:v1",
        "base_model_id": "open-model/base",
        "base_model_revision": "v1",
        "base_model_sha256": "e" * 64,
        "trainer_name": "trainer",
        "trainer_version": "1",
        "trainer_config": {"epochs": 1},
        "seed": 1,
        "code_repository": "owner/repo",
        "code_commit_sha": "f" * 40,
    }

    with pytest.raises(ValueError, match="base_model_sha256"):
        builder.create_spec(**{**common, "base_model_sha256": "bad"})
    with pytest.raises(ValueError, match="code_commit_sha"):
        builder.create_spec(**{**common, "code_commit_sha": "deadbeef"})
    with pytest.raises(ValueError, match="seed"):
        builder.create_spec(**{**common, "seed": -1})
