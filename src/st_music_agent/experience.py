from __future__ import annotations

import re
from collections import defaultdict
from collections.abc import Mapping
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Any

from .agent_tools import ToolRegistry
from .journal import JournalEvent, RunJournal
from .music_evidence import MusicProject
from .portfolio_planning import PlanVerificationReport, PlanVerificationStatus

EXPERIENCE_SCHEMA_VERSION = "1.0.0"
_PLAYBOOK_KEY = re.compile(r"^[a-z0-9][a-z0-9_.-]{0,127}$")


class ExperienceError(RuntimeError):
    pass


class ExperienceOutcome(str, Enum):
    SUCCESS = "success"
    FAILURE = "failure"
    ABSTAINED = "abstained"


class LearningDisposition(str, Enum):
    PREFER = "prefer"
    OBSERVE = "observe"
    REVIEW = "review"


@dataclass(frozen=True, slots=True)
class ExperienceObservation:
    plan_id: str
    project: MusicProject
    action: str
    playbook_key: str
    outcome: ExperienceOutcome
    evidence_refs: tuple[str, ...]

    def __post_init__(self) -> None:
        if not self.plan_id.strip():
            raise ValueError("plan_id must not be empty")
        if not self.action.strip():
            raise ValueError("action must not be empty")
        if not _PLAYBOOK_KEY.fullmatch(self.playbook_key):
            raise ValueError("playbook_key has an invalid format")
        if not self.evidence_refs:
            raise ValueError("at least one evidence reference is required")
        if any(not ref.strip() for ref in self.evidence_refs):
            raise ValueError("evidence references must not be empty")


@dataclass(frozen=True, slots=True)
class ExperienceRecord:
    record_id: str
    sequence: int
    timestamp: str
    plan_id: str
    project: MusicProject
    action: str
    playbook_key: str
    outcome: ExperienceOutcome
    evidence_refs: tuple[str, ...]

    def as_dict(self) -> dict[str, Any]:
        return {
            "schema_version": EXPERIENCE_SCHEMA_VERSION,
            "record_id": self.record_id,
            "sequence": self.sequence,
            "timestamp": self.timestamp,
            "plan_id": self.plan_id,
            "project": self.project.value,
            "action": self.action,
            "playbook_key": self.playbook_key,
            "outcome": self.outcome.value,
            "evidence_refs": list(self.evidence_refs),
        }


@dataclass(frozen=True, slots=True)
class LearningRecommendation:
    playbook_key: str
    project: MusicProject
    disposition: LearningDisposition
    successful: int
    failed: int
    abstained: int
    evaluated_attempts: int
    success_rate: float | None
    auto_apply: bool = False

    def as_dict(self) -> dict[str, Any]:
        return {
            "playbook_key": self.playbook_key,
            "project": self.project.value,
            "disposition": self.disposition.value,
            "successful": self.successful,
            "failed": self.failed,
            "abstained": self.abstained,
            "evaluated_attempts": self.evaluated_attempts,
            "success_rate": self.success_rate,
            "auto_apply": self.auto_apply,
        }


class ExperienceStore:
    """Host-write-only verified experience store backed by a hash-chained JSONL journal.

    There is intentionally no model-callable record operation. A host must provide a PASS
    verification report for the exact plan before an observation can be persisted.
    """

    _RUN_ID = "st-music-agent-experience-v1"
    _EVENT_TYPE = "verified_experience"

    def __init__(self, path: Path) -> None:
        self.journal = RunJournal(path, self._RUN_ID)

    def record_verified(
        self,
        observation: ExperienceObservation,
        verification: PlanVerificationReport,
    ) -> ExperienceRecord:
        if verification.status is not PlanVerificationStatus.PASS:
            raise ExperienceError("experience cannot be recorded from a failed verification")
        if verification.plan_id != observation.plan_id:
            raise ExperienceError("experience plan_id does not match verification")
        if verification.recomputed_plan_id != observation.plan_id:
            raise ExperienceError("experience requires exact deterministic plan recomputation")

        payload = {
            "schema_version": EXPERIENCE_SCHEMA_VERSION,
            "plan_id": observation.plan_id,
            "project": observation.project.value,
            "action": observation.action,
            "playbook_key": observation.playbook_key,
            "outcome": observation.outcome.value,
            "evidence_refs": list(observation.evidence_refs),
        }
        event = self.journal.append(self._EVENT_TYPE, payload)
        return self._record_from_event(event)

    def read_records(self) -> tuple[ExperienceRecord, ...]:
        records: list[ExperienceRecord] = []
        for event in self.journal.read_events():
            if event.event_type != self._EVENT_TYPE:
                raise ExperienceError("experience journal contains an unsupported event type")
            records.append(self._record_from_event(event))
        return tuple(records)

    @staticmethod
    def _record_from_event(event: JournalEvent) -> ExperienceRecord:
        payload = event.payload
        if not isinstance(payload, Mapping):
            raise ExperienceError("experience payload is not an object")
        required = {
            "schema_version",
            "plan_id",
            "project",
            "action",
            "playbook_key",
            "outcome",
            "evidence_refs",
        }
        if set(payload) != required:
            raise ExperienceError("experience payload schema is invalid")
        if payload.get("schema_version") != EXPERIENCE_SCHEMA_VERSION:
            raise ExperienceError("experience schema version is unsupported")
        evidence_refs = payload.get("evidence_refs")
        if not isinstance(evidence_refs, list) or not evidence_refs:
            raise ExperienceError("experience evidence references are invalid")
        try:
            project = MusicProject(str(payload["project"]))
            outcome = ExperienceOutcome(str(payload["outcome"]))
        except ValueError as exc:
            raise ExperienceError("experience enum value is invalid") from exc
        observation = ExperienceObservation(
            plan_id=str(payload["plan_id"]),
            project=project,
            action=str(payload["action"]),
            playbook_key=str(payload["playbook_key"]),
            outcome=outcome,
            evidence_refs=tuple(str(value) for value in evidence_refs),
        )
        return ExperienceRecord(
            record_id=event.event_hash,
            sequence=event.sequence,
            timestamp=event.timestamp,
            plan_id=observation.plan_id,
            project=observation.project,
            action=observation.action,
            playbook_key=observation.playbook_key,
            outcome=observation.outcome,
            evidence_refs=observation.evidence_refs,
        )


