from __future__ import annotations

import hashlib
import json
import os
from dataclasses import dataclass
from datetime import UTC, datetime
from enum import Enum
from pathlib import Path
from typing import Any

TASK_STATE_SCHEMA_VERSION = "1.0.0"
_ZERO_HASH = "0" * 64


class TaskStateError(RuntimeError):
    pass


class TaskStage(str, Enum):
    PREVIEWED = "PREVIEWED"
    BRANCH_CREATED = "BRANCH_CREATED"
    AGENT_RUNNING = "AGENT_RUNNING"
    AGENT_COMPLETED = "AGENT_COMPLETED"
    COMMIT_BOUND = "COMMIT_BOUND"
    CI_PENDING = "CI_PENDING"
    CI_REVIEWED = "CI_REVIEWED"
    VALIDATORS_REVIEWED = "VALIDATORS_REVIEWED"
    VERIFIED_SUCCESS = "VERIFIED_SUCCESS"
    FAILED = "FAILED"
    PR_OPENED = "PR_OPENED"


class TaskOutcome(str, Enum):
    WORKING = "WORKING"
    REVIEW_REQUIRED = "REVIEW_REQUIRED"
    VERIFIED_SUCCESS = "VERIFIED_SUCCESS"
    FAILED = "FAILED"


class ValidatorStatus(str, Enum):
    PASS = "PASS"
    FAIL = "FAIL"
    UNAVAILABLE = "UNAVAILABLE"


@dataclass(frozen=True, slots=True)
class ValidatorResult:
    name: str
    status: ValidatorStatus
    evidence_reference: str
    commit_sha: str
    message: str

    def __post_init__(self) -> None:
        if not self.name.strip():
            raise ValueError("validator name must not be empty")
        if not self.evidence_reference.strip():
            raise ValueError("validator evidence_reference must not be empty")
        if len(self.commit_sha) != 40 or any(char not in "0123456789abcdef" for char in self.commit_sha):
            raise ValueError("validator commit_sha must be a full lowercase Git SHA")
        if not self.message.strip():
            raise ValueError("validator message must not be empty")
        if len(self.message) > 500:
            raise ValueError("validator message exceeds configured limit")

    def as_dict(self) -> dict[str, str]:
        return {
            "name": self.name,
            "status": self.status.value,
            "evidence_reference": self.evidence_reference,
            "commit_sha": self.commit_sha,
            "message": self.message,
        }


@dataclass(frozen=True, slots=True)
class ProjectExecutionProfile:
    project: str
    required_workflows: tuple[str, ...] = ()
    validator_names: tuple[str, ...] = (
        "exact_commit_binding",
        "bounded_diff_evidence",
    )
    workflow_mode: str = "all_exact_sha_runs"

    def as_dict(self) -> dict[str, Any]:
        return {
            "project": self.project,
            "required_workflows": list(self.required_workflows),
            "validator_names": list(self.validator_names),
            "workflow_mode": self.workflow_mode,
        }


DEFAULT_PROJECT_PROFILES: dict[str, ProjectExecutionProfile] = {
    name: ProjectExecutionProfile(project=name)
    for name in (
        "score_restore",
        "musicxml_guitar_tab",
        "score_editor",
        "real_time_score_following",
    )
}

_ALLOWED_STAGE_TRANSITIONS: dict[TaskStage, frozenset[TaskStage]] = {
    TaskStage.PREVIEWED: frozenset({TaskStage.BRANCH_CREATED, TaskStage.FAILED}),
    TaskStage.BRANCH_CREATED: frozenset({TaskStage.AGENT_RUNNING, TaskStage.FAILED}),
    TaskStage.AGENT_RUNNING: frozenset({TaskStage.AGENT_COMPLETED, TaskStage.FAILED}),
    TaskStage.AGENT_COMPLETED: frozenset({TaskStage.COMMIT_BOUND, TaskStage.FAILED}),
    TaskStage.COMMIT_BOUND: frozenset({TaskStage.CI_PENDING, TaskStage.FAILED}),
    TaskStage.CI_PENDING: frozenset({TaskStage.CI_REVIEWED, TaskStage.FAILED}),
    TaskStage.CI_REVIEWED: frozenset({TaskStage.VALIDATORS_REVIEWED, TaskStage.FAILED}),
    TaskStage.VALIDATORS_REVIEWED: frozenset(
        {TaskStage.VERIFIED_SUCCESS, TaskStage.FAILED}
    ),
    TaskStage.VERIFIED_SUCCESS: frozenset({TaskStage.PR_OPENED}),
    TaskStage.FAILED: frozenset(),
    TaskStage.PR_OPENED: frozenset(),
}


