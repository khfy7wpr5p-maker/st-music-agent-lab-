from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Mapping
from dataclasses import dataclass
from enum import Enum
from typing import Any

from .agent_tools import ToolRegistry

EVALUATION_SCHEMA_VERSION = "1.0.0"
EVALUATION_POLICY_VERSION = "2026-09-11.v1"
_CANDIDATE_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}$")
_CASE_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}$")


class LearningEvaluationError(RuntimeError):
    pass


class BenchmarkOutcome(str, Enum):
    SUCCESS = "success"
    ABSTAINED = "abstained"
    FAILURE = "failure"


class BenchmarkSeverity(str, Enum):
    STANDARD = "standard"
    CRITICAL = "critical"


class PromotionDecision(str, Enum):
    ELIGIBLE_FOR_HOST_REVIEW = "eligible_for_host_review"
    REJECTED = "rejected"


_OUTCOME_RANK = {
    BenchmarkOutcome.FAILURE: 0,
    BenchmarkOutcome.ABSTAINED: 1,
    BenchmarkOutcome.SUCCESS: 2,
}


@dataclass(frozen=True, slots=True)
class BenchmarkCaseResult:
    case_id: str
    severity: BenchmarkSeverity
    outcome: BenchmarkOutcome
    evidence_refs: tuple[str, ...]

    def __post_init__(self) -> None:
        if not _CASE_ID.fullmatch(self.case_id):
            raise ValueError("case_id has an invalid format")
        if not self.evidence_refs:
            raise ValueError("benchmark result requires evidence references")
        if any(not ref.strip() for ref in self.evidence_refs):
            raise ValueError("benchmark evidence references must not be empty")

    def as_dict(self) -> dict[str, Any]:
        return {
            "case_id": self.case_id,
            "severity": self.severity.value,
            "outcome": self.outcome.value,
            "evidence_refs": list(self.evidence_refs),
        }


@dataclass(frozen=True, slots=True)
class BenchmarkRun:
    candidate_id: str
    results: tuple[BenchmarkCaseResult, ...]

    def __post_init__(self) -> None:
        if not _CANDIDATE_ID.fullmatch(self.candidate_id):
            raise ValueError("candidate_id has an invalid format")
        if not self.results:
            raise ValueError("benchmark run must contain results")
        case_ids = [result.case_id for result in self.results]
        if len(case_ids) != len(set(case_ids)):
            raise ValueError("benchmark case ids must be unique")

    def result_map(self) -> dict[str, BenchmarkCaseResult]:
        return {result.case_id: result for result in self.results}

    def fingerprint(self) -> str:
        payload = {
            "candidate_id": self.candidate_id,
            "results": [
                result.as_dict()
                for result in sorted(self.results, key=lambda item: item.case_id)
            ],
        }
        encoded = json.dumps(
            payload,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        )
        return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


@dataclass(frozen=True, slots=True)
class LearningEvaluationPolicy:
    minimum_cases: int = 8
    minimum_critical_cases: int = 2

    def __post_init__(self) -> None:
        if self.minimum_cases < 1:
            raise ValueError("minimum_cases must be positive")
        if self.minimum_critical_cases < 0:
            raise ValueError("minimum_critical_cases must not be negative")
        if self.minimum_critical_cases > self.minimum_cases:
            raise ValueError("minimum_critical_cases cannot exceed minimum_cases")


@dataclass(frozen=True, slots=True)
class LearningEvaluationReport:
    policy_version: str
    baseline_id: str
    candidate_id: str
    baseline_fingerprint: str
    candidate_fingerprint: str
    compared_cases: int
    critical_cases: int
    improved_cases: tuple[str, ...]
    regressed_cases: tuple[str, ...]
    candidate_critical_failures: tuple[str, ...]
    decision: PromotionDecision
    reasons: tuple[str, ...]
    auto_promote: bool = False

    def as_dict(self) -> dict[str, Any]:
        return {
            "schema_version": EVALUATION_SCHEMA_VERSION,
            "policy_version": self.policy_version,
            "baseline_id": self.baseline_id,
            "candidate_id": self.candidate_id,
            "baseline_fingerprint": self.baseline_fingerprint,
            "candidate_fingerprint": self.candidate_fingerprint,
            "compared_cases": self.compared_cases,
            "critical_cases": self.critical_cases,
            "improved_cases": list(self.improved_cases),
            "regressed_cases": list(self.regressed_cases),
            "candidate_critical_failures": list(self.candidate_critical_failures),
            "decision": self.decision.value,
            "reasons": list(self.reasons),
            "auto_promote": self.auto_promote,
        }


