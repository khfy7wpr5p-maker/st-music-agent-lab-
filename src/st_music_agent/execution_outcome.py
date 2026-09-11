from __future__ import annotations

import re
from collections.abc import Mapping
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Any

from .journal import JournalEvent, RunJournal
from .music_evidence import MusicProject
from .portfolio_planning import (
    CrossProjectPlan,
    PlanCandidate,
    PlanVerificationReport,
    PlanVerificationStatus,
)

EXECUTION_OUTCOME_SCHEMA_VERSION = "1.0.0"
_COMMIT_SHA = re.compile(r"^[0-9a-f]{40}$")
_REF = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:/-]{0,255}$")


class ExecutionOutcomeError(RuntimeError):
    pass


class ExecutionOutcomeStatus(str, Enum):
    SUCCESS = "success"
    FAILURE = "failure"
    ABSTAINED = "abstained"


class EvidenceCheckStatus(str, Enum):
    SUCCESS = "success"
    FAILURE = "failure"
    SKIPPED = "skipped"


@dataclass(frozen=True, slots=True)
class ExecutionCheck:
    name: str
    status: EvidenceCheckStatus
    evidence_ref: str

    def __post_init__(self) -> None:
        if not self.name.strip():
            raise ValueError("check name must not be empty")
        if not self.evidence_ref.strip():
            raise ValueError("check evidence_ref must not be empty")

    def as_dict(self) -> dict[str, str]:
        return {
            "name": self.name,
            "status": self.status.value,
            "evidence_ref": self.evidence_ref,
        }


@dataclass(frozen=True, slots=True)
class ExecutionObservation:
    plan_id: str
    project: MusicProject
    candidate_rank: int
    action: str
    candidate_evidence_hash: str
    repository: str
    branch: str
    commit_sha: str
    outcome: ExecutionOutcomeStatus
    ci_checks: tuple[ExecutionCheck, ...]
    validator_checks: tuple[ExecutionCheck, ...]
    notes: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if not self.plan_id.strip():
            raise ValueError("plan_id must not be empty")
        if self.candidate_rank < 1:
            raise ValueError("candidate_rank must be positive")
        if not self.action.strip():
            raise ValueError("action must not be empty")
        if not re.fullmatch(r"[0-9a-f]{64}", self.candidate_evidence_hash):
            raise ValueError("candidate_evidence_hash must be a SHA-256 hex digest")
        if not self.repository.strip() or "/" not in self.repository:
            raise ValueError("repository must be owner/name text")
        if not _REF.fullmatch(self.branch):
            raise ValueError("branch has an invalid format")
        if not _COMMIT_SHA.fullmatch(self.commit_sha):
            raise ValueError("commit_sha must be a full lowercase 40-hex SHA")
        if not self.ci_checks:
            raise ValueError("at least one CI check is required")
        if not self.validator_checks:
            raise ValueError("at least one validator check is required")
        if any(not note.strip() for note in self.notes):
            raise ValueError("notes must not contain empty values")


@dataclass(frozen=True, slots=True)
class ExecutionRecord:
    record_id: str
    sequence: int
    timestamp: str
    plan_id: str
    project: MusicProject
    candidate_rank: int
    action: str
    candidate_evidence_hash: str
    repository: str
    branch: str
    commit_sha: str
    outcome: ExecutionOutcomeStatus
    ci_checks: tuple[ExecutionCheck, ...]
    validator_checks: tuple[ExecutionCheck, ...]
    notes: tuple[str, ...]

    def as_dict(self) -> dict[str, Any]:
        return {
            "schema_version": EXECUTION_OUTCOME_SCHEMA_VERSION,
            "record_id": self.record_id,
            "sequence": self.sequence,
            "timestamp": self.timestamp,
            "plan_id": self.plan_id,
            "project": self.project.value,
            "candidate_rank": self.candidate_rank,
            "action": self.action,
            "candidate_evidence_hash": self.candidate_evidence_hash,
            "repository": self.repository,
            "branch": self.branch,
            "commit_sha": self.commit_sha,
            "outcome": self.outcome.value,
            "ci_checks": [check.as_dict() for check in self.ci_checks],
            "validator_checks": [check.as_dict() for check in self.validator_checks],
            "notes": list(self.notes),
        }


