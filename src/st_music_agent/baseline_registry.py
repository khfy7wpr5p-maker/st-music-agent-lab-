from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Any

from .canonical_baseline import (
    CanonicalizationOutcome,
    CanonicalizationReceipt,
    CanonicalizationReceiptBuilder,
)
from .journal import JournalEvent, RunJournal
from .post_canonical_stability import (
    PostCanonicalObservationRound,
    PostCanonicalStabilityDecision,
    PostCanonicalStabilityGate,
    PostCanonicalStabilityReport,
)

BASELINE_REGISTRY_SCHEMA_VERSION = "1.1.0"
_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_MODEL_ID = re.compile(r"^model:[0-9a-f]{64}$")


class BaselineRegistryError(RuntimeError):
    pass


class BaselineRecordKind(str, Enum):
    BOOTSTRAP = "bootstrap"
    CANONICALIZATION = "canonicalization"
    ROLLBACK = "rollback"


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
class BaselineRecord:
    generation: int
    environment: str
    record_kind: BaselineRecordKind
    model_id: str
    checkpoint_sha256: str
    previous_model_id: str | None
    previous_checkpoint_sha256: str | None
    rollback_model_id: str | None
    rollback_checkpoint_sha256: str | None
    canonicalization_receipt_fingerprint: str | None
    stability_report_fingerprint: str | None
    host_registration_ref: str
    evidence_refs: tuple[str, ...]
    record_fingerprint: str
    rollback_execution_receipt_fingerprint: str | None = None
    recovery_report_fingerprint: str | None = None
    auto_switch: bool = False
    auto_rollback: bool = False

    def as_dict(self) -> dict[str, Any]:
        result = {
            "schema_version": BASELINE_REGISTRY_SCHEMA_VERSION,
            "generation": self.generation,
            "environment": self.environment,
            "record_kind": self.record_kind.value,
            "model_id": self.model_id,
            "checkpoint_sha256": self.checkpoint_sha256,
            "previous_model_id": self.previous_model_id,
            "previous_checkpoint_sha256": self.previous_checkpoint_sha256,
            "rollback_model_id": self.rollback_model_id,
            "rollback_checkpoint_sha256": self.rollback_checkpoint_sha256,
            "canonicalization_receipt_fingerprint": (
                self.canonicalization_receipt_fingerprint
            ),
            "stability_report_fingerprint": self.stability_report_fingerprint,
            "host_registration_ref": self.host_registration_ref,
            "evidence_refs": list(self.evidence_refs),
            "record_fingerprint": self.record_fingerprint,
            "auto_switch": self.auto_switch,
            "auto_rollback": self.auto_rollback,
        }
        if (
            self.record_kind is BaselineRecordKind.ROLLBACK
            or self.rollback_execution_receipt_fingerprint is not None
            or self.recovery_report_fingerprint is not None
        ):
            result["rollback_execution_receipt_fingerprint"] = (
                self.rollback_execution_receipt_fingerprint
            )
            result["recovery_report_fingerprint"] = self.recovery_report_fingerprint
        return result


