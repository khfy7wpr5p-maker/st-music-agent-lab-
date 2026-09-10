from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from enum import Enum
from pathlib import PurePosixPath
from typing import Mapping, Protocol, Sequence

from .models import TaskSpec


class ValidatorStatus(str, Enum):
    PASS = "PASS"
    FAIL = "FAIL"
    SKIP = "SKIP"
    ERROR = "ERROR"


class ValidationState(str, Enum):
    VERIFIED = "VERIFIED"
    REJECTED = "REJECTED"
    INCOMPLETE = "INCOMPLETE"


@dataclass(frozen=True, slots=True)
class ValidationContext:
    task: TaskSpec
    changed_paths: tuple[str, ...] = ()
    forbidden_paths: tuple[str, ...] = ()
    command_results: tuple[Mapping[str, object], ...] = ()
    schemas: Mapping[str, Mapping[str, object]] = field(default_factory=dict)
    determinism_pairs: Mapping[str, tuple[object, object]] = field(default_factory=dict)
    ci_runs: tuple[Mapping[str, object], ...] = ()
    metadata: Mapping[str, object] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class ValidatorResult:
    validator_id: str
    category: str
    status: ValidatorStatus
    blocking: bool
    summary: str
    evidence: tuple[str, ...] = ()

    @property
    def blocks_acceptance(self) -> bool:
        return self.blocking and self.status in {ValidatorStatus.FAIL, ValidatorStatus.ERROR}


@dataclass(frozen=True, slots=True)
class ValidationReport:
    state: ValidationState
    results: tuple[ValidatorResult, ...]
    required_validator_ids: tuple[str, ...]
    missing_required_validator_ids: tuple[str, ...]

    @property
    def accepted(self) -> bool:
        return self.state is ValidationState.VERIFIED

    def to_dict(self) -> dict[str, object]:
        return {
            "schema_version": "0.1.0",
            "state": self.state.value,
            "accepted": self.accepted,
            "required_validator_ids": list(self.required_validator_ids),
            "missing_required_validator_ids": list(self.missing_required_validator_ids),
            "results": [
                {
                    "validator_id": result.validator_id,
                    "category": result.category,
                    "status": result.status.value,
                    "blocking": result.blocking,
                    "summary": result.summary,
                    "evidence": list(result.evidence),
                }
                for result in self.results
            ],
        }


class Validator(Protocol):
    validator_id: str
    category: str
    blocking: bool

    def validate(self, context: ValidationContext) -> ValidatorResult: ...


class ValidatorRegistry:
    """Deterministic validator authority independent from the proposing agent."""

    def __init__(self, validators: Sequence[Validator] = ()) -> None:
        self._validators: dict[str, Validator] = {}
        for validator in validators:
            self.register(validator)

    def register(self, validator: Validator) -> None:
        validator_id = validator.validator_id.strip()
        if not validator_id:
            raise ValueError("validator_id must be non-empty")
        if validator_id in self._validators:
            raise ValueError(f"duplicate validator_id: {validator_id}")
        self._validators[validator_id] = validator

    @property
    def validator_ids(self) -> tuple[str, ...]:
        return tuple(sorted(self._validators))

    def run(
        self,
        context: ValidationContext,
        *,
        required_validator_ids: Sequence[str] = (),
    ) -> ValidationReport:
        required = tuple(sorted(set(required_validator_ids)))
        missing = tuple(validator_id for validator_id in required if validator_id not in self._validators)
        results: list[ValidatorResult] = []

        for validator_id in sorted(self._validators):
            validator = self._validators[validator_id]
            try:
                result = validator.validate(context)
            except Exception as exc:  # validator failure is evidence, never success
                result = ValidatorResult(
                    validator_id=validator.validator_id,
                    category=validator.category,
                    status=ValidatorStatus.ERROR,
                    blocking=validator.blocking,
                    summary=f"validator raised {type(exc).__name__}",
                    evidence=(),
                )
            if result.validator_id != validator.validator_id:
                raise ValueError("validator result id does not match registered validator id")
            results.append(result)

        if missing:
            state = ValidationState.INCOMPLETE
        elif any(result.blocks_acceptance for result in results):
            state = ValidationState.REJECTED
        elif any(
            result.validator_id in required and result.status in {ValidatorStatus.SKIP, ValidatorStatus.ERROR}
            for result in results
        ):
            state = ValidationState.INCOMPLETE
        else:
            state = ValidationState.VERIFIED

        return ValidationReport(
            state=state,
            results=tuple(results),
            required_validator_ids=required,
            missing_required_validator_ids=missing,
        )


@dataclass(frozen=True, slots=True)
class CommandEvidenceValidator:
    validator_id: str = "tests"
    category: str = "tests"
    blocking: bool = True

    def validate(self, context: ValidationContext) -> ValidatorResult:
        if not context.command_results:
            return ValidatorResult(
                self.validator_id,
                self.category,
                ValidatorStatus.SKIP,
                self.blocking,
                "no command evidence supplied",
            )

        failed: list[str] = []
        evidence: list[str] = []
        for index, item in enumerate(context.command_results, start=1):
            name = str(item.get("name") or item.get("command") or f"command-{index}")
            returncode = item.get("returncode")
            timed_out = bool(item.get("timed_out", False))
            evidence.append(f"{name}:returncode={returncode}:timed_out={timed_out}")
            if timed_out or returncode != 0:
                failed.append(name)

        if failed:
            return ValidatorResult(
                self.validator_id,
                self.category,
                ValidatorStatus.FAIL,
                self.blocking,
                "command evidence contains failures",
                tuple(evidence),
            )
        return ValidatorResult(
            self.validator_id,
            self.category,
            ValidatorStatus.PASS,
            self.blocking,
            "all supplied command evidence passed",
            tuple(evidence),
        )


