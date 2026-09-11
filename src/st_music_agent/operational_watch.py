from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass, replace
from enum import IntEnum
from pathlib import Path
from typing import Any

from .baseline_registry import BaselineRecord, BaselineRecordKind
from .drift_watch import (
    DriftObservationWindow,
    DriftWatchGate,
    DriftWatchReport,
    RollbackReviewRequest,
    RollbackReviewRequestBuilder,
)
from .journal import JournalEvent, RunJournal
from .rollback_recovery import (
    PostRollbackRecoveryGate,
    PostRollbackRecoveryReport,
    PostRollbackRecoveryRound,
    RollbackExecutionReceipt,
    RollbackExecutionReceiptBuilder,
)

OPERATIONAL_WATCH_STATE_SCHEMA_VERSION = "1.1.0"
_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_MODEL_ID = re.compile(r"^model:[0-9a-f]{64}$")
_WATCH_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}$")


class OperationalWatchStateError(RuntimeError):
    pass


class OperationalWatchStage(IntEnum):
    BASELINE_BOUND = 10
    DRIFT_REVIEWED = 20
    ROLLBACK_REVIEW_REQUESTED = 30
    ROLLBACK_EXECUTION_RECORDED = 40
    POST_ROLLBACK_RECOVERY_REVIEWED = 50
    ROLLBACK_BASELINE_REGISTERED = 60


