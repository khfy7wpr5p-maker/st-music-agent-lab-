from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from enum import Enum
from typing import Any

from .baseline_registry import BaselineRecord, BaselineRecordKind

DRIFT_WATCH_SCHEMA_VERSION = "1.0.0"
ROLLBACK_REVIEW_REQUEST_SCHEMA_VERSION = "1.0.0"
DRIFT_WATCH_POLICY_VERSION = "2026-09-11.v1"
MIN_DRIFT_WINDOWS = 4
MIN_CONSECUTIVE_DEGRADED_WINDOWS = 2
_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_MODEL_ID = re.compile(r"^model:[0-9a-f]{64}$")


class DriftWatchError(RuntimeError):
    pass


class DriftCheckKind(str, Enum):
    SERVING_IDENTITY = "serving_identity"
    HEALTH = "health"
    QUALITY = "quality"
    DISTRIBUTION = "distribution"
    ROLLBACK_READINESS = "rollback_readiness"


class DriftCheckStatus(str, Enum):
    STABLE = "stable"
    DEGRADED = "degraded"
    FAILED = "failed"
    UNAVAILABLE = "unavailable"


class DriftWatchDecision(str, Enum):
    HEALTHY = "healthy"
    OBSERVE = "observe"
    ELIGIBLE_FOR_ROLLBACK_REVIEW = "eligible_for_rollback_review"


class RollbackReviewDecision(str, Enum):
    ELIGIBLE_FOR_HOST_ROLLBACK_REVIEW = "eligible_for_host_rollback_review"


def _canonical_hash(value: Any) -> str:
    encoded = json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _require_sha(value: str, label: str) -> None:
    if not isinstance(value, str) or not _SHA256.fullmatch(value):
        raise DriftWatchError(f"{label} must be a lowercase SHA-256 digest")


def _require_model(value: str, label: str) -> None:
    if not isinstance(value, str) or not _MODEL_ID.fullmatch(value):
        raise DriftWatchError(f"{label} must be a model candidate id")


def _require_text(value: str, label: str) -> None:
    if not isinstance(value, str) or not value.strip():
        raise DriftWatchError(f"{label} must be non-empty text")


@dataclass(frozen=True, slots=True)
class DriftCheck:
    kind: DriftCheckKind
    status: DriftCheckStatus
    evidence_refs: tuple[str, ...]
    observed_model_id: str | None = None
    observed_checkpoint_sha256: str | None = None

    def as_dict(self) -> dict[str, Any]:
        return {
            "kind": self.kind.value,
            "status": self.status.value,
            "evidence_refs": list(self.evidence_refs),
            "observed_model_id": self.observed_model_id,
            "observed_checkpoint_sha256": self.observed_checkpoint_sha256,
        }


@dataclass(frozen=True, slots=True)
class DriftObservationWindow:
    window_id: str
    checks: tuple[DriftCheck, ...]

    def as_dict(self) -> dict[str, Any]:
        return {
            "window_id": self.window_id,
            "checks": [check.as_dict() for check in self.checks],
        }


@dataclass(frozen=True, slots=True)
class DriftWatchReport:
    policy_version: str
    baseline_record_fingerprint: str
    environment: str
    model_id: str
    checkpoint_sha256: str
    rollback_model_id: str | None
    rollback_checkpoint_sha256: str | None
    window_ids: tuple[str, ...]
    degraded_window_count: int
    max_consecutive_degraded_windows: int
    latest_window_degraded: bool
    decision: DriftWatchDecision
    reasons: tuple[str, ...]
    report_fingerprint: str
    host_review_required: bool = True
    rollback_authorized: bool = False
    auto_rollback: bool = False

    def as_dict(self) -> dict[str, Any]:
        return {
            "schema_version": DRIFT_WATCH_SCHEMA_VERSION,
            "policy_version": self.policy_version,
            "baseline_record_fingerprint": self.baseline_record_fingerprint,
            "environment": self.environment,
            "model_id": self.model_id,
            "checkpoint_sha256": self.checkpoint_sha256,
            "rollback_model_id": self.rollback_model_id,
            "rollback_checkpoint_sha256": self.rollback_checkpoint_sha256,
            "window_ids": list(self.window_ids),
            "degraded_window_count": self.degraded_window_count,
            "max_consecutive_degraded_windows": self.max_consecutive_degraded_windows,
            "latest_window_degraded": self.latest_window_degraded,
            "decision": self.decision.value,
            "reasons": list(self.reasons),
            "report_fingerprint": self.report_fingerprint,
            "host_review_required": self.host_review_required,
            "rollback_authorized": self.rollback_authorized,
            "auto_rollback": self.auto_rollback,
        }


