from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass, replace
from enum import IntEnum
from pathlib import Path
from typing import Any

from .journal import JournalEvent, RunJournal

ORCHESTRATION_STATE_SCHEMA_VERSION = "1.0.0"
_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_MODEL_ID = re.compile(r"^model:[0-9a-f]{64}$")
_ORCHESTRATION_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}$")


class OrchestrationStateError(RuntimeError):
    pass


class OrchestrationStage(IntEnum):
    PLAN_VERIFIED = 10
    EXECUTION_VERIFIED = 20
    DATASET_CURATED = 30
    TRAINING_COMPLETED = 40
    MODEL_REGISTERED = 50
    PROMOTION_REVIEWED = 60
    ACTIVATION_REQUESTED = 70


_NEXT_STAGE = {
    None: OrchestrationStage.PLAN_VERIFIED,
    OrchestrationStage.PLAN_VERIFIED: OrchestrationStage.EXECUTION_VERIFIED,
    OrchestrationStage.EXECUTION_VERIFIED: OrchestrationStage.DATASET_CURATED,
    OrchestrationStage.DATASET_CURATED: OrchestrationStage.TRAINING_COMPLETED,
    OrchestrationStage.TRAINING_COMPLETED: OrchestrationStage.MODEL_REGISTERED,
    OrchestrationStage.MODEL_REGISTERED: OrchestrationStage.PROMOTION_REVIEWED,
    OrchestrationStage.PROMOTION_REVIEWED: OrchestrationStage.ACTIVATION_REQUESTED,
}


def _canonical_hash(value: Any) -> str:
    encoded = json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


@dataclass(frozen=True, slots=True)
class OrchestrationState:
    orchestration_id: str
    stage: OrchestrationStage
    plan_id: str
    plan_verification_ref: str
    execution_record_id: str | None = None
    experience_record_id: str | None = None
    evaluation_report_hash: str | None = None
    dataset_manifest_hash: str | None = None
    training_input_fingerprint: str | None = None
    training_completion_fingerprint: str | None = None
    training_authorization_ref: str | None = None
    model_candidate_id: str | None = None
    promotion_review_fingerprint: str | None = None
    activation_request_fingerprint: str | None = None
    state_fingerprint: str = ""

    def as_dict(self) -> dict[str, Any]:
        return {
            "schema_version": ORCHESTRATION_STATE_SCHEMA_VERSION,
            "orchestration_id": self.orchestration_id,
            "stage": self.stage.name.lower(),
            "plan_id": self.plan_id,
            "plan_verification_ref": self.plan_verification_ref,
            "execution_record_id": self.execution_record_id,
            "experience_record_id": self.experience_record_id,
            "evaluation_report_hash": self.evaluation_report_hash,
            "dataset_manifest_hash": self.dataset_manifest_hash,
            "training_input_fingerprint": self.training_input_fingerprint,
            "training_completion_fingerprint": self.training_completion_fingerprint,
            "training_authorization_ref": self.training_authorization_ref,
            "model_candidate_id": self.model_candidate_id,
            "promotion_review_fingerprint": self.promotion_review_fingerprint,
            "activation_request_fingerprint": self.activation_request_fingerprint,
            "state_fingerprint": self.state_fingerprint,
        }