class LearningEvaluationGate:
    """Host-side paired benchmark gate for playbook/model candidates.

    The gate never promotes a candidate. It can only mark a candidate eligible for explicit
    host review after a non-regressing paired comparison against the current baseline.
    """

    def __init__(self, policy: LearningEvaluationPolicy | None = None) -> None:
        self.policy = policy or LearningEvaluationPolicy()

    def compare(
        self,
        baseline: BenchmarkRun,
        candidate: BenchmarkRun,
    ) -> LearningEvaluationReport:
        if baseline.candidate_id == candidate.candidate_id:
            raise LearningEvaluationError("baseline and candidate ids must differ")

        baseline_map = baseline.result_map()
        candidate_map = candidate.result_map()
        if set(baseline_map) != set(candidate_map):
            raise LearningEvaluationError(
                "baseline and candidate must cover the exact same cases"
            )

        ordered_ids = tuple(sorted(baseline_map))
        if len(ordered_ids) < self.policy.minimum_cases:
            raise LearningEvaluationError("benchmark does not meet minimum case count")

        severity_mismatches = [
            case_id
            for case_id in ordered_ids
            if baseline_map[case_id].severity is not candidate_map[case_id].severity
        ]
        if severity_mismatches:
            raise LearningEvaluationError("baseline and candidate case severities differ")

        critical_cases = tuple(
            case_id
            for case_id in ordered_ids
            if baseline_map[case_id].severity is BenchmarkSeverity.CRITICAL
        )
        if len(critical_cases) < self.policy.minimum_critical_cases:
            raise LearningEvaluationError(
                "benchmark does not meet minimum critical case count"
            )

        improved: list[str] = []
        regressed: list[str] = []
        critical_failures: list[str] = []
        for case_id in ordered_ids:
            baseline_result = baseline_map[case_id]
            candidate_result = candidate_map[case_id]
            baseline_rank = _OUTCOME_RANK[baseline_result.outcome]
            candidate_rank = _OUTCOME_RANK[candidate_result.outcome]
            if candidate_rank > baseline_rank:
                improved.append(case_id)
            elif candidate_rank < baseline_rank:
                regressed.append(case_id)
            if (
                candidate_result.severity is BenchmarkSeverity.CRITICAL
                and candidate_result.outcome is BenchmarkOutcome.FAILURE
            ):
                critical_failures.append(case_id)

        reasons: list[str] = []
        if regressed:
            reasons.append("candidate regresses one or more paired benchmark cases")
        if critical_failures:
            reasons.append("candidate has one or more critical benchmark failures")
        if not improved:
            reasons.append("candidate does not improve any paired benchmark case")

        decision = (
            PromotionDecision.ELIGIBLE_FOR_HOST_REVIEW
            if not reasons
            else PromotionDecision.REJECTED
        )
        return LearningEvaluationReport(
            policy_version=EVALUATION_POLICY_VERSION,
            baseline_id=baseline.candidate_id,
            candidate_id=candidate.candidate_id,
            baseline_fingerprint=baseline.fingerprint(),
            candidate_fingerprint=candidate.fingerprint(),
            compared_cases=len(ordered_ids),
            critical_cases=len(critical_cases),
            improved_cases=tuple(improved),
            regressed_cases=tuple(regressed),
            candidate_critical_failures=tuple(critical_failures),
            decision=decision,
            reasons=tuple(reasons),
            auto_promote=False,
        )

    def policy_snapshot(self) -> dict[str, Any]:
        return {
            "schema_version": EVALUATION_SCHEMA_VERSION,
            "policy_version": EVALUATION_POLICY_VERSION,
            "minimum_cases": self.policy.minimum_cases,
            "minimum_critical_cases": self.policy.minimum_critical_cases,
            "paired_case_sets_required": True,
            "case_severity_match_required": True,
            "regression_allowed": False,
            "at_least_one_improvement_required": True,
            "critical_failure_allowed": False,
            "auto_promote": False,
        }


class LearningEvaluationReadToolset:
    """Read-only model surface describing the host-side evaluation gate."""

    def __init__(self, gate: LearningEvaluationGate | None = None) -> None:
        self.gate = gate or LearningEvaluationGate()

    def register_into(self, registry: ToolRegistry) -> None:
        registry.register(
            "learning.evaluation.policy",
            self._policy,
            description=(
                "Read the current paired benchmark gate. This tool cannot submit benchmark "
                "results, approve candidates or promote models/playbooks."
            ),
            parameters={
                "type": "object",
                "properties": {},
                "additionalProperties": False,
            },
        )

    def _policy(self, arguments: Mapping[str, Any]) -> Mapping[str, Any]:
        if arguments:
            raise ValueError("learning.evaluation.policy accepts no arguments")
        return self.gate.policy_snapshot()