class BaselineRegistry:
    """Append-only host registry for canonical baseline lineage.

    The registry records already-observed state. It never deploys, switches, or rolls back a model.
    """

    _EVENT_TYPE = "baseline_registry_record"

    def __init__(self, path: Path, environment: str) -> None:
        self._require_text(environment, "environment")
        self.environment = environment
        self.journal = RunJournal(path, f"st-baseline-registry:{environment}")
        self._records = self._load_records()

    def bootstrap(
        self,
        *,
        model_id: str,
        checkpoint_sha256: str,
        host_registration_ref: str,
        evidence_refs: tuple[str, ...],
    ) -> BaselineRecord:
        if self._records:
            raise BaselineRegistryError("baseline registry is already initialized")
        self._require_model(model_id, "model_id")
        self._require_sha(checkpoint_sha256, "checkpoint_sha256")
        self._require_text(host_registration_ref, "host_registration_ref")
        self._require_evidence(evidence_refs)
        record = self._build_record(
            generation=1,
            record_kind=BaselineRecordKind.BOOTSTRAP,
            model_id=model_id,
            checkpoint_sha256=checkpoint_sha256,
            previous_model_id=None,
            previous_checkpoint_sha256=None,
            rollback_model_id=None,
            rollback_checkpoint_sha256=None,
            canonicalization_receipt_fingerprint=None,
            stability_report_fingerprint=None,
            rollback_execution_receipt_fingerprint=None,
            recovery_report_fingerprint=None,
            host_registration_ref=host_registration_ref,
            evidence_refs=evidence_refs,
        )
        return self._append(record)

    def register_canonicalization(
        self,
        receipt: CanonicalizationReceipt,
        rounds: tuple[PostCanonicalObservationRound, ...],
        stability_report: PostCanonicalStabilityReport,
        *,
        host_registration_ref: str,
        evidence_refs: tuple[str, ...],
    ) -> BaselineRecord:
        CanonicalizationReceiptBuilder.verify(receipt)
        PostCanonicalStabilityGate().verify(receipt, rounds, stability_report)
        if receipt.outcome is not CanonicalizationOutcome.CANONICALIZED:
            raise BaselineRegistryError("baseline registration requires canonicalized receipt")
        if (
            stability_report.decision
            is not PostCanonicalStabilityDecision.ELIGIBLE_FOR_BASELINE_REGISTRATION
        ):
            raise BaselineRegistryError("post-canonical stability is not eligible for registration")
        if receipt.target_environment != self.environment:
            raise BaselineRegistryError("canonicalization environment does not match registry")
        if not self._records:
            raise BaselineRegistryError("baseline registry must be bootstrapped before transition")
        current = self._records[-1]
        if current.model_id != receipt.previous_canonical_id:
            raise BaselineRegistryError("registered baseline differs from canonicalization predecessor")
        if current.checkpoint_sha256 != receipt.previous_canonical_checkpoint_sha256:
            raise BaselineRegistryError(
                "registered checkpoint differs from canonicalization predecessor"
            )
        if receipt.rollback_candidate_id != current.model_id:
            raise BaselineRegistryError("canonicalization rollback model differs from registry")
        if receipt.rollback_checkpoint_sha256 != current.checkpoint_sha256:
            raise BaselineRegistryError("canonicalization rollback checkpoint differs from registry")
        self._require_text(host_registration_ref, "host_registration_ref")
        self._require_evidence(evidence_refs)

        record = self._build_record(
            generation=current.generation + 1,
            record_kind=BaselineRecordKind.CANONICALIZATION,
            model_id=receipt.candidate_id,
            checkpoint_sha256=receipt.candidate_checkpoint_sha256,
            previous_model_id=current.model_id,
            previous_checkpoint_sha256=current.checkpoint_sha256,
            rollback_model_id=receipt.rollback_candidate_id,
            rollback_checkpoint_sha256=receipt.rollback_checkpoint_sha256,
            canonicalization_receipt_fingerprint=receipt.receipt_fingerprint,
            stability_report_fingerprint=stability_report.report_fingerprint,
            rollback_execution_receipt_fingerprint=None,
            recovery_report_fingerprint=None,
            host_registration_ref=host_registration_ref,
            evidence_refs=evidence_refs,
        )
        return self._append(record)

    def register_rollback(
        self,
        baseline: BaselineRecord,
        windows: tuple[Any, ...],
        drift_report: Any,
        rollback_request: Any,
        rollback_receipt: Any,
        recovery_rounds: tuple[Any, ...],
        recovery_report: Any,
        *,
        host_registration_ref: str,
        evidence_refs: tuple[str, ...],
    ) -> BaselineRecord:
        from .drift_watch import DriftWatchGate
        from .rollback_recovery import (
            PostRollbackRecoveryDecision,
            PostRollbackRecoveryGate,
            RollbackExecutionOutcome,
            RollbackExecutionReceiptBuilder,
        )

        if not self._records:
            raise BaselineRegistryError("baseline registry must be initialized before rollback")
        current = self._records[-1]
        DriftWatchGate.verify_baseline_record(baseline)
        if baseline.record_fingerprint != current.record_fingerprint:
            raise BaselineRegistryError("rollback baseline differs from current registry record")
        if baseline.model_id != current.model_id:
            raise BaselineRegistryError("rollback source model differs from current registry record")
        if baseline.checkpoint_sha256 != current.checkpoint_sha256:
            raise BaselineRegistryError(
                "rollback source checkpoint differs from current registry record"
            )

        RollbackExecutionReceiptBuilder().verify_with_evidence(
            baseline,
            windows,
            drift_report,
            rollback_request,
            rollback_receipt,
        )
        RollbackExecutionReceiptBuilder.verify_record(rollback_receipt)
        PostRollbackRecoveryGate().verify(
            rollback_receipt,
            recovery_rounds,
            recovery_report,
        )
        if rollback_receipt.outcome is not RollbackExecutionOutcome.ROLLED_BACK:
            raise BaselineRegistryError("rollback registration requires successful rollback receipt")
        if (
            recovery_report.decision
            is not PostRollbackRecoveryDecision.ELIGIBLE_FOR_BASELINE_REGISTRATION
        ):
            raise BaselineRegistryError("post-rollback recovery is not eligible for registration")
        if rollback_receipt.environment != self.environment:
            raise BaselineRegistryError("rollback environment does not match registry")
        if current.rollback_model_id != rollback_receipt.to_model_id:
            raise BaselineRegistryError("rollback target model differs from registered predecessor")
        if current.rollback_checkpoint_sha256 != rollback_receipt.to_checkpoint_sha256:
            raise BaselineRegistryError(
                "rollback target checkpoint differs from registered predecessor"
            )
        if current.previous_model_id != rollback_receipt.to_model_id:
            raise BaselineRegistryError("rollback target must equal the exact prior generation")
        if current.previous_checkpoint_sha256 != rollback_receipt.to_checkpoint_sha256:
            raise BaselineRegistryError(
                "rollback checkpoint must equal the exact prior generation checkpoint"
            )
        if not any(
            record.model_id == rollback_receipt.to_model_id
            and record.checkpoint_sha256 == rollback_receipt.to_checkpoint_sha256
            for record in self._records[:-1]
        ):
            raise BaselineRegistryError("rollback target is absent from registry history")
        self._require_text(host_registration_ref, "host_registration_ref")
        self._require_evidence(evidence_refs)

        record = self._build_record(
            generation=current.generation + 1,
            record_kind=BaselineRecordKind.ROLLBACK,
            model_id=rollback_receipt.to_model_id,
            checkpoint_sha256=rollback_receipt.to_checkpoint_sha256,
            previous_model_id=current.model_id,
            previous_checkpoint_sha256=current.checkpoint_sha256,
            rollback_model_id=None,
            rollback_checkpoint_sha256=None,
            canonicalization_receipt_fingerprint=None,
            stability_report_fingerprint=None,
            rollback_execution_receipt_fingerprint=rollback_receipt.receipt_fingerprint,
            recovery_report_fingerprint=recovery_report.report_fingerprint,
            host_registration_ref=host_registration_ref,
            evidence_refs=evidence_refs,
        )
        return self._append(record)

    def current(self) -> BaselineRecord | None:
        return self._records[-1] if self._records else None

    def history(self) -> tuple[BaselineRecord, ...]:
        return tuple(self._records)

    def _build_record(
        self,
        *,
        generation: int,
        record_kind: BaselineRecordKind,
        model_id: str,
        checkpoint_sha256: str,
        previous_model_id: str | None,
        previous_checkpoint_sha256: str | None,
        rollback_model_id: str | None,
        rollback_checkpoint_sha256: str | None,
        canonicalization_receipt_fingerprint: str | None,
        stability_report_fingerprint: str | None,
        rollback_execution_receipt_fingerprint: str | None,
        recovery_report_fingerprint: str | None,
        host_registration_ref: str,
        evidence_refs: tuple[str, ...],
    ) -> BaselineRecord:
        base = {
            "schema_version": BASELINE_REGISTRY_SCHEMA_VERSION,
            "generation": generation,
            "environment": self.environment,
            "record_kind": record_kind.value,
            "model_id": model_id,
            "checkpoint_sha256": checkpoint_sha256,
            "previous_model_id": previous_model_id,
            "previous_checkpoint_sha256": previous_checkpoint_sha256,
            "rollback_model_id": rollback_model_id,
            "rollback_checkpoint_sha256": rollback_checkpoint_sha256,
            "canonicalization_receipt_fingerprint": canonicalization_receipt_fingerprint,
            "stability_report_fingerprint": stability_report_fingerprint,
            "host_registration_ref": host_registration_ref,
            "evidence_refs": list(evidence_refs),
            "auto_switch": False,
            "auto_rollback": False,
        }
        if record_kind is BaselineRecordKind.ROLLBACK:
            base["rollback_execution_receipt_fingerprint"] = (
                rollback_execution_receipt_fingerprint
            )
            base["recovery_report_fingerprint"] = recovery_report_fingerprint
        return BaselineRecord(
            generation=generation,
            environment=self.environment,
            record_kind=record_kind,
            model_id=model_id,
            checkpoint_sha256=checkpoint_sha256,
            previous_model_id=previous_model_id,
            previous_checkpoint_sha256=previous_checkpoint_sha256,
            rollback_model_id=rollback_model_id,
            rollback_checkpoint_sha256=rollback_checkpoint_sha256,
            canonicalization_receipt_fingerprint=canonicalization_receipt_fingerprint,
            stability_report_fingerprint=stability_report_fingerprint,
            host_registration_ref=host_registration_ref,
            evidence_refs=evidence_refs,
            record_fingerprint=_canonical_hash(base),
            rollback_execution_receipt_fingerprint=(
                rollback_execution_receipt_fingerprint
            ),
            recovery_report_fingerprint=recovery_report_fingerprint,
            auto_switch=False,
            auto_rollback=False,
        )

    def _append(self, record: BaselineRecord) -> BaselineRecord:
        self._validate_record(record)
        self.journal.append(self._EVENT_TYPE, record.as_dict())
        self._records.append(record)
        return record

    def _load_records(self) -> list[BaselineRecord]:
        records: list[BaselineRecord] = []
        for event in self.journal.read_events():
            if event.event_type != self._EVENT_TYPE:
                raise BaselineRegistryError("baseline registry contains unsupported event")
            record = self._from_event(event)
            if record.generation != len(records) + 1:
                raise BaselineRegistryError("baseline registry generations are not contiguous")
            if records:
                previous = records[-1]
                if record.previous_model_id != previous.model_id:
                    raise BaselineRegistryError("baseline registry model lineage is broken")
                if record.previous_checkpoint_sha256 != previous.checkpoint_sha256:
                    raise BaselineRegistryError("baseline registry checkpoint lineage is broken")
                if record.record_kind is BaselineRecordKind.CANONICALIZATION:
                    if record.rollback_model_id != previous.model_id:
                        raise BaselineRegistryError("baseline registry rollback model lineage is broken")
                    if record.rollback_checkpoint_sha256 != previous.checkpoint_sha256:
                        raise BaselineRegistryError(
                            "baseline registry rollback checkpoint lineage is broken"
                        )
                elif record.record_kind is BaselineRecordKind.ROLLBACK:
                    if record.model_id != previous.rollback_model_id:
                        raise BaselineRegistryError("rollback generation model target is invalid")
                    if record.checkpoint_sha256 != previous.rollback_checkpoint_sha256:
                        raise BaselineRegistryError("rollback generation checkpoint target is invalid")
                else:
                    raise BaselineRegistryError("baseline registry transition kind is invalid")
            elif record.record_kind is not BaselineRecordKind.BOOTSTRAP:
                raise BaselineRegistryError("first baseline registry record must be bootstrap")
            records.append(record)
        return records

    def _from_event(self, event: JournalEvent) -> BaselineRecord:
        payload = event.payload
        if not isinstance(payload, dict):
            raise BaselineRegistryError("baseline registry payload is not an object")
        if payload.get("schema_version") != BASELINE_REGISTRY_SCHEMA_VERSION:
            raise BaselineRegistryError("baseline registry schema is unsupported")
        try:
            record = BaselineRecord(
                generation=int(payload["generation"]),
                environment=str(payload["environment"]),
                record_kind=BaselineRecordKind(str(payload["record_kind"])),
                model_id=str(payload["model_id"]),
                checkpoint_sha256=str(payload["checkpoint_sha256"]),
                previous_model_id=self._optional_text(payload.get("previous_model_id")),
                previous_checkpoint_sha256=self._optional_text(
                    payload.get("previous_checkpoint_sha256")
                ),
                rollback_model_id=self._optional_text(payload.get("rollback_model_id")),
                rollback_checkpoint_sha256=self._optional_text(
                    payload.get("rollback_checkpoint_sha256")
                ),
                canonicalization_receipt_fingerprint=self._optional_text(
                    payload.get("canonicalization_receipt_fingerprint")
                ),
                stability_report_fingerprint=self._optional_text(
                    payload.get("stability_report_fingerprint")
                ),
                host_registration_ref=str(payload["host_registration_ref"]),
                evidence_refs=tuple(str(item) for item in payload["evidence_refs"]),
                record_fingerprint=str(payload["record_fingerprint"]),
                rollback_execution_receipt_fingerprint=self._optional_text(
                    payload.get("rollback_execution_receipt_fingerprint")
                ),
                recovery_report_fingerprint=self._optional_text(
                    payload.get("recovery_report_fingerprint")
                ),
                auto_switch=bool(payload["auto_switch"]),
                auto_rollback=bool(payload["auto_rollback"]),
            )
        except (KeyError, TypeError, ValueError) as exc:
            raise BaselineRegistryError("baseline registry payload is invalid") from exc
        self._validate_record(record)
        return record

    def _validate_record(self, record: BaselineRecord) -> None:
        if record.generation < 1:
            raise BaselineRegistryError("baseline registry generation is invalid")
        if record.environment != self.environment:
            raise BaselineRegistryError("baseline registry environment is invalid")
        self._require_model(record.model_id, "model_id")
        self._require_sha(record.checkpoint_sha256, "checkpoint_sha256")
        self._require_text(record.host_registration_ref, "host_registration_ref")
        self._require_evidence(record.evidence_refs)
        if record.auto_switch or record.auto_rollback:
            raise BaselineRegistryError("baseline registry cannot authorize automatic actions")

        optional_models = (record.previous_model_id, record.rollback_model_id)
        optional_hashes = (
            record.previous_checkpoint_sha256,
            record.rollback_checkpoint_sha256,
            record.canonicalization_receipt_fingerprint,
            record.stability_report_fingerprint,
            record.rollback_execution_receipt_fingerprint,
            record.recovery_report_fingerprint,
        )
        for value in optional_models:
            if value is not None:
                self._require_model(value, "baseline lineage model id")
        for value in optional_hashes:
            if value is not None:
                self._require_sha(value, "baseline lineage fingerprint")

        if record.record_kind is BaselineRecordKind.BOOTSTRAP:
            if any(value is not None for value in (*optional_models, *optional_hashes)):
                raise BaselineRegistryError("bootstrap record cannot claim prior transition evidence")
        elif record.record_kind is BaselineRecordKind.CANONICALIZATION:
            required = (
                record.previous_model_id,
                record.previous_checkpoint_sha256,
                record.rollback_model_id,
                record.rollback_checkpoint_sha256,
                record.canonicalization_receipt_fingerprint,
                record.stability_report_fingerprint,
            )
            if any(value is None for value in required):
                raise BaselineRegistryError(
                    "canonicalization record requires complete lineage evidence"
                )
            if (
                record.rollback_execution_receipt_fingerprint is not None
                or record.recovery_report_fingerprint is not None
            ):
                raise BaselineRegistryError("canonicalization record cannot claim rollback evidence")
        else:
            required = (
                record.previous_model_id,
                record.previous_checkpoint_sha256,
                record.rollback_execution_receipt_fingerprint,
                record.recovery_report_fingerprint,
            )
            if any(value is None for value in required):
                raise BaselineRegistryError("rollback record requires complete recovery evidence")
            if record.rollback_model_id is not None or record.rollback_checkpoint_sha256 is not None:
                raise BaselineRegistryError("rollback record cannot invent a new fallback target")
            if (
                record.canonicalization_receipt_fingerprint is not None
                or record.stability_report_fingerprint is not None
            ):
                raise BaselineRegistryError("rollback record cannot claim canonicalization evidence")

        base = record.as_dict()
        fingerprint = base.pop("record_fingerprint")
        self._require_sha(fingerprint, "record_fingerprint")
        if _canonical_hash(base) != fingerprint:
            raise BaselineRegistryError("baseline registry record fingerprint does not verify")

    @staticmethod
    def _require_model(value: str, label: str) -> None:
        if not isinstance(value, str) or not _MODEL_ID.fullmatch(value):
            raise ValueError(f"{label} must be a model candidate id")

    @staticmethod
    def _require_sha(value: str, label: str) -> None:
        if not isinstance(value, str) or not _SHA256.fullmatch(value):
            raise ValueError(f"{label} must be a lowercase SHA-256 digest")

    @staticmethod
    def _require_text(value: str, label: str) -> None:
        if not isinstance(value, str) or not value.strip():
            raise ValueError(f"{label} must be non-empty text")

    @staticmethod
    def _require_evidence(evidence_refs: tuple[str, ...]) -> None:
        if not evidence_refs or any(not ref.strip() for ref in evidence_refs):
            raise ValueError("baseline registry requires non-empty evidence references")

    @staticmethod
    def _optional_text(value: Any) -> str | None:
        return None if value is None else str(value)