_PROJECT_REPOSITORIES = {
    MusicProject.SCORE_RESTORE: "khfy7wpr5p-maker/st-score-restore-engine",
    MusicProject.MUSICXML_GUITAR_TAB: "khfy7wpr5p-maker/musicxml-to-guitar-tab-engine",
    MusicProject.SCORE_EDITOR: "khfy7wpr5p-maker/st-score-editor-core",
    MusicProject.REAL_TIME_SCORE_FOLLOWING: "khfy7wpr5p-maker/st-real-time-score-following-lab",
}


class ExecutionOutcomeStore:
    """Host-only hash-chained store for outcomes bound to an exact verified plan candidate."""

    _RUN_ID = "st-music-agent-execution-outcomes-v1"
    _EVENT_TYPE = "verified_execution_outcome"

    def __init__(self, path: Path) -> None:
        self.journal = RunJournal(path, self._RUN_ID)

    def record_verified(
        self,
        observation: ExecutionObservation,
        plan: CrossProjectPlan,
        verification: PlanVerificationReport,
    ) -> ExecutionRecord:
        candidate = self._validate_binding(observation, plan, verification)
        self._validate_result_semantics(observation)
        payload = {
            "schema_version": EXECUTION_OUTCOME_SCHEMA_VERSION,
            "plan_id": observation.plan_id,
            "project": observation.project.value,
            "candidate_rank": observation.candidate_rank,
            "action": observation.action,
            "candidate_evidence_hash": observation.candidate_evidence_hash,
            "repository": observation.repository,
            "branch": observation.branch,
            "commit_sha": observation.commit_sha,
            "outcome": observation.outcome.value,
            "ci_checks": [check.as_dict() for check in observation.ci_checks],
            "validator_checks": [check.as_dict() for check in observation.validator_checks],
            "notes": list(observation.notes),
            "plan_candidate_category": candidate.category,
        }
        event = self.journal.append(self._EVENT_TYPE, payload)
        return self._record_from_event(event)

    def read_records(self) -> tuple[ExecutionRecord, ...]:
        records: list[ExecutionRecord] = []
        for event in self.journal.read_events():
            if event.event_type != self._EVENT_TYPE:
                raise ExecutionOutcomeError("execution journal contains an unsupported event type")
            records.append(self._record_from_event(event))
        return tuple(records)

    @staticmethod
    def _validate_binding(
        observation: ExecutionObservation,
        plan: CrossProjectPlan,
        verification: PlanVerificationReport,
    ) -> PlanCandidate:
        if verification.status is not PlanVerificationStatus.PASS:
            raise ExecutionOutcomeError("execution outcome requires PASS plan verification")
        if verification.plan_id != plan.plan_id or verification.recomputed_plan_id != plan.plan_id:
            raise ExecutionOutcomeError("execution outcome requires exact plan recomputation")
        if observation.plan_id != plan.plan_id:
            raise ExecutionOutcomeError("execution observation plan_id does not match plan")
        matches = [candidate for candidate in plan.candidates if candidate.rank == observation.candidate_rank]
        if len(matches) != 1:
            raise ExecutionOutcomeError("execution candidate rank is not uniquely present in plan")
        candidate = matches[0]
        if candidate.project is not observation.project:
            raise ExecutionOutcomeError("execution project does not match planned candidate")
        if candidate.action != observation.action:
            raise ExecutionOutcomeError("execution action does not match planned candidate")
        if candidate.evidence_hash != observation.candidate_evidence_hash:
            raise ExecutionOutcomeError("execution evidence hash does not match planned candidate")
        if observation.repository != _PROJECT_REPOSITORIES[observation.project]:
            raise ExecutionOutcomeError("execution repository does not match project binding")
        return candidate

    @staticmethod
    def _validate_result_semantics(observation: ExecutionObservation) -> None:
        checks = observation.ci_checks + observation.validator_checks
        if observation.outcome is ExecutionOutcomeStatus.SUCCESS:
            non_success = [check.name for check in checks if check.status is not EvidenceCheckStatus.SUCCESS]
            if non_success:
                raise ExecutionOutcomeError("successful execution requires every CI/validator check to pass")
        elif observation.outcome is ExecutionOutcomeStatus.FAILURE:
            if all(check.status is EvidenceCheckStatus.SUCCESS for check in checks):
                raise ExecutionOutcomeError("failure execution requires at least one failed or skipped check")
        else:
            if all(check.status is EvidenceCheckStatus.SUCCESS for check in checks):
                raise ExecutionOutcomeError("abstained execution requires unresolved check evidence")

    @staticmethod
    def _record_from_event(event: JournalEvent) -> ExecutionRecord:
        payload = event.payload
        if not isinstance(payload, Mapping):
            raise ExecutionOutcomeError("execution payload is not an object")
        required = {
            "schema_version",
            "plan_id",
            "project",
            "candidate_rank",
            "action",
            "candidate_evidence_hash",
            "repository",
            "branch",
            "commit_sha",
            "outcome",
            "ci_checks",
            "validator_checks",
            "notes",
            "plan_candidate_category",
        }
        if set(payload) != required or payload.get("schema_version") != EXECUTION_OUTCOME_SCHEMA_VERSION:
            raise ExecutionOutcomeError("execution payload schema is invalid")
        try:
            project = MusicProject(str(payload["project"]))
            outcome = ExecutionOutcomeStatus(str(payload["outcome"]))
        except ValueError as exc:
            raise ExecutionOutcomeError("execution enum value is invalid") from exc
        ci_checks = ExecutionOutcomeStore._parse_checks(payload.get("ci_checks"), "CI")
        validator_checks = ExecutionOutcomeStore._parse_checks(payload.get("validator_checks"), "validator")
        notes = payload.get("notes")
        if not isinstance(notes, list):
            raise ExecutionOutcomeError("execution notes are invalid")
        observation = ExecutionObservation(
            plan_id=str(payload["plan_id"]),
            project=project,
            candidate_rank=int(payload["candidate_rank"]),
            action=str(payload["action"]),
            candidate_evidence_hash=str(payload["candidate_evidence_hash"]),
            repository=str(payload["repository"]),
            branch=str(payload["branch"]),
            commit_sha=str(payload["commit_sha"]),
            outcome=outcome,
            ci_checks=ci_checks,
            validator_checks=validator_checks,
            notes=tuple(str(note) for note in notes),
        )
        ExecutionOutcomeStore._validate_result_semantics(observation)
        return ExecutionRecord(
            record_id=event.event_hash,
            sequence=event.sequence,
            timestamp=event.timestamp,
            plan_id=observation.plan_id,
            project=observation.project,
            candidate_rank=observation.candidate_rank,
            action=observation.action,
            candidate_evidence_hash=observation.candidate_evidence_hash,
            repository=observation.repository,
            branch=observation.branch,
            commit_sha=observation.commit_sha,
            outcome=observation.outcome,
            ci_checks=observation.ci_checks,
            validator_checks=observation.validator_checks,
            notes=observation.notes,
        )

    @staticmethod
    def _parse_checks(value: Any, label: str) -> tuple[ExecutionCheck, ...]:
        if not isinstance(value, list) or not value:
            raise ExecutionOutcomeError(f"execution {label} checks are invalid")
        checks: list[ExecutionCheck] = []
        for item in value:
            if not isinstance(item, Mapping) or set(item) != {"name", "status", "evidence_ref"}:
                raise ExecutionOutcomeError(f"execution {label} check schema is invalid")
            try:
                status = EvidenceCheckStatus(str(item["status"]))
            except ValueError as exc:
                raise ExecutionOutcomeError(f"execution {label} check status is invalid") from exc
            checks.append(
                ExecutionCheck(
                    name=str(item["name"]),
                    status=status,
                    evidence_ref=str(item["evidence_ref"]),
                )
            )
        return tuple(checks)