class TaskEventStore:
    """Small append-only, hash-chained APP3/APP4/APP5 task evidence journal."""

    def __init__(self, path: str | Path) -> None:
        self.path = Path(path).expanduser()
        self._events = self._load()

    def append_stage(
        self,
        task_id: str,
        stage: TaskStage,
        payload: dict[str, Any],
        *,
        attempt: int = 1,
    ) -> dict[str, Any]:
        current = self.current_stage(task_id)
        if current is None:
            if stage is not TaskStage.PREVIEWED:
                raise TaskStateError("first task stage must be PREVIEWED")
        else:
            allowed = _ALLOWED_STAGE_TRANSITIONS[current]
            if stage not in allowed:
                raise TaskStateError(
                    f"invalid task stage transition: {current.value} -> {stage.value}"
                )
        return self._append(task_id, stage.value, payload, stage=stage, attempt=attempt)

    def append_evidence(
        self,
        task_id: str,
        event: str,
        payload: dict[str, Any],
        *,
        attempt: int = 1,
    ) -> dict[str, Any]:
        if self.current_stage(task_id) is None:
            raise TaskStateError("task evidence requires an existing PREVIEWED task")
        normalized = " ".join(event.split()).strip()
        if not normalized or len(normalized) > 80:
            raise ValueError("event name is invalid")
        return self._append(task_id, normalized, payload, stage=None, attempt=attempt)

    def current_stage(self, task_id: str) -> TaskStage | None:
        stage: TaskStage | None = None
        for item in self._events:
            if item["task_id"] != task_id:
                continue
            value = item.get("stage")
            if isinstance(value, str):
                stage = TaskStage(value)
        return stage

    def task_events(self, task_id: str) -> tuple[dict[str, Any], ...]:
        return tuple(dict(item) for item in self._events if item["task_id"] == task_id)

    def task_view(self, task_id: str) -> dict[str, Any]:
        events = self.task_events(task_id)
        if not events:
            raise TaskStateError("task does not exist in persistent state")
        view: dict[str, Any] = {
            "schema_version": TASK_STATE_SCHEMA_VERSION,
            "task_id": task_id,
            "stage": None,
            "outcome": TaskOutcome.WORKING.value,
            "attempt": 1,
            "preview": None,
            "execution": None,
            "commit": None,
            "ci": None,
            "validators": [],
            "pull_request": None,
            "review": None,
            "review_ack": None,
            "lineage": {"parent": None, "children": []},
            "pr_review": None,
            "pr_collaboration": None,
        }
        for item in events:
            payload = dict(item["payload"])
            stage = item.get("stage")
            if isinstance(stage, str):
                view["stage"] = stage
            view["attempt"] = item.get("attempt", 1)
            event = item["event"]
            if event == TaskStage.PREVIEWED.value:
                view["preview"] = payload
            elif event == TaskStage.AGENT_COMPLETED.value:
                view["execution"] = payload
            elif event == TaskStage.COMMIT_BOUND.value:
                view["commit"] = payload
            elif event == "CI_SNAPSHOT":
                view["ci"] = payload
            elif event == "VALIDATOR_SNAPSHOT":
                view["validators"] = list(payload.get("results", []))
            elif event == "OUTCOME":
                view["outcome"] = payload.get("outcome", view["outcome"])
            elif event == "REVIEW_SNAPSHOT":
                view["review"] = payload
            elif event == "REVIEW_ACKNOWLEDGED":
                view["review_ack"] = payload
            elif event == "LINEAGE_PARENT":
                view["lineage"]["parent"] = payload
            elif event == "LINEAGE_CHILD_CREATED":
                view["lineage"]["children"].append(payload)
            elif event == "PR_REVIEW_SNAPSHOT":
                view["pr_review"] = payload
            elif event == "PR_COLLABORATION_SNAPSHOT":
                view["pr_collaboration"] = payload
            elif event == TaskStage.VERIFIED_SUCCESS.value:
                view["outcome"] = TaskOutcome.VERIFIED_SUCCESS.value
            elif event == TaskStage.FAILED.value:
                view["outcome"] = TaskOutcome.FAILED.value
            elif event == TaskStage.PR_OPENED.value:
                view["pull_request"] = payload
        return view

    def has_task(self, task_id: str) -> bool:
        return any(item["task_id"] == task_id for item in self._events)

    def _append(
        self,
        task_id: str,
        event: str,
        payload: dict[str, Any],
        *,
        stage: TaskStage | None,
        attempt: int,
    ) -> dict[str, Any]:
        if not isinstance(payload, dict):
            raise TypeError("task event payload must be an object")
        if attempt < 1:
            raise ValueError("attempt must be >= 1")
        previous_hash = self._events[-1]["hash"] if self._events else _ZERO_HASH
        record: dict[str, Any] = {
            "schema_version": TASK_STATE_SCHEMA_VERSION,
            "sequence": len(self._events) + 1,
            "recorded_at": datetime.now(UTC).isoformat(),
            "task_id": task_id,
            "attempt": attempt,
            "event": event,
            "stage": stage.value if stage is not None else None,
            "payload": payload,
            "previous_hash": previous_hash,
        }
        record["hash"] = _record_hash(record)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        encoded = json.dumps(record, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        with self.path.open("a", encoding="utf-8") as handle:
            handle.write(encoded + "\n")
            handle.flush()
            os.fsync(handle.fileno())
        self._events.append(record)
        return dict(record)

    def _load(self) -> list[dict[str, Any]]:
        if not self.path.exists():
            return []
        events: list[dict[str, Any]] = []
        previous_hash = _ZERO_HASH
        with self.path.open("r", encoding="utf-8") as handle:
            for line_number, line in enumerate(handle, start=1):
                if not line.strip():
                    continue
                try:
                    item = json.loads(line)
                except json.JSONDecodeError as exc:
                    raise TaskStateError(
                        f"task state is not valid JSON at line {line_number}"
                    ) from exc
                if not isinstance(item, dict):
                    raise TaskStateError("task state record must be a JSON object")
                if item.get("schema_version") != TASK_STATE_SCHEMA_VERSION:
                    raise TaskStateError("task state schema version is unsupported")
                if item.get("sequence") != len(events) + 1:
                    raise TaskStateError("task state sequence is not append-only")
                if item.get("previous_hash") != previous_hash:
                    raise TaskStateError("task state hash chain is broken")
                actual_hash = item.get("hash")
                if not isinstance(actual_hash, str) or actual_hash != _record_hash(item):
                    raise TaskStateError("task state record hash does not match")
                task_id = item.get("task_id")
                payload = item.get("payload")
                if not isinstance(task_id, str) or not isinstance(payload, dict):
                    raise TaskStateError("task state record fields are invalid")
                stage = item.get("stage")
                if stage is not None:
                    try:
                        TaskStage(stage)
                    except ValueError as exc:
                        raise TaskStateError("task state contains an unknown stage") from exc
                previous_hash = actual_hash
                events.append(item)
        return events


def instruction_fingerprint(instruction: str) -> str:
    return hashlib.sha256(instruction.encode("utf-8")).hexdigest()


def default_task_state_path() -> Path:
    override = os.environ.get("ST_MUSIC_AGENT_TASK_STATE")
    if override:
        return Path(override).expanduser()
    return Path.home() / ".st-music-agent" / "task-events.jsonl"


def _record_hash(record: dict[str, Any]) -> str:
    material = {key: value for key, value in record.items() if key != "hash"}
    encoded = json.dumps(
        material,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()
