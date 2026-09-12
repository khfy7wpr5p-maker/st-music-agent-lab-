from __future__ import annotations

import hashlib
import json
from collections import Counter
from collections.abc import Mapping
from typing import Any

from .app6_task_execution import APP6_EVIDENCE_SCHEMA_VERSION, App6TaskService
from .task_execution import TaskExecutionError
from .task_state import TaskOutcome, TaskStage

APP7_VERIFICATION_SCHEMA_VERSION = "1.0.0"

_STAGE_TRANSITIONS: dict[TaskStage, frozenset[TaskStage]] = {
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


class App7TaskService(App6TaskService):
    """APP7 adds deterministic audit verification/replay without widening mutation authority."""

    def verify_current_audit(self, task_id: str) -> dict[str, Any]:
        bundle = self.audit_bundle(task_id)
        export = verify_audit_export(bundle)
        replay = self.replay_task(task_id)
        events = self.store.task_events(task_id)
        if not events:
            raise TaskExecutionError("task has no journal events")
        latest = events[-1]
        journal = bundle.get("journal")
        reasons = list(export["reasons"])
        if not isinstance(journal, Mapping):
            reasons.append("audit journal projection is missing")
        else:
            if journal.get("anchor_sequence") != latest.get("sequence"):
                reasons.append("audit anchor sequence does not match the local journal")
            if journal.get("anchor_hash") != latest.get("hash"):
                reasons.append("audit anchor hash does not match the local journal")
        if bundle.get("stage") != replay["derived_stage"]:
            reasons.append("audit stage does not match deterministic journal replay")
        if bundle.get("outcome") != replay["derived_outcome"]:
            reasons.append("audit outcome does not match deterministic journal replay")

        verified = export["verified"] is True and not reasons
        result = {
            "schema_version": APP7_VERIFICATION_SCHEMA_VERSION,
            "task_id": task_id,
            "verified": verified,
            "status": "VERIFIED" if verified else "INVALID",
            "verification_scope": "local_hash_chained_journal_and_export",
            "audit_sha256": bundle.get("audit_sha256"),
            "journal_anchor_sequence": latest.get("sequence"),
            "journal_anchor_hash": latest.get("hash"),
            "export_verification": export,
            "replay": replay,
            "reasons": reasons,
            "merge_authorized": False,
            "production_actions_authorized": False,
        }
        result["verification_sha256"] = _digest_payload(result)
        return result

    def replay_task(self, task_id: str) -> dict[str, Any]:
        events = self.store.task_events(task_id)
        if not events:
            raise TaskExecutionError("task has no journal events to replay")
        current_stage: TaskStage | None = None
        outcome = TaskOutcome.WORKING.value
        violations: list[str] = []
        event_counts: Counter[str] = Counter()
        headers: list[dict[str, Any]] = []

        for item in events:
            event = item.get("event")
            if isinstance(event, str):
                event_counts[event] += 1
            stage_value = item.get("stage")
            if isinstance(stage_value, str):
                try:
                    stage = TaskStage(stage_value)
                except ValueError:
                    violations.append(f"unknown stage {stage_value!r}")
                else:
                    if current_stage is None:
                        if stage is not TaskStage.PREVIEWED:
                            violations.append("first replayed stage is not PREVIEWED")
                    elif stage not in _STAGE_TRANSITIONS[current_stage]:
                        violations.append(
                            f"invalid replay transition {current_stage.value} -> {stage.value}"
                        )
                    current_stage = stage
                    if stage is TaskStage.VERIFIED_SUCCESS:
                        outcome = TaskOutcome.VERIFIED_SUCCESS.value
                    elif stage is TaskStage.FAILED:
                        outcome = TaskOutcome.FAILED.value
            payload = item.get("payload")
            if event == "OUTCOME" and isinstance(payload, Mapping):
                candidate = payload.get("outcome")
                if candidate in {value.value for value in TaskOutcome}:
                    outcome = str(candidate)
            headers.append(
                {
                    "sequence": item.get("sequence"),
                    "event": event,
                    "stage": stage_value,
                    "hash": item.get("hash"),
                    "previous_hash": item.get("previous_hash"),
                }
            )

        view = self.store.task_view(task_id)
        derived_stage = current_stage.value if current_stage is not None else None
        if view.get("stage") != derived_stage:
            violations.append("replayed stage differs from TaskEventStore projection")
        if view.get("outcome") != outcome:
            violations.append("replayed outcome differs from TaskEventStore projection")

        replay_material = {
            "task_id": task_id,
            "derived_stage": derived_stage,
            "derived_outcome": outcome,
            "headers": headers,
        }
        return {
            "schema_version": APP7_VERIFICATION_SCHEMA_VERSION,
            "task_id": task_id,
            "verified": not violations,
            "derived_stage": derived_stage,
            "derived_outcome": outcome,
            "event_count": len(events),
            "event_counts": dict(sorted(event_counts.items())),
            "anchor_sequence": events[-1].get("sequence"),
            "anchor_hash": events[-1].get("hash"),
            "violations": violations,
            "replay_sha256": _digest_payload(replay_material),
            "merge_authorized": False,
            "production_actions_authorized": False,
        }


def verify_audit_export(bundle: Mapping[str, Any]) -> dict[str, Any]:
    """Verify APP6 audit digest/structure only; this does not authenticate the source journal."""
    reasons: list[str] = []
    if bundle.get("schema_version") != APP6_EVIDENCE_SCHEMA_VERSION:
        reasons.append("unsupported audit schema_version")
    supplied_digest = bundle.get("audit_sha256")
    if not _sha256(supplied_digest):
        reasons.append("audit_sha256 is missing or invalid")
        calculated = None
    else:
        material = dict(bundle)
        material.pop("audit_sha256", None)
        calculated = _digest_payload(material)
        if calculated != supplied_digest:
            reasons.append("audit_sha256 does not match audit content")
    if bundle.get("merge_authorized") is not False:
        reasons.append("audit must not authorize merge")
    if bundle.get("production_actions_authorized") is not False:
        reasons.append("audit must not authorize production actions")

    journal = bundle.get("journal")
    if not isinstance(journal, Mapping):
        reasons.append("journal projection is missing")
    else:
        events = journal.get("events")
        if not isinstance(events, list):
            reasons.append("journal events projection is invalid")
        else:
            if journal.get("exported_event_count") != len(events):
                reasons.append("journal exported_event_count is inconsistent")
            event_count = journal.get("event_count")
            if not isinstance(event_count, int) or isinstance(event_count, bool):
                reasons.append("journal event_count is invalid")
            elif event_count < len(events):
                reasons.append("journal event_count is smaller than exported events")
            if events:
                last = events[-1]
                if not isinstance(last, Mapping):
                    reasons.append("last journal event header is invalid")
                else:
                    if last.get("sequence") != journal.get("anchor_sequence"):
                        reasons.append("journal anchor_sequence does not match last exported event")
                    if last.get("hash") != journal.get("anchor_hash"):
                        reasons.append("journal anchor_hash does not match last exported event")
        if not _sha256(journal.get("anchor_hash")):
            reasons.append("journal anchor_hash is invalid")
        anchor_sequence = journal.get("anchor_sequence")
        if not isinstance(anchor_sequence, int) or isinstance(anchor_sequence, bool):
            reasons.append("journal anchor_sequence is invalid")

    return {
        "schema_version": APP7_VERIFICATION_SCHEMA_VERSION,
        "verified": not reasons,
        "status": "STRUCTURE_VERIFIED" if not reasons else "INVALID",
        "verification_scope": "export_digest_and_structure_only",
        "source_journal_authenticated": False,
        "supplied_audit_sha256": supplied_digest,
        "calculated_audit_sha256": calculated,
        "reasons": reasons,
    }


def _digest_payload(payload: Mapping[str, Any]) -> str:
    encoded = json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _sha256(value: Any) -> bool:
    return (
        isinstance(value, str)
        and len(value) == 64
        and all(char in "0123456789abcdef" for char in value)
    )