@dataclass(frozen=True, slots=True)
class SchemaContractValidator:
    required_fields: Mapping[str, tuple[str, ...]]
    validator_id: str = "schema_contract"
    category: str = "schema_and_contract"
    blocking: bool = True

    def validate(self, context: ValidationContext) -> ValidatorResult:
        missing: list[str] = []
        evidence: list[str] = []
        for schema_name, fields in sorted(self.required_fields.items()):
            payload = context.schemas.get(schema_name)
            if payload is None:
                missing.append(f"{schema_name}:<document>")
                continue
            for field_name in fields:
                present = field_name in payload
                evidence.append(f"{schema_name}:{field_name}:{'present' if present else 'missing'}")
                if not present:
                    missing.append(f"{schema_name}:{field_name}")

        if missing:
            return ValidatorResult(
                self.validator_id,
                self.category,
                ValidatorStatus.FAIL,
                self.blocking,
                "required schema/contract fields are missing",
                tuple(sorted(missing)),
            )
        return ValidatorResult(
            self.validator_id,
            self.category,
            ValidatorStatus.PASS,
            self.blocking,
            "required schema/contract fields are present",
            tuple(evidence),
        )


@dataclass(frozen=True, slots=True)
class ForbiddenPathValidator:
    validator_id: str = "forbidden_path_diff_risk"
    category: str = "forbidden_path_and_diff_risk"
    blocking: bool = True

    @staticmethod
    def _inside(path: PurePosixPath, root: PurePosixPath) -> bool:
        return path == root or root in path.parents

    def validate(self, context: ValidationContext) -> ValidatorResult:
        violations: list[str] = []
        allowed_roots = tuple(PurePosixPath(path) for path in context.task.allowed_paths)
        forbidden_roots = tuple(PurePosixPath(path) for path in context.forbidden_paths)

        for raw_path in context.changed_paths:
            candidate = PurePosixPath(raw_path)
            if candidate.is_absolute() or ".." in candidate.parts:
                violations.append(f"unsafe:{raw_path}")
                continue
            if any(self._inside(candidate, root) for root in forbidden_roots):
                violations.append(f"forbidden:{raw_path}")
                continue
            if allowed_roots and not any(self._inside(candidate, root) for root in allowed_roots):
                violations.append(f"outside-allowed:{raw_path}")

        if violations:
            return ValidatorResult(
                self.validator_id,
                self.category,
                ValidatorStatus.FAIL,
                self.blocking,
                "changed paths exceed the admitted diff boundary",
                tuple(sorted(violations)),
            )
        return ValidatorResult(
            self.validator_id,
            self.category,
            ValidatorStatus.PASS,
            self.blocking,
            "changed paths stay within admitted boundaries",
            tuple(sorted(context.changed_paths)),
        )


@dataclass(frozen=True, slots=True)
class DeterminismValidator:
    validator_id: str = "determinism"
    category: str = "deterministic_rerun"
    blocking: bool = True

    @staticmethod
    def _digest(value: object) -> str:
        encoded = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, default=str).encode("utf-8")
        return hashlib.sha256(encoded).hexdigest()

    def validate(self, context: ValidationContext) -> ValidatorResult:
        if not context.determinism_pairs:
            return ValidatorResult(
                self.validator_id,
                self.category,
                ValidatorStatus.SKIP,
                self.blocking,
                "no deterministic rerun evidence supplied",
            )
        mismatches: list[str] = []
        evidence: list[str] = []
        for name, (left, right) in sorted(context.determinism_pairs.items()):
            left_digest = self._digest(left)
            right_digest = self._digest(right)
            evidence.append(f"{name}:{left_digest}:{right_digest}")
            if left_digest != right_digest:
                mismatches.append(name)
        if mismatches:
            return ValidatorResult(
                self.validator_id,
                self.category,
                ValidatorStatus.FAIL,
                self.blocking,
                "rerun evidence is not deterministic",
                tuple(sorted(mismatches)),
            )
        return ValidatorResult(
            self.validator_id,
            self.category,
            ValidatorStatus.PASS,
            self.blocking,
            "rerun evidence is deterministic",
            tuple(evidence),
        )


@dataclass(frozen=True, slots=True)
class CIStatusValidator:
    validator_id: str = "ci_required_checks"
    category: str = "ci_required_checks"
    blocking: bool = True

    def validate(self, context: ValidationContext) -> ValidatorResult:
        if not context.ci_runs:
            return ValidatorResult(
                self.validator_id,
                self.category,
                ValidatorStatus.SKIP,
                self.blocking,
                "no CI evidence supplied",
            )

        failures: list[str] = []
        pending: list[str] = []
        evidence: list[str] = []
        for index, run in enumerate(context.ci_runs, start=1):
            name = str(run.get("name") or f"ci-{index}")
            status = str(run.get("status") or "unknown")
            conclusion = run.get("conclusion")
            evidence.append(f"{name}:{status}:{conclusion}")
            if status != "completed":
                pending.append(name)
            elif conclusion not in {"success", "neutral", "skipped"}:
                failures.append(name)

        if failures:
            return ValidatorResult(
                self.validator_id,
                self.category,
                ValidatorStatus.FAIL,
                self.blocking,
                "CI evidence contains failed required checks",
                tuple(sorted(failures)),
            )
        if pending:
            return ValidatorResult(
                self.validator_id,
                self.category,
                ValidatorStatus.SKIP,
                self.blocking,
                "CI evidence is still in progress",
                tuple(sorted(pending)),
            )
        return ValidatorResult(
            self.validator_id,
            self.category,
            ValidatorStatus.PASS,
            self.blocking,
            "all supplied CI checks passed",
            tuple(evidence),
        )