class DriftWatchGate:
    """Evaluates sustained canonical-baseline drift without executing rollback."""

    _DEGRADATION_KINDS = {
        DriftCheckKind.HEALTH,
        DriftCheckKind.QUALITY,
        DriftCheckKind.DISTRIBUTION,
    }

    def evaluate(
        self,
        baseline: BaselineRecord,
        windows: tuple[DriftObservationWindow, ...],
    ) -> DriftWatchReport:
        self.verify_baseline_record(baseline)
        if len(windows) < MIN_DRIFT_WINDOWS:
            raise DriftWatchError(
                f"drift watch requires at least {MIN_DRIFT_WINDOWS} observation windows"
            )

        expected = set(DriftCheckKind)
        seen_window_ids: set[str] = set()
        degraded_flags: list[bool] = []
        unavailable_seen = False
        rollback_ready = True

        for window in windows:
            _require_text(window.window_id, "window_id")
            if window.window_id in seen_window_ids:
                raise DriftWatchError("drift observation window ids must be unique")
            seen_window_ids.add(window.window_id)
            by_kind = {check.kind: check for check in window.checks}
            if len(by_kind) != len(window.checks) or set(by_kind) != expected:
                raise DriftWatchError("each drift window requires exactly one check of every kind")

            for check in window.checks:
                if not check.evidence_refs or any(not ref.strip() for ref in check.evidence_refs):
                    raise DriftWatchError("drift checks require evidence references")
                if check.observed_model_id is not None:
                    _require_model(check.observed_model_id, "observed model id")
                if check.observed_checkpoint_sha256 is not None:
                    _require_sha(check.observed_checkpoint_sha256, "observed checkpoint")
                if check.status is DriftCheckStatus.UNAVAILABLE:
                    unavailable_seen = True

            identity = by_kind[DriftCheckKind.SERVING_IDENTITY]
            if identity.observed_model_id != baseline.model_id:
                raise DriftWatchError("serving identity does not match registered baseline")
            if identity.observed_checkpoint_sha256 != baseline.checkpoint_sha256:
                raise DriftWatchError("serving checkpoint does not match registered baseline")
            if identity.status is not DriftCheckStatus.STABLE:
                raise DriftWatchError("serving identity must remain stable during drift watch")

            readiness = by_kind[DriftCheckKind.ROLLBACK_READINESS]
            if readiness.status is not DriftCheckStatus.STABLE:
                rollback_ready = False

            degraded = any(
                by_kind[kind].status in (DriftCheckStatus.DEGRADED, DriftCheckStatus.FAILED)
                for kind in self._DEGRADATION_KINDS
            )
            degraded_flags.append(degraded)

        max_streak = 0
        current_streak = 0
        for degraded in degraded_flags:
            current_streak = current_streak + 1 if degraded else 0
            max_streak = max(max_streak, current_streak)

        latest_degraded = degraded_flags[-1]
        degraded_count = sum(degraded_flags)
        reasons: list[str] = []
        if unavailable_seen:
            decision = DriftWatchDecision.OBSERVE
            reasons.append("one or more drift checks are unavailable")
        elif not rollback_ready:
            decision = DriftWatchDecision.OBSERVE
            reasons.append("rollback readiness is not stable across all observation windows")
        elif degraded_count == 0:
            decision = DriftWatchDecision.HEALTHY
            reasons.append("no canonical-baseline drift or regression was observed")
        elif baseline.rollback_model_id is None or baseline.rollback_checkpoint_sha256 is None:
            decision = DriftWatchDecision.OBSERVE
            reasons.append("registered baseline has no exact rollback predecessor")
        elif (
            max_streak >= MIN_CONSECUTIVE_DEGRADED_WINDOWS
            and latest_degraded
        ):
            decision = DriftWatchDecision.ELIGIBLE_FOR_ROLLBACK_REVIEW
            reasons.append("sustained drift or regression remains present in the latest window")
        else:
            decision = DriftWatchDecision.OBSERVE
            reasons.append("degradation is not yet sustained enough for rollback review")

        base = {
            "schema_version": DRIFT_WATCH_SCHEMA_VERSION,
            "policy_version": DRIFT_WATCH_POLICY_VERSION,
            "baseline_record_fingerprint": baseline.record_fingerprint,
            "environment": baseline.environment,
            "model_id": baseline.model_id,
            "checkpoint_sha256": baseline.checkpoint_sha256,
            "rollback_model_id": baseline.rollback_model_id,
            "rollback_checkpoint_sha256": baseline.rollback_checkpoint_sha256,
            "window_ids": [window.window_id for window in windows],
            "degraded_window_count": degraded_count,
            "max_consecutive_degraded_windows": max_streak,
            "latest_window_degraded": latest_degraded,
            "decision": decision.value,
            "reasons": reasons,
            "host_review_required": True,
            "rollback_authorized": False,
            "auto_rollback": False,
        }
        return DriftWatchReport(
            policy_version=DRIFT_WATCH_POLICY_VERSION,
            baseline_record_fingerprint=baseline.record_fingerprint,
            environment=baseline.environment,
            model_id=baseline.model_id,
            checkpoint_sha256=baseline.checkpoint_sha256,
            rollback_model_id=baseline.rollback_model_id,
            rollback_checkpoint_sha256=baseline.rollback_checkpoint_sha256,
            window_ids=tuple(window.window_id for window in windows),
            degraded_window_count=degraded_count,
            max_consecutive_degraded_windows=max_streak,
            latest_window_degraded=latest_degraded,
            decision=decision,
            reasons=tuple(reasons),
            report_fingerprint=_canonical_hash(base),
        )

    def verify(
        self,
        baseline: BaselineRecord,
        windows: tuple[DriftObservationWindow, ...],
        report: DriftWatchReport,
    ) -> None:
        recomputed = self.evaluate(baseline, windows)
        if recomputed.as_dict() != report.as_dict():
            raise DriftWatchError("drift report differs from source-evidence recomputation")

    @staticmethod
    def verify_baseline_record(record: BaselineRecord) -> None:
        _require_model(record.model_id, "baseline model id")
        _require_sha(record.checkpoint_sha256, "baseline checkpoint")
        _require_sha(record.record_fingerprint, "baseline record fingerprint")
        _require_text(record.environment, "baseline environment")
        if record.auto_switch or record.auto_rollback:
            raise DriftWatchError("baseline record cannot authorize automatic actions")
        if record.record_kind is BaselineRecordKind.CANONICALIZATION:
            if (
                record.previous_model_id is None
                or record.previous_checkpoint_sha256 is None
                or record.rollback_model_id is None
                or record.rollback_checkpoint_sha256 is None
            ):
                raise DriftWatchError("canonical baseline record has incomplete rollback lineage")
            if record.rollback_model_id != record.previous_model_id:
                raise DriftWatchError("baseline rollback model differs from predecessor")
            if record.rollback_checkpoint_sha256 != record.previous_checkpoint_sha256:
                raise DriftWatchError("baseline rollback checkpoint differs from predecessor")

        base = record.as_dict()
        fingerprint = base.pop("record_fingerprint")
        if _canonical_hash(base) != fingerprint:
            raise DriftWatchError("baseline record fingerprint does not verify")