class OrchestrationStateStore:
    """Host-write-only resumable evidence pointers for the guarded lifecycle.

    The store persists structured identities/fingerprints only. It intentionally has no field for
    prompts, provider messages or hidden reasoning.
    """

    _EVENT_TYPE = "orchestration_state"

    def __init__(self, path: Path, orchestration_id: str) -> None:
        if not _ORCHESTRATION_ID.fullmatch(orchestration_id):
            raise ValueError("orchestration_id has an invalid format")
        self.orchestration_id = orchestration_id
        self.journal = RunJournal(path, f"st-orchestration:{orchestration_id}")
        self._latest = self._load_latest()

    def start_plan(self, *, plan_id: str, plan_verification_ref: str) -> OrchestrationState:
        if self._latest is not None:
            raise OrchestrationStateError("orchestration has already started")
        self._require_sha(plan_id, "plan_id")
        self._require_text(plan_verification_ref, "plan_verification_ref")
        state = OrchestrationState(
            orchestration_id=self.orchestration_id,
            stage=OrchestrationStage.PLAN_VERIFIED,
            plan_id=plan_id,
            plan_verification_ref=plan_verification_ref,
        )
        return self._persist(self._with_fingerprint(state))

    def record_execution(self, *, execution_record_id: str) -> OrchestrationState:
        self._require_next(OrchestrationStage.EXECUTION_VERIFIED)
        self._require_sha(execution_record_id, "execution_record_id")
        return self._advance(
            OrchestrationStage.EXECUTION_VERIFIED,
            execution_record_id=execution_record_id,
        )

    def attach_learning_evidence(
        self,
        *,
        experience_record_id: str | None = None,
        evaluation_report_hash: str | None = None,
    ) -> OrchestrationState:
        if self._latest is None or self._latest.stage < OrchestrationStage.EXECUTION_VERIFIED:
            raise OrchestrationStateError("learning evidence requires verified execution")
        if experience_record_id is None and evaluation_report_hash is None:
            raise ValueError("at least one learning evidence reference is required")
        if experience_record_id is not None:
            self._require_sha(experience_record_id, "experience_record_id")
        if evaluation_report_hash is not None:
            self._require_sha(evaluation_report_hash, "evaluation_report_hash")
        state = self._latest
        if state.experience_record_id not in (None, experience_record_id):
            raise OrchestrationStateError("experience record cannot be replaced")
        if state.evaluation_report_hash not in (None, evaluation_report_hash):
            raise OrchestrationStateError("evaluation report cannot be replaced")
        updated = replace(
            state,
            experience_record_id=experience_record_id or state.experience_record_id,
            evaluation_report_hash=evaluation_report_hash or state.evaluation_report_hash,
            state_fingerprint="",
        )
        return self._persist(self._with_fingerprint(updated))

    def record_dataset(self, *, dataset_manifest_hash: str) -> OrchestrationState:
        self._require_next(OrchestrationStage.DATASET_CURATED)
        self._require_sha(dataset_manifest_hash, "dataset_manifest_hash")
        return self._advance(
            OrchestrationStage.DATASET_CURATED,
            dataset_manifest_hash=dataset_manifest_hash,
        )

    def record_training(
        self,
        *,
        input_fingerprint: str,
        completion_fingerprint: str,
        authorization_ref: str,
    ) -> OrchestrationState:
        self._require_next(OrchestrationStage.TRAINING_COMPLETED)
        self._require_sha(input_fingerprint, "training_input_fingerprint")
        self._require_sha(completion_fingerprint, "training_completion_fingerprint")
        self._require_text(authorization_ref, "training_authorization_ref")
        return self._advance(
            OrchestrationStage.TRAINING_COMPLETED,
            training_input_fingerprint=input_fingerprint,
            training_completion_fingerprint=completion_fingerprint,
            training_authorization_ref=authorization_ref,
        )

    def record_model_candidate(self, *, candidate_id: str) -> OrchestrationState:
        self._require_next(OrchestrationStage.MODEL_REGISTERED)
        if not _MODEL_ID.fullmatch(candidate_id):
            raise ValueError("candidate_id must be a model candidate id")
        return self._advance(OrchestrationStage.MODEL_REGISTERED, model_candidate_id=candidate_id)

    def record_promotion_review(self, *, review_fingerprint: str) -> OrchestrationState:
        self._require_next(OrchestrationStage.PROMOTION_REVIEWED)
        self._require_sha(review_fingerprint, "promotion_review_fingerprint")
        return self._advance(
            OrchestrationStage.PROMOTION_REVIEWED,
            promotion_review_fingerprint=review_fingerprint,
        )

    def record_activation_request(self, *, request_fingerprint: str) -> OrchestrationState:
        self._require_next(OrchestrationStage.ACTIVATION_REQUESTED)
        self._require_sha(request_fingerprint, "activation_request_fingerprint")
        return self._advance(
            OrchestrationStage.ACTIVATION_REQUESTED,
            activation_request_fingerprint=request_fingerprint,
        )

    def latest(self) -> OrchestrationState | None:
        return self._latest

    def _advance(self, stage: OrchestrationStage, **updates: Any) -> OrchestrationState:
        state = self._latest
        if state is None:
            raise OrchestrationStateError("orchestration has not started")
        updated = replace(state, stage=stage, state_fingerprint="", **updates)
        return self._persist(self._with_fingerprint(updated))

    def _require_next(self, stage: OrchestrationStage) -> None:
        current = self._latest.stage if self._latest is not None else None
        expected = _NEXT_STAGE.get(current)
        if expected is not stage:
            current_name = current.name.lower() if current is not None else "not_started"
            expected_name = expected.name.lower() if expected is not None else "complete"
            raise OrchestrationStateError(
                f"invalid stage transition from {current_name}; expected {expected_name}"
            )

    def _persist(self, state: OrchestrationState) -> OrchestrationState:
        self._validate_state(state)
        self.journal.append(self._EVENT_TYPE, state.as_dict())
        self._latest = state
        return state

    def _load_latest(self) -> OrchestrationState | None:
        latest: OrchestrationState | None = None
        for event in self.journal.read_events():
            if event.event_type != self._EVENT_TYPE:
                raise OrchestrationStateError("orchestration journal contains unsupported event")
            state = self._from_event(event)
            if latest is not None:
                if state.stage < latest.stage:
                    raise OrchestrationStateError("orchestration stage regressed in journal")
                for field in (
                    "plan_id",
                    "plan_verification_ref",
                    "execution_record_id",
                    "experience_record_id",
                    "evaluation_report_hash",
                    "dataset_manifest_hash",
                    "training_input_fingerprint",
                    "training_completion_fingerprint",
                    "training_authorization_ref",
                    "model_candidate_id",
                    "promotion_review_fingerprint",
                    "activation_request_fingerprint",
                ):
                    previous = getattr(latest, field)
                    current = getattr(state, field)
                    if previous is not None and current != previous:
                        raise OrchestrationStateError(f"orchestration evidence changed: {field}")
            latest = state
        return latest

    def _from_event(self, event: JournalEvent) -> OrchestrationState:
        payload = event.payload
        if not isinstance(payload, dict):
            raise OrchestrationStateError("orchestration state payload is not an object")
        if payload.get("schema_version") != ORCHESTRATION_STATE_SCHEMA_VERSION:
            raise OrchestrationStateError("orchestration state schema is unsupported")
        try:
            stage = OrchestrationStage[str(payload["stage"]).upper()]
            state = OrchestrationState(
                orchestration_id=str(payload["orchestration_id"]),
                stage=stage,
                plan_id=str(payload["plan_id"]),
                plan_verification_ref=str(payload["plan_verification_ref"]),
                execution_record_id=self._optional_text(payload.get("execution_record_id")),
                experience_record_id=self._optional_text(payload.get("experience_record_id")),
                evaluation_report_hash=self._optional_text(payload.get("evaluation_report_hash")),
                dataset_manifest_hash=self._optional_text(payload.get("dataset_manifest_hash")),
                training_input_fingerprint=self._optional_text(
                    payload.get("training_input_fingerprint")
                ),
                training_completion_fingerprint=self._optional_text(
                    payload.get("training_completion_fingerprint")
                ),
                training_authorization_ref=self._optional_text(
                    payload.get("training_authorization_ref")
                ),
                model_candidate_id=self._optional_text(payload.get("model_candidate_id")),
                promotion_review_fingerprint=self._optional_text(
                    payload.get("promotion_review_fingerprint")
                ),
                activation_request_fingerprint=self._optional_text(
                    payload.get("activation_request_fingerprint")
                ),
                state_fingerprint=str(payload["state_fingerprint"]),
            )
        except (KeyError, ValueError) as exc:
            raise OrchestrationStateError("orchestration state payload is invalid") from exc
        self._validate_state(state)
        return state

    def _with_fingerprint(self, state: OrchestrationState) -> OrchestrationState:
        base = state.as_dict()
        base["state_fingerprint"] = ""
        return replace(state, state_fingerprint=_canonical_hash(base))

    def _validate_state(self, state: OrchestrationState) -> None:
        if state.orchestration_id != self.orchestration_id:
            raise OrchestrationStateError("orchestration id does not match store")
        self._require_sha(state.plan_id, "plan_id")
        self._require_text(state.plan_verification_ref, "plan_verification_ref")
        for label, value in (
            ("execution_record_id", state.execution_record_id),
            ("experience_record_id", state.experience_record_id),
            ("evaluation_report_hash", state.evaluation_report_hash),
            ("dataset_manifest_hash", state.dataset_manifest_hash),
            ("training_input_fingerprint", state.training_input_fingerprint),
            ("training_completion_fingerprint", state.training_completion_fingerprint),
            ("promotion_review_fingerprint", state.promotion_review_fingerprint),
            ("activation_request_fingerprint", state.activation_request_fingerprint),
        ):
            if value is not None:
                self._require_sha(value, label)
        if state.model_candidate_id is not None and not _MODEL_ID.fullmatch(state.model_candidate_id):
            raise OrchestrationStateError("model_candidate_id is invalid")
        if state.training_authorization_ref is not None:
            self._require_text(state.training_authorization_ref, "training_authorization_ref")

        required_by_stage = {
            OrchestrationStage.PLAN_VERIFIED: ("plan_id",),
            OrchestrationStage.EXECUTION_VERIFIED: ("execution_record_id",),
            OrchestrationStage.DATASET_CURATED: ("dataset_manifest_hash",),
            OrchestrationStage.TRAINING_COMPLETED: (
                "training_input_fingerprint",
                "training_completion_fingerprint",
                "training_authorization_ref",
            ),
            OrchestrationStage.MODEL_REGISTERED: ("model_candidate_id",),
            OrchestrationStage.PROMOTION_REVIEWED: ("promotion_review_fingerprint",),
            OrchestrationStage.ACTIVATION_REQUESTED: ("activation_request_fingerprint",),
        }
        for checkpoint_stage, fields in required_by_stage.items():
            if state.stage >= checkpoint_stage:
                for field in fields:
                    if getattr(state, field) in (None, ""):
                        raise OrchestrationStateError(
                            f"orchestration stage requires evidence field: {field}"
                        )

        base = state.as_dict()
        expected = base.pop("state_fingerprint")
        base["state_fingerprint"] = ""
        if not _SHA256.fullmatch(expected) or _canonical_hash(base) != expected:
            raise OrchestrationStateError("orchestration state fingerprint does not verify")

    @staticmethod
    def _require_sha(value: str, label: str) -> None:
        if not isinstance(value, str) or not _SHA256.fullmatch(value):
            raise ValueError(f"{label} must be a lowercase SHA-256 digest")

    @staticmethod
    def _require_text(value: str, label: str) -> None:
        if not isinstance(value, str) or not value.strip():
            raise ValueError(f"{label} must be non-empty text")

    @staticmethod
    def _optional_text(value: Any) -> str | None:
        return None if value is None else str(value)
