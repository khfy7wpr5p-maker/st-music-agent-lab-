from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from enum import Enum
from typing import Any

from .activation_request import ActivationRequest, ActivationRequestBuilder

ACTIVATION_RECEIPT_SCHEMA_VERSION = "1.0.0"
_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_MODEL_ID = re.compile(r"^model:[0-9a-f]{64}$")


class ActivationReceiptError(RuntimeError):
    pass


class ActivationReceiptOutcome(str, Enum):
    ACTIVATED = "activated"
    FAILED = "failed"
    ROLLED_BACK = "rolled_back"


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
class ActivationReceipt:
    request_id: str
    request_fingerprint: str
    candidate_id: str
    candidate_checkpoint_sha256: str
    target_environment: str
    previous_baseline_id: str
    previous_baseline_checkpoint_sha256: str
    rollback_candidate_id: str
    rollback_checkpoint_sha256: str
    outcome: ActivationReceiptOutcome
    host_authorization_ref: str
    deployment_ref: str
    evidence_refs: tuple[str, ...]
    observed_model_id: str | None
    observed_checkpoint_sha256: str | None
    receipt_fingerprint: str
    shadow_health_required: bool
    canonicalization_authorized: bool = False
    auto_canonicalize: bool = False

    def as_dict(self) -> dict[str, Any]:
        return {
            "schema_version": ACTIVATION_RECEIPT_SCHEMA_VERSION,
            "request_id": self.request_id,
            "request_fingerprint": self.request_fingerprint,
            "candidate_id": self.candidate_id,
            "candidate_checkpoint_sha256": self.candidate_checkpoint_sha256,
            "target_environment": self.target_environment,
            "previous_baseline_id": self.previous_baseline_id,
            "previous_baseline_checkpoint_sha256": self.previous_baseline_checkpoint_sha256,
            "rollback_candidate_id": self.rollback_candidate_id,
            "rollback_checkpoint_sha256": self.rollback_checkpoint_sha256,
            "outcome": self.outcome.value,
            "host_authorization_ref": self.host_authorization_ref,
            "deployment_ref": self.deployment_ref,
            "evidence_refs": list(self.evidence_refs),
            "observed_model_id": self.observed_model_id,
            "observed_checkpoint_sha256": self.observed_checkpoint_sha256,
            "receipt_fingerprint": self.receipt_fingerprint,
            "shadow_health_required": self.shadow_health_required,
            "canonicalization_authorized": self.canonicalization_authorized,
            "auto_canonicalize": self.auto_canonicalize,
        }