@dataclass(frozen=True, slots=True)
class RollbackReviewRequest:
    baseline_record_fingerprint: str
    drift_report_fingerprint: str
    environment: str
    current_model_id: str
    current_checkpoint_sha256: str
    rollback_model_id: str
    rollback_checkpoint_sha256: str
    decision: RollbackReviewDecision
    evidence_refs: tuple[str, ...]
    request_fingerprint: str
    human_approval_required: bool = True
    rollback_authorized: bool = False
    auto_rollback: bool = False

    def as_dict(self) -> dict[str, Any]:
        return {
            "schema_version": ROLLBACK_REVIEW_REQUEST_SCHEMA_VERSION,
            "baseline_record_fingerprint": self.baseline_record_fingerprint,
            "drift_report_fingerprint": self.drift_report_fingerprint,
            "environment": self.environment,
            "current_model_id": self.current_model_id,
            "current_checkpoint_sha256": self.current_checkpoint_sha256,
            "rollback_model_id": self.rollback_model_id,
            "rollback_checkpoint_sha256": self.rollback_checkpoint_sha256,
            "decision": self.decision.value,
            "evidence_refs": list(self.evidence_refs),
            "request_fingerprint": self.request_fingerprint,
            "human_approval_required": self.human_approval_required,
            "rollback_authorized": self.rollback_authorized,
            "auto_rollback": self.auto_rollback,
        }