_NEXT_STAGE = {
    None: OperationalWatchStage.BASELINE_BOUND,
    OperationalWatchStage.BASELINE_BOUND: OperationalWatchStage.DRIFT_REVIEWED,
    OperationalWatchStage.DRIFT_REVIEWED: OperationalWatchStage.ROLLBACK_REVIEW_REQUESTED,
    OperationalWatchStage.ROLLBACK_REVIEW_REQUESTED: (
        OperationalWatchStage.ROLLBACK_EXECUTION_RECORDED
    ),
    OperationalWatchStage.ROLLBACK_EXECUTION_RECORDED: (
        OperationalWatchStage.POST_ROLLBACK_RECOVERY_REVIEWED
    ),
    OperationalWatchStage.POST_ROLLBACK_RECOVERY_REVIEWED: (
        OperationalWatchStage.ROLLBACK_BASELINE_REGISTERED
    ),
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
class OperationalWatchState:
    watch_id: str
    stage: OperationalWatchStage
    environment: str
    baseline_record_fingerprint: str
    model_id: str
    checkpoint_sha256: str
    drift_report_fingerprint: str | None = None
    rollback_review_request_fingerprint: str | None = None
    rollback_execution_receipt_fingerprint: str | None = None
    post_rollback_recovery_report_fingerprint: str | None = None
    rollback_baseline_record_fingerprint: str | None = None
    state_fingerprint: str = ""

    def as_dict(self) -> dict[str, Any]:
        return {
            "schema_version": OPERATIONAL_WATCH_STATE_SCHEMA_VERSION,
            "watch_id": self.watch_id,
            "stage": self.stage.name.lower(),
            "environment": self.environment,
            "baseline_record_fingerprint": self.baseline_record_fingerprint,
            "model_id": self.model_id,
            "checkpoint_sha256": self.checkpoint_sha256,
            "drift_report_fingerprint": self.drift_report_fingerprint,
            "rollback_review_request_fingerprint": self.rollback_review_request_fingerprint,
            "rollback_execution_receipt_fingerprint": (
                self.rollback_execution_receipt_fingerprint
            ),
            "post_rollback_recovery_report_fingerprint": (
                self.post_rollback_recovery_report_fingerprint
            ),
            "rollback_baseline_record_fingerprint": (
                self.rollback_baseline_record_fingerprint
            ),
            "state_fingerprint": self.state_fingerprint,
        }


class OperationalWatchStateStore:
    """Hash-chained operational evidence pointers for one registered baseline watch cycle."""

    _EVENT_TYPE = "operational_watch_state"

    def __init__(self, path: Path, watch_id: str) -> None:
        if not _WATCH_ID.fullmatch(watch_id):
            raise ValueError("watch_id has an invalid format")
        self.watch_id = watch_id
        self.journal = RunJournal(path, f"st-operational-watch:{watch_id}")
        self._latest = self._load_latest()

    def bind_baseline(self, baseline: BaselineRecord) -> OperationalWatchState:
        if self._latest is not None:
            raise OperationalWatchStateError("operational watch has already started")
        DriftWatchGate.verify_baseline_record(baseline)
        state = OperationalWatchState(
            watch_id=self.watch_id,
            stage=OperationalWatchStage.BASELINE_BOUND,
            environment=baseline.environment,
            baseline_record_fingerprint=baseline.record_fingerprint,
            model_id=baseline.model_id,
            checkpoint_sha256=baseline.checkpoint_sha256,
        )
        return self._persist(self._with_fingerprint(state))

    def record_drift_review(
        self,
        baseline: BaselineRecord,
        windows: tuple[DriftObservationWindow, ...],
        report: DriftWatchReport,
    ) -> OperationalWatchState:
        self._require_next(OperationalWatchStage.DRIFT_REVIEWED)
        self._require_same_baseline(baseline)
        DriftWatchGate().verify(baseline, windows, report)
        return self._advance(
            OperationalWatchStage.DRIFT_REVIEWED,
            drift_report_fingerprint=report.report_fingerprint,
        )

    def record_rollback_review_request(
        self,
        baseline: BaselineRecord,
        windows: tuple[DriftObservationWindow, ...],
        report: DriftWatchReport,
        request: RollbackReviewRequest,
    ) -> OperationalWatchState:
        self._require_next(OperationalWatchStage.ROLLBACK_REVIEW_REQUESTED)
        self._require_same_baseline(baseline)
        if self._latest is None or self._latest.drift_report_fingerprint != report.report_fingerprint:
            raise OperationalWatchStateError("rollback request does not match recorded drift report")
        RollbackReviewRequestBuilder().verify_with_evidence(
            baseline,
            windows,
            report,
            request,
        )
        return self._advance(
            OperationalWatchStage.ROLLBACK_REVIEW_REQUESTED,
            rollback_review_request_fingerprint=request.request_fingerprint,
        )

    def record_rollback_execution(
        self,
        baseline: BaselineRecord,
        windows: tuple[DriftObservationWindow, ...],
        report: DriftWatchReport,
        request: RollbackReviewRequest,
        receipt: RollbackExecutionReceipt,
    ) -> OperationalWatchState:
        self._require_next(OperationalWatchStage.ROLLBACK_EXECUTION_RECORDED)
        self._require_same_baseline(baseline)
        if (
            self._latest is None
            or self._latest.rollback_review_request_fingerprint != request.request_fingerprint
        ):
            raise OperationalWatchStateError(
                "rollback receipt does not match recorded rollback request"
            )
        RollbackExecutionReceiptBuilder().verify_with_evidence(
            baseline,
            windows,
            report,
            request,
            receipt,
        )
        return self._advance(
            OperationalWatchStage.ROLLBACK_EXECUTION_RECORDED,
            rollback_execution_receipt_fingerprint=receipt.receipt_fingerprint,
        )

    def record_post_rollback_recovery(
        self,
        receipt: RollbackExecutionReceipt,
        rounds: tuple[PostRollbackRecoveryRound, ...],
        report: PostRollbackRecoveryReport,
    ) -> OperationalWatchState:
        self._require_next(OperationalWatchStage.POST_ROLLBACK_RECOVERY_REVIEWED)
        if (
            self._latest is None
            or self._latest.rollback_execution_receipt_fingerprint != receipt.receipt_fingerprint
        ):
            raise OperationalWatchStateError(
                "recovery report does not match recorded rollback receipt"
            )
        PostRollbackRecoveryGate().verify(receipt, rounds, report)
        return self._advance(
            OperationalWatchStage.POST_ROLLBACK_RECOVERY_REVIEWED,
            post_rollback_recovery_report_fingerprint=report.report_fingerprint,
        )

    def record_rollback_baseline_registration(
        self,
        record: BaselineRecord,
    ) -> OperationalWatchState:
        self._require_next(OperationalWatchStage.ROLLBACK_BASELINE_REGISTERED)
        if record.record_kind is not BaselineRecordKind.ROLLBACK:
            raise OperationalWatchStateError("operational watch requires a rollback registry record")
        if self._latest is None:
            raise OperationalWatchStateError("operational watch has not started")
        if record.environment != self._latest.environment:
            raise OperationalWatchStateError("rollback registry environment changed")
        if record.previous_model_id != self._latest.model_id:
            raise OperationalWatchStateError("rollback registry source model changed")
        if record.previous_checkpoint_sha256 != self._latest.checkpoint_sha256:
            raise OperationalWatchStateError("rollback registry source checkpoint changed")
        if (
            record.rollback_execution_receipt_fingerprint
            != self._latest.rollback_execution_receipt_fingerprint
        ):
            raise OperationalWatchStateError("rollback registry receipt evidence changed")
        if (
            record.recovery_report_fingerprint
            != self._latest.post_rollback_recovery_report_fingerprint
        ):
            raise OperationalWatchStateError("rollback registry recovery evidence changed")
        return self._advance(
            OperationalWatchStage.ROLLBACK_BASELINE_REGISTERED,
            rollback_baseline_record_fingerprint=record.record_fingerprint,
        )

    def latest(self) -> OperationalWatchState | None:
        return self._latest

    def _require_same_baseline(self, baseline: BaselineRecord) -> None:
        DriftWatchGate.verify_baseline_record(baseline)
        if self._latest is None:
            raise OperationalWatchStateError("operational watch has not started")
        if baseline.environment != self._latest.environment:
            raise OperationalWatchStateError("operational watch environment changed")
        if baseline.record_fingerprint != self._latest.baseline_record_fingerprint:
            raise OperationalWatchStateError("operational watch baseline record changed")
        if baseline.model_id != self._latest.model_id:
            raise OperationalWatchStateError("operational watch model changed")
        if baseline.checkpoint_sha256 != self._latest.checkpoint_sha256:
            raise OperationalWatchStateError("operational watch checkpoint changed")

    def _advance(self, stage: OperationalWatchStage, **updates: Any) -> OperationalWatchState:
        if self._latest is None:
            raise OperationalWatchStateError("operational watch has not started")
        updated = replace(self._latest, stage=stage, state_fingerprint="", **updates)
        return self._persist(self._with_fingerprint(updated))

    def _require_next(self, stage: OperationalWatchStage) -> None:
        current = self._latest.stage if self._latest is not None else None
        expected = _NEXT_STAGE.get(current)
        if expected is not stage:
            current_name = current.name.lower() if current is not None else "not_started"
            expected_name = expected.name.lower() if expected is not None else "complete"
            raise OperationalWatchStateError(
                f"invalid operational watch transition from {current_name}; expected {expected_name}"
            )

    def _persist(self, state: OperationalWatchState) -> OperationalWatchState:
        self._validate_state(state)
        self.journal.append(self._EVENT_TYPE, state.as_dict())
        self._latest = state
        return state

    def _load_latest(self) -> OperationalWatchState | None:
        latest: OperationalWatchState | None = None
        immutable_fields = (
            "environment",
            "baseline_record_fingerprint",
            "model_id",
            "checkpoint_sha256",
            "drift_report_fingerprint",
            "rollback_review_request_fingerprint",
            "rollback_execution_receipt_fingerprint",
            "post_rollback_recovery_report_fingerprint",
            "rollback_baseline_record_fingerprint",
        )
        for event in self.journal.read_events():
            if event.event_type != self._EVENT_TYPE:
                raise OperationalWatchStateError("operational watch journal has unsupported event")
            state = self._from_event(event)
            if latest is not None:
                if state.stage < latest.stage:
                    raise OperationalWatchStateError("operational watch stage regressed")
                for field in immutable_fields:
                    previous = getattr(latest, field)
                    current = getattr(state, field)
                    if previous is not None and current != previous:
                        raise OperationalWatchStateError(
                            f"operational watch evidence changed: {field}"
                        )
            latest = state
        return latest

    def _from_event(self, event: JournalEvent) -> OperationalWatchState:
        payload = event.payload
        if not isinstance(payload, dict):
            raise OperationalWatchStateError("operational watch payload is not an object")
        if payload.get("schema_version") != OPERATIONAL_WATCH_STATE_SCHEMA_VERSION:
            raise OperationalWatchStateError("operational watch state schema is unsupported")
        try:
            state = OperationalWatchState(
                watch_id=str(payload["watch_id"]),
                stage=OperationalWatchStage[str(payload["stage"]).upper()],
                environment=str(payload["environment"]),
                baseline_record_fingerprint=str(payload["baseline_record_fingerprint"]),
                model_id=str(payload["model_id"]),
                checkpoint_sha256=str(payload["checkpoint_sha256"]),
                drift_report_fingerprint=self._optional_text(
                    payload.get("drift_report_fingerprint")
                ),
                rollback_review_request_fingerprint=self._optional_text(
                    payload.get("rollback_review_request_fingerprint")
                ),
                rollback_execution_receipt_fingerprint=self._optional_text(
                    payload.get("rollback_execution_receipt_fingerprint")
                ),
                post_rollback_recovery_report_fingerprint=self._optional_text(
                    payload.get("post_rollback_recovery_report_fingerprint")
                ),
                rollback_baseline_record_fingerprint=self._optional_text(
                    payload.get("rollback_baseline_record_fingerprint")
                ),
                state_fingerprint=str(payload["state_fingerprint"]),
            )
        except (KeyError, ValueError) as exc:
            raise OperationalWatchStateError("operational watch payload is invalid") from exc
        self._validate_state(state)
        return state

    def _with_fingerprint(self, state: OperationalWatchState) -> OperationalWatchState:
        base = state.as_dict()
        base["state_fingerprint"] = ""
        return replace(state, state_fingerprint=_canonical_hash(base))

    def _validate_state(self, state: OperationalWatchState) -> None:
        if state.watch_id != self.watch_id:
            raise OperationalWatchStateError("watch id does not match store")
        if not state.environment.strip():
            raise OperationalWatchStateError("operational watch environment is empty")
        if not _SHA256.fullmatch(state.baseline_record_fingerprint):
            raise OperationalWatchStateError("baseline record fingerprint is invalid")
        if not _MODEL_ID.fullmatch(state.model_id):
            raise OperationalWatchStateError("operational watch model id is invalid")
        if not _SHA256.fullmatch(state.checkpoint_sha256):
            raise OperationalWatchStateError("operational watch checkpoint is invalid")
        fingerprint_fields = (
            state.drift_report_fingerprint,
            state.rollback_review_request_fingerprint,
            state.rollback_execution_receipt_fingerprint,
            state.post_rollback_recovery_report_fingerprint,
            state.rollback_baseline_record_fingerprint,
        )
        if any(value is not None and not _SHA256.fullmatch(value) for value in fingerprint_fields):
            raise OperationalWatchStateError("operational watch evidence fingerprint is invalid")

        required_by_stage = {
            OperationalWatchStage.DRIFT_REVIEWED: "drift_report_fingerprint",
            OperationalWatchStage.ROLLBACK_REVIEW_REQUESTED: (
                "rollback_review_request_fingerprint"
            ),
            OperationalWatchStage.ROLLBACK_EXECUTION_RECORDED: (
                "rollback_execution_receipt_fingerprint"
            ),
            OperationalWatchStage.POST_ROLLBACK_RECOVERY_REVIEWED: (
                "post_rollback_recovery_report_fingerprint"
            ),
            OperationalWatchStage.ROLLBACK_BASELINE_REGISTERED: (
                "rollback_baseline_record_fingerprint"
            ),
        }
        for checkpoint_stage, field in required_by_stage.items():
            if state.stage >= checkpoint_stage and getattr(state, field) is None:
                raise OperationalWatchStateError(
                    f"operational watch stage requires evidence field: {field}"
                )

        base = state.as_dict()
        fingerprint = base.pop("state_fingerprint")
        base["state_fingerprint"] = ""
        if not _SHA256.fullmatch(fingerprint) or _canonical_hash(base) != fingerprint:
            raise OperationalWatchStateError("operational watch state fingerprint does not verify")

    @staticmethod
    def _optional_text(value: Any) -> str | None:
        return None if value is None else str(value)