class ExperienceAdvisor:
    """Produces non-binding playbook advice from verified historical outcomes."""

    def summarize(
        self,
        records: tuple[ExperienceRecord, ...],
        *,
        project: MusicProject | None = None,
        playbook_key: str | None = None,
    ) -> tuple[LearningRecommendation, ...]:
        if playbook_key is not None and not _PLAYBOOK_KEY.fullmatch(playbook_key):
            raise ValueError("playbook_key has an invalid format")

        grouped: dict[tuple[MusicProject, str], list[ExperienceRecord]] = defaultdict(list)
        for record in records:
            if project is not None and record.project is not project:
                continue
            if playbook_key is not None and record.playbook_key != playbook_key:
                continue
            grouped[(record.project, record.playbook_key)].append(record)

        recommendations = [
            self._recommend(group_project, group_key, group_records)
            for (group_project, group_key), group_records in grouped.items()
        ]
        recommendations.sort(key=lambda item: (item.project.value, item.playbook_key))
        return tuple(recommendations)

    @staticmethod
    def _recommend(
        project: MusicProject,
        playbook_key: str,
        records: list[ExperienceRecord],
    ) -> LearningRecommendation:
        successful = sum(record.outcome is ExperienceOutcome.SUCCESS for record in records)
        failed = sum(record.outcome is ExperienceOutcome.FAILURE for record in records)
        abstained = sum(record.outcome is ExperienceOutcome.ABSTAINED for record in records)
        evaluated = successful + failed
        success_rate = successful / evaluated if evaluated else None

        if evaluated < 3 or success_rate is None:
            disposition = LearningDisposition.OBSERVE
        elif success_rate >= 0.8:
            disposition = LearningDisposition.PREFER
        elif success_rate <= 0.5:
            disposition = LearningDisposition.REVIEW
        else:
            disposition = LearningDisposition.OBSERVE

        return LearningRecommendation(
            playbook_key=playbook_key,
            project=project,
            disposition=disposition,
            successful=successful,
            failed=failed,
            abstained=abstained,
            evaluated_attempts=evaluated,
            success_rate=success_rate,
            auto_apply=False,
        )


class ExperienceReadToolset:
    """Read-only model surface for verified experience summaries."""

    def __init__(
        self,
        store: ExperienceStore,
        advisor: ExperienceAdvisor | None = None,
    ) -> None:
        self.store = store
        self.advisor = advisor or ExperienceAdvisor()

    def register_into(self, registry: ToolRegistry) -> None:
        registry.register(
            "learning.experience.summary",
            self._summary,
            description=(
                "Summarize verified historical playbook outcomes. Recommendations are advisory "
                "and never auto-change policy, privileges, models or code."
            ),
            parameters={
                "type": "object",
                "properties": {
                    "project": {"type": "string"},
                    "playbook_key": {"type": "string"},
                },
                "additionalProperties": False,
            },
        )

    def _summary(self, arguments: Mapping[str, Any]) -> Mapping[str, Any]:
        extras = set(arguments) - {"project", "playbook_key"}
        if extras:
            raise ValueError("tool arguments contain unsupported fields")
        raw_project = arguments.get("project")
        project = None
        if raw_project is not None:
            if not isinstance(raw_project, str):
                raise TypeError("project must be text when provided")
            try:
                project = MusicProject(raw_project)
            except ValueError as exc:
                raise ValueError("project is not a known music project") from exc
        playbook_key = arguments.get("playbook_key")
        if playbook_key is not None and not isinstance(playbook_key, str):
            raise TypeError("playbook_key must be text when provided")

        recommendations = self.advisor.summarize(
            self.store.read_records(),
            project=project,
            playbook_key=playbook_key,
        )
        return {
            "schema_version": EXPERIENCE_SCHEMA_VERSION,
            "auto_apply": False,
            "recommendations": [item.as_dict() for item in recommendations],
        }