class ActivationReceiptBuilder:
    """Records externally executed activation outcomes without performing deployment itself."""

    def bind(
        self,
        request: ActivationRequest,
        *,
        outcome: ActivationReceiptOutcome,
        host_authorization_ref: str,
        deployment_ref: str,
        evidence_refs: tuple[str, ...],
        observed_model_id: str | None,
        observed_checkpoint_sha256: str | None,
    ) -> ActivationReceipt:
        ActivationRequestBuilder.verify(request)
        self._require_text(host_authorization_ref, "host_authorization_ref")
        self._require_text(deployment_ref, "deployment_ref")
        if not evidence_refs or any(not ref.strip() for ref in evidence_refs):
            raise ValueError("activation receipt requires non-empty evidence references")

        if outcome is ActivationReceiptOutcome.ACTIVATED:
            if observed_model_id != request.candidate_id:
                raise ActivationReceiptError("activated serving model does not match request")
            if observed_checkpoint_sha256 != request.candidate_checkpoint_sha256:
                raise ActivationReceiptError("activated checkpoint does not match request")
            shadow_health_required = True
        elif outcome is ActivationReceiptOutcome.ROLLED_BACK:
            if observed_model_id != request.rollback_candidate_id:
                raise ActivationReceiptError("rolled-back model does not match rollback target")
            if observed_checkpoint_sha256 != request.rollback_checkpoint_sha256:
                raise ActivationReceiptError("rolled-back checkpoint does not match rollback target")
            shadow_health_required = False
        else:
            if observed_model_id is not None or observed_checkpoint_sha256 is not None:
                raise ActivationReceiptError("failed activation cannot claim a serving model")
            shadow_health_required = False

        if observed_model_id is not None and not _MODEL_ID.fullmatch(observed_model_id):
            raise ValueError("observed_model_id must be a model candidate id")
        if observed_checkpoint_sha256 is not None and not _SHA256.fullmatch(
            observed_checkpoint_sha256
        ):
            raise ValueError("observed checkpoint hash is invalid")

        base = {
            "schema_version": ACTIVATION_RECEIPT_SCHEMA_VERSION,
            "request_id": request.request_id,
            "request_fingerprint": request.request_fingerprint,
            "candidate_id": request.candidate_id,
            "candidate_checkpoint_sha256": request.candidate_checkpoint_sha256,
            "target_environment": request.target_environment,
            "previous_baseline_id": request.current_baseline_id,
            "previous_baseline_checkpoint_sha256": request.current_baseline_checkpoint_sha256,
            "rollback_candidate_id": request.rollback_candidate_id,
            "rollback_checkpoint_sha256": request.rollback_checkpoint_sha256,
            "outcome": outcome.value,
            "host_authorization_ref": host_authorization_ref,
            "deployment_ref": deployment_ref,
            "evidence_refs": list(evidence_refs),
            "observed_model_id": observed_model_id,
            "observed_checkpoint_sha256": observed_checkpoint_sha256,
            "shadow_health_required": shadow_health_required,
            "canonicalization_authorized": False,
            "auto_canonicalize": False,
        }
        receipt_fingerprint = _canonical_hash(base)
        return ActivationReceipt(
            request_id=request.request_id,
            request_fingerprint=request.request_fingerprint,
            candidate_id=request.candidate_id,
            candidate_checkpoint_sha256=request.candidate_checkpoint_sha256,
            target_environment=request.target_environment,
            previous_baseline_id=request.current_baseline_id,
            previous_baseline_checkpoint_sha256=request.current_baseline_checkpoint_sha256,
            rollback_candidate_id=request.rollback_candidate_id,
            rollback_checkpoint_sha256=request.rollback_checkpoint_sha256,
            outcome=outcome,
            host_authorization_ref=host_authorization_ref,
            deployment_ref=deployment_ref,
            evidence_refs=evidence_refs,
            observed_model_id=observed_model_id,
            observed_checkpoint_sha256=observed_checkpoint_sha256,
            receipt_fingerprint=receipt_fingerprint,
            shadow_health_required=shadow_health_required,
            canonicalization_authorized=False,
            auto_canonicalize=False,
        )

    @staticmethod
    def verify(receipt: ActivationReceipt) -> None:
        if receipt.canonicalization_authorized or receipt.auto_canonicalize:
            raise ActivationReceiptError("activation receipt cannot authorize canonicalization")
        if receipt.rollback_candidate_id != receipt.previous_baseline_id:
            raise ActivationReceiptError("activation receipt rollback candidate is invalid")
        if receipt.rollback_checkpoint_sha256 != receipt.previous_baseline_checkpoint_sha256:
            raise ActivationReceiptError("activation receipt rollback checkpoint is invalid")

        if receipt.outcome is ActivationReceiptOutcome.ACTIVATED:
            if not receipt.shadow_health_required:
                raise ActivationReceiptError("activated receipt must require shadow health checks")
            if receipt.observed_model_id != receipt.candidate_id:
                raise ActivationReceiptError("activated receipt serving model is invalid")
            if receipt.observed_checkpoint_sha256 != receipt.candidate_checkpoint_sha256:
                raise ActivationReceiptError("activated receipt serving checkpoint is invalid")
        elif receipt.outcome is ActivationReceiptOutcome.ROLLED_BACK:
            if receipt.shadow_health_required:
                raise ActivationReceiptError("rolled-back receipt cannot require candidate health")
            if receipt.observed_model_id != receipt.rollback_candidate_id:
                raise ActivationReceiptError("rolled-back receipt serving model is invalid")
            if receipt.observed_checkpoint_sha256 != receipt.rollback_checkpoint_sha256:
                raise ActivationReceiptError("rolled-back receipt serving checkpoint is invalid")
        else:
            if receipt.shadow_health_required:
                raise ActivationReceiptError("failed receipt cannot require candidate health")
            if receipt.observed_model_id is not None or receipt.observed_checkpoint_sha256 is not None:
                raise ActivationReceiptError("failed receipt cannot claim a serving model")

        if not receipt.host_authorization_ref.strip() or not receipt.deployment_ref.strip():
            raise ActivationReceiptError("activation receipt is missing host evidence")
        if not receipt.evidence_refs or any(not ref.strip() for ref in receipt.evidence_refs):
            raise ActivationReceiptError("activation receipt is missing evidence references")

        base = receipt.as_dict()
        fingerprint = base.pop("receipt_fingerprint")
        if not _SHA256.fullmatch(fingerprint) or _canonical_hash(base) != fingerprint:
            raise ActivationReceiptError("activation receipt fingerprint does not verify")

    @staticmethod
    def _require_text(value: str, label: str) -> None:
        if not isinstance(value, str) or not value.strip():
            raise ValueError(f"{label} must be non-empty text")