class RollbackReviewRequestBuilder:
    """Builds a host-review request only; it never executes rollback."""

    def build(
        self,
        baseline: BaselineRecord,
        windows: tuple[DriftObservationWindow, ...],
        report: DriftWatchReport,
        *,
        evidence_refs: tuple[str, ...],
    ) -> RollbackReviewRequest:
        gate = DriftWatchGate()
        gate.verify(baseline, windows, report)
        if report.decision is not DriftWatchDecision.ELIGIBLE_FOR_ROLLBACK_REVIEW:
            raise DriftWatchError("drift report is not eligible for rollback review")
        if baseline.rollback_model_id is None or baseline.rollback_checkpoint_sha256 is None:
            raise DriftWatchError("baseline does not have an exact rollback target")
        if not evidence_refs or any(not ref.strip() for ref in evidence_refs):
            raise DriftWatchError("rollback review request requires evidence references")

        base = {
            "schema_version": ROLLBACK_REVIEW_REQUEST_SCHEMA_VERSION,
            "baseline_record_fingerprint": baseline.record_fingerprint,
            "drift_report_fingerprint": report.report_fingerprint,
            "environment": baseline.environment,
            "current_model_id": baseline.model_id,
            "current_checkpoint_sha256": baseline.checkpoint_sha256,
            "rollback_model_id": baseline.rollback_model_id,
            "rollback_checkpoint_sha256": baseline.rollback_checkpoint_sha256,
            "decision": RollbackReviewDecision.ELIGIBLE_FOR_HOST_ROLLBACK_REVIEW.value,
            "evidence_refs": list(evidence_refs),
            "human_approval_required": True,
            "rollback_authorized": False,
            "auto_rollback": False,
        }
        return RollbackReviewRequest(
            baseline_record_fingerprint=baseline.record_fingerprint,
            drift_report_fingerprint=report.report_fingerprint,
            environment=baseline.environment,
            current_model_id=baseline.model_id,
            current_checkpoint_sha256=baseline.checkpoint_sha256,
            rollback_model_id=baseline.rollback_model_id,
            rollback_checkpoint_sha256=baseline.rollback_checkpoint_sha256,
            decision=RollbackReviewDecision.ELIGIBLE_FOR_HOST_ROLLBACK_REVIEW,
            evidence_refs=evidence_refs,
            request_fingerprint=_canonical_hash(base),
        )

    def verify_with_evidence(
        self,
        baseline: BaselineRecord,
        windows: tuple[DriftObservationWindow, ...],
        report: DriftWatchReport,
        request: RollbackReviewRequest,
    ) -> None:
        recomputed = self.build(
            baseline,
            windows,
            report,
            evidence_refs=request.evidence_refs,
        )
        if recomputed.as_dict() != request.as_dict():
            raise DriftWatchError("rollback request differs from source-evidence recomputation")

    @staticmethod
    def verify_record(request: RollbackReviewRequest) -> None:
        if not request.human_approval_required:
            raise DriftWatchError("rollback review request must require human approval")
        if request.rollback_authorized or request.auto_rollback:
            raise DriftWatchError("rollback review request cannot authorize rollback")
        _require_model(request.current_model_id, "current model id")
        _require_model(request.rollback_model_id, "rollback model id")
        _require_sha(request.current_checkpoint_sha256, "current checkpoint")
        _require_sha(request.rollback_checkpoint_sha256, "rollback checkpoint")
        _require_sha(request.baseline_record_fingerprint, "baseline record fingerprint")
        _require_sha(request.drift_report_fingerprint, "drift report fingerprint")
        _require_sha(request.request_fingerprint, "rollback request fingerprint")
        if not request.evidence_refs or any(not ref.strip() for ref in request.evidence_refs):
            raise DriftWatchError("rollback review request requires evidence references")
        base = request.as_dict()
        fingerprint = base.pop("request_fingerprint")
        if _canonical_hash(base) != fingerprint:
            raise DriftWatchError("rollback review request fingerprint does not verify")
