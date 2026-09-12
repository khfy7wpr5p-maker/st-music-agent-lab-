from __future__ import annotations

import hashlib
import json
import os
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from enum import Enum
from pathlib import Path
from typing import Any

from .app8_coordination import (
    CoordinationEvent,
    CoordinationEventType,
    CrossProjectPlan,
    ProjectCompletionReceipt,
    ProjectWorkItem,
    replay_coordination,
)
from .app8_supervision import (
    AgentRole,
    BudgetEnvelope,
    DependencyGraph,
    MutationClass,
    ObjectiveContract,
    SubtaskNode,
    SupervisorEvent,
    SupervisorEventType,
    replay_supervision,
)
from .contracts import TaskKind
from .music_evidence import MusicProject

APP8_GRAPH_STATE_SCHEMA_VERSION = "1.0.0"
APP8_GRAPH_STATE_POLICY_VERSION = "2026-09-12.app8e.v1"
_ZERO_HASH = "0" * 64
_GRAPH_ID = re.compile(r"^(?:supervision|coordination):[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}$")
_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_MAX_GRAPH_RECORDS = 100_000
_MAX_GRAPH_EVENTS = 10_000


class GraphStateError(RuntimeError):
    pass


class GraphKind(str, Enum):
    SUPERVISION = "supervision"
    COORDINATION = "coordination"


class GraphRecordType(str, Enum):
    GRAPH_REGISTERED = "graph_registered"
    GRAPH_EVENT = "graph_event"


def supervision_graph_id(graph: DependencyGraph) -> str:
    return f"supervision:{graph.objective.objective_id}"


def coordination_graph_id(plan: CrossProjectPlan) -> str:
    return f"coordination:{plan.plan_id}"


def default_graph_state_path() -> Path:
    override = os.environ.get("ST_MUSIC_AGENT_APP8_GRAPH_STATE")
    if override:
        return Path(override).expanduser()
    return Path.home() / ".st-music-agent" / "app8-graph-events.jsonl"


def _canonical_hash(value: Any) -> str:
    encoded = json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _record_hash(record: Mapping[str, Any]) -> str:
    material = {key: value for key, value in record.items() if key != "hash"}
    return _canonical_hash(material)


def _require_graph_id(value: str) -> None:
    if not _GRAPH_ID.fullmatch(value):
        raise GraphStateError("graph_id has an invalid format")


def _require_sha256(value: Any, label: str) -> str:
    if not isinstance(value, str) or not _SHA256.fullmatch(value):
        raise GraphStateError(f"{label} must be a lowercase SHA-256 digest")
    return value


@dataclass(frozen=True, slots=True)
class GraphSummary:
    graph_id: str
    kind: GraphKind
    plan_fingerprint: str
    disposition: str
    event_count: int
    anchor_sequence: int
    anchor_hash: str
    resume_available: bool
    execution_authorized: bool = False
    repository_mutation_authorized: bool = False
    pr_open_authorized: bool = False
    merge_authorized: bool = False
    production_actions_authorized: bool = False

    def as_dict(self) -> dict[str, Any]:
        return {
            "schema_version": APP8_GRAPH_STATE_SCHEMA_VERSION,
            "policy_version": APP8_GRAPH_STATE_POLICY_VERSION,
            "graph_id": self.graph_id,
            "kind": self.kind.value,
            "plan_fingerprint": self.plan_fingerprint,
            "disposition": self.disposition,
            "event_count": self.event_count,
            "anchor_sequence": self.anchor_sequence,
            "anchor_hash": self.anchor_hash,
            "resume_available": self.resume_available,
            "execution_authorized": False,
            "repository_mutation_authorized": False,
            "pr_open_authorized": False,
            "merge_authorized": False,
            "production_actions_authorized": False,
        }


class App8GraphStore:
    """Append-only hash-chained APP8 graph journal with deterministic replay on resume."""

    def __init__(self, path: str | Path | None = None) -> None:
        self.path = Path(path or default_graph_state_path()).expanduser()
        self._records = self._load()

    def register_supervision(self, graph: DependencyGraph) -> str:
        graph_id = supervision_graph_id(graph)
        self._register(
            graph_id,
            GraphKind.SUPERVISION,
            graph.graph_fingerprint,
            graph.as_dict(),
        )
        return graph_id

    def register_coordination(self, plan: CrossProjectPlan) -> str:
        graph_id = coordination_graph_id(plan)
        self._register(
            graph_id,
            GraphKind.COORDINATION,
            plan.plan_fingerprint,
            plan.as_dict(),
        )
        return graph_id

    def append_supervision_event(self, graph_id: str, event: SupervisorEvent) -> dict[str, Any]:
        metadata = self._metadata(graph_id)
        if metadata["kind"] is not GraphKind.SUPERVISION:
            raise GraphStateError("graph kind does not accept supervision events")
        self._require_next_graph_event_sequence(graph_id, event.sequence)
        return self._append_record(
            graph_id=graph_id,
            kind=GraphKind.SUPERVISION,
            record_type=GraphRecordType.GRAPH_EVENT,
            payload=event.as_dict(),
        )

    def append_coordination_event(
        self,
        graph_id: str,
        event: CoordinationEvent,
    ) -> dict[str, Any]:
        metadata = self._metadata(graph_id)
        if metadata["kind"] is not GraphKind.COORDINATION:
            raise GraphStateError("graph kind does not accept coordination events")
        self._require_next_graph_event_sequence(graph_id, event.sequence)
        return self._append_record(
            graph_id=graph_id,
            kind=GraphKind.COORDINATION,
            record_type=GraphRecordType.GRAPH_EVENT,
            payload=event.as_dict(),
        )

    def capture_supervision(
        self,
        graph: DependencyGraph,
        events: Sequence[SupervisorEvent],
    ) -> str:
        graph_id = self.register_supervision(graph)
        existing = self._graph_event_count(graph_id)
        if existing > len(events):
            raise GraphStateError("persistent graph contains more events than supplied supervision")
        persisted = self._graph_event_payloads(graph_id)
        for index, payload in enumerate(persisted):
            if payload.get("event_fingerprint") != events[index].event_fingerprint:
                raise GraphStateError("supplied supervision diverges from persistent graph history")
        for event in events[existing:]:
            self.append_supervision_event(graph_id, event)
        return graph_id

    def capture_coordination(
        self,
        plan: CrossProjectPlan,
        events: Sequence[CoordinationEvent],
    ) -> str:
        graph_id = self.register_coordination(plan)
        existing = self._graph_event_count(graph_id)
        if existing > len(events):
            raise GraphStateError("persistent graph contains more events than supplied coordination")
        persisted = self._graph_event_payloads(graph_id)
        for index, payload in enumerate(persisted):
            if payload.get("event_fingerprint") != events[index].event_fingerprint:
                raise GraphStateError("supplied coordination diverges from persistent graph history")
        for event in events[existing:]:
            self.append_coordination_event(graph_id, event)
        return graph_id

    def recent_graphs(self, limit: int = 20) -> list[dict[str, Any]]:
        if limit < 1 or limit > 100:
            raise ValueError("limit must be between 1 and 100")
        graph_ids: list[str] = []
        for record in reversed(self._records):
            graph_id = str(record["graph_id"])
            if graph_id not in graph_ids:
                graph_ids.append(graph_id)
            if len(graph_ids) >= limit:
                break
        return [self.graph_summary(graph_id).as_dict() for graph_id in graph_ids]

    def graph_summary(self, graph_id: str) -> GraphSummary:
        view = self.graph_view(graph_id)
        graph_records = self._graph_records(graph_id)
        anchor = graph_records[-1]
        disposition = str(view["replay"]["disposition"])
        return GraphSummary(
            graph_id=graph_id,
            kind=GraphKind(str(view["kind"])),
            plan_fingerprint=str(view["plan_fingerprint"]),
            disposition=disposition,
            event_count=int(view["event_count"]),
            anchor_sequence=int(anchor["sequence"]),
            anchor_hash=str(anchor["hash"]),
            resume_available=disposition in {"continue", "human_gate_required"},
        )

    def graph_view(self, graph_id: str) -> dict[str, Any]:
        metadata = self._metadata(graph_id)
        kind = metadata["kind"]
        plan_payload = metadata["plan_payload"]
        raw_events = self._graph_event_payloads(graph_id)
        if len(raw_events) > _MAX_GRAPH_EVENTS:
            raise GraphStateError("graph event count exceeds configured limit")

        if kind is GraphKind.SUPERVISION:
            graph = _parse_supervision_graph(plan_payload)
            events = tuple(_parse_supervisor_event(item) for item in raw_events)
            replay = replay_supervision(graph, events)
            replay_payload = replay.as_dict()
            plan_fingerprint = graph.graph_fingerprint
        else:
            plan = _parse_coordination_plan(plan_payload)
            events = tuple(_parse_coordination_event(item) for item in raw_events)
            replay = replay_coordination(plan, events)
            replay_payload = replay.as_dict()
            plan_fingerprint = plan.plan_fingerprint

        if plan_fingerprint != metadata["plan_fingerprint"]:
            raise GraphStateError("persistent plan fingerprint does not match reconstructed graph")
        graph_records = self._graph_records(graph_id)
        anchor = graph_records[-1]
        return {
            "schema_version": APP8_GRAPH_STATE_SCHEMA_VERSION,
            "policy_version": APP8_GRAPH_STATE_POLICY_VERSION,
            "graph_id": graph_id,
            "kind": kind.value,
            "plan_fingerprint": plan_fingerprint,
            "plan": plan_payload,
            "event_count": len(raw_events),
            "replay": replay_payload,
            "anchor_sequence": anchor["sequence"],
            "anchor_hash": anchor["hash"],
            "resume_scope": "deterministic_state_reconstruction_only",
            "execution_authorized": False,
            "repository_mutation_authorized": False,
            "pr_open_authorized": False,
            "merge_authorized": False,
            "production_actions_authorized": False,
        }

    def verify_graph(self, graph_id: str) -> dict[str, Any]:
        view = self.graph_view(graph_id)
        records = self._graph_records(graph_id)
        material = {
            "schema_version": APP8_GRAPH_STATE_SCHEMA_VERSION,
            "policy_version": APP8_GRAPH_STATE_POLICY_VERSION,
            "graph_id": graph_id,
            "kind": view["kind"],
            "plan_fingerprint": view["plan_fingerprint"],
            "record_hashes": [record["hash"] for record in records],
            "replay_fingerprint": view["replay"].get("replay_fingerprint"),
            "anchor_sequence": view["anchor_sequence"],
            "anchor_hash": view["anchor_hash"],
            "execution_authorized": False,
            "repository_mutation_authorized": False,
            "pr_open_authorized": False,
            "merge_authorized": False,
            "production_actions_authorized": False,
        }
        verification_sha256 = _canonical_hash(material)
        return {
            **material,
            "verified": True,
            "status": "VERIFIED",
            "verification_scope": "local_hash_chained_graph_journal_and_deterministic_replay",
            "verification_sha256": verification_sha256,
        }

    def _register(
        self,
        graph_id: str,
        kind: GraphKind,
        plan_fingerprint: str,
        plan_payload: Mapping[str, Any],
    ) -> None:
        _require_graph_id(graph_id)
        _require_sha256(plan_fingerprint, "plan_fingerprint")
        existing = [
            record
            for record in self._records
            if record["graph_id"] == graph_id
            and record["record_type"] == GraphRecordType.GRAPH_REGISTERED.value
        ]
        payload = {
            "plan_fingerprint": plan_fingerprint,
            "plan": dict(plan_payload),
        }
        if existing:
            if len(existing) != 1 or existing[0]["kind"] != kind.value:
                raise GraphStateError("persistent graph registration is inconsistent")
            if existing[0]["payload"] != payload:
                raise GraphStateError("graph_id is already registered with different plan material")
            return
        self._append_record(
            graph_id=graph_id,
            kind=kind,
            record_type=GraphRecordType.GRAPH_REGISTERED,
            payload=payload,
        )

    def _metadata(self, graph_id: str) -> dict[str, Any]:
        _require_graph_id(graph_id)
        registrations = [
            record
            for record in self._records
            if record["graph_id"] == graph_id
            and record["record_type"] == GraphRecordType.GRAPH_REGISTERED.value
        ]
        if len(registrations) != 1:
            raise GraphStateError("graph does not have exactly one persistent registration")
        record = registrations[0]
        payload = record["payload"]
        if not isinstance(payload, Mapping):
            raise GraphStateError("graph registration payload is invalid")
        plan_payload = payload.get("plan")
        if not isinstance(plan_payload, Mapping):
            raise GraphStateError("graph registration plan is invalid")
        return {
            "kind": GraphKind(str(record["kind"])),
            "plan_fingerprint": _require_sha256(
                payload.get("plan_fingerprint"),
                "stored plan_fingerprint",
            ),
            "plan_payload": dict(plan_payload),
        }

    def _graph_records(self, graph_id: str) -> tuple[dict[str, Any], ...]:
        _require_graph_id(graph_id)
        records = tuple(dict(item) for item in self._records if item["graph_id"] == graph_id)
        if not records:
            raise GraphStateError("graph does not exist in persistent state")
        return records

    def _graph_event_payloads(self, graph_id: str) -> tuple[dict[str, Any], ...]:
        return tuple(
            dict(record["payload"])
            for record in self._graph_records(graph_id)
            if record["record_type"] == GraphRecordType.GRAPH_EVENT.value
        )

    def _graph_event_count(self, graph_id: str) -> int:
        return len(self._graph_event_payloads(graph_id))

    def _require_next_graph_event_sequence(self, graph_id: str, event_sequence: int) -> None:
        expected = self._graph_event_count(graph_id) + 1
        if event_sequence != expected:
            raise GraphStateError(
                f"graph event sequence must be contiguous: expected {expected}, got {event_sequence}"
            )
        if expected > _MAX_GRAPH_EVENTS:
            raise GraphStateError("graph event count exceeds configured limit")

    def _append_record(
        self,
        *,
        graph_id: str,
        kind: GraphKind,
        record_type: GraphRecordType,
        payload: Mapping[str, Any],
    ) -> dict[str, Any]:
        if len(self._records) >= _MAX_GRAPH_RECORDS:
            raise GraphStateError("graph journal exceeds configured record limit")
        previous_hash = self._records[-1]["hash"] if self._records else _ZERO_HASH
        record: dict[str, Any] = {
            "schema_version": APP8_GRAPH_STATE_SCHEMA_VERSION,
            "sequence": len(self._records) + 1,
            "recorded_at": datetime.now(UTC).isoformat(),
            "graph_id": graph_id,
            "kind": kind.value,
            "record_type": record_type.value,
            "payload": dict(payload),
            "previous_hash": previous_hash,
        }
        record["hash"] = _record_hash(record)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        encoded = json.dumps(record, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        with self.path.open("a", encoding="utf-8") as handle:
            handle.write(encoded + "\n")
            handle.flush()
            os.fsync(handle.fileno())
        self._records.append(record)
        return dict(record)

    def _load(self) -> list[dict[str, Any]]:
        if not self.path.exists():
            return []
        records: list[dict[str, Any]] = []
        previous_hash = _ZERO_HASH
        registrations: dict[str, GraphKind] = {}
        graph_event_counts: dict[str, int] = {}
        with self.path.open("r", encoding="utf-8") as handle:
            for line_number, line in enumerate(handle, start=1):
                if not line.strip():
                    continue
                if len(records) >= _MAX_GRAPH_RECORDS:
                    raise GraphStateError("graph journal exceeds configured record limit")
                try:
                    item = json.loads(line)
                except json.JSONDecodeError as exc:
                    raise GraphStateError(
                        f"graph state is not valid JSON at line {line_number}"
                    ) from exc
                if not isinstance(item, dict):
                    raise GraphStateError("graph state record must be a JSON object")
                if item.get("schema_version") != APP8_GRAPH_STATE_SCHEMA_VERSION:
                    raise GraphStateError("graph state schema version is unsupported")
                if item.get("sequence") != len(records) + 1:
                    raise GraphStateError("graph state sequence is not append-only")
                if item.get("previous_hash") != previous_hash:
                    raise GraphStateError("graph state hash chain is broken")
                actual_hash = item.get("hash")
                if not isinstance(actual_hash, str) or actual_hash != _record_hash(item):
                    raise GraphStateError("graph state record hash does not match")
                graph_id = item.get("graph_id")
                kind_value = item.get("kind")
                record_type_value = item.get("record_type")
                payload = item.get("payload")
                if not isinstance(graph_id, str):
                    raise GraphStateError("graph state graph_id is invalid")
                _require_graph_id(graph_id)
                try:
                    kind = GraphKind(str(kind_value))
                    record_type = GraphRecordType(str(record_type_value))
                except ValueError as exc:
                    raise GraphStateError("graph state record enum value is invalid") from exc
                if not isinstance(payload, dict):
                    raise GraphStateError("graph state payload must be an object")
                if record_type is GraphRecordType.GRAPH_REGISTERED:
                    if graph_id in registrations:
                        raise GraphStateError("graph state contains duplicate registration")
                    registrations[graph_id] = kind
                    graph_event_counts[graph_id] = 0
                    _require_sha256(payload.get("plan_fingerprint"), "stored plan_fingerprint")
                    if not isinstance(payload.get("plan"), dict):
                        raise GraphStateError("graph registration plan must be an object")
                else:
                    if registrations.get(graph_id) is not kind:
                        raise GraphStateError("graph event appears before matching registration")
                    event_sequence = payload.get("sequence")
                    expected = graph_event_counts[graph_id] + 1
                    if event_sequence != expected:
                        raise GraphStateError("persistent graph event sequence is not contiguous")
                    graph_event_counts[graph_id] = expected
                    if expected > _MAX_GRAPH_EVENTS:
                        raise GraphStateError("persistent graph event count exceeds configured limit")
                previous_hash = actual_hash
                records.append(item)
        return records


def _parse_budget(value: Any) -> BudgetEnvelope:
    if not isinstance(value, Mapping):
        raise GraphStateError("budget projection is invalid")
    return BudgetEnvelope(
        max_elapsed_seconds=float(value["max_elapsed_seconds"]),
        max_model_turns=int(value["max_model_turns"]),
        max_tool_calls=int(value["max_tool_calls"]),
        max_model_facing_bytes=int(value["max_model_facing_bytes"]),
    )


def _parse_supervision_graph(payload: Mapping[str, Any]) -> DependencyGraph:
    objective_value = payload.get("objective")
    nodes_value = payload.get("nodes")
    if not isinstance(objective_value, Mapping) or not isinstance(nodes_value, list):
        raise GraphStateError("supervision plan projection is invalid")
    try:
        objective = ObjectiveContract(
            objective_id=str(objective_value["objective_id"]),
            instruction=str(objective_value["instruction"]),
            repositories=tuple(str(item) for item in objective_value["repositories"]),
            allowed_change_classes=tuple(
                MutationClass(str(item)) for item in objective_value["allowed_change_classes"]
            ),
            success_evidence=tuple(str(item) for item in objective_value["success_evidence"]),
            max_agent_count=int(objective_value["max_agent_count"]),
            total_budget=_parse_budget(objective_value["total_budget"]),
            human_gates=tuple(str(item) for item in objective_value["human_gates"]),
            stop_conditions=tuple(str(item) for item in objective_value["stop_conditions"]),
            forbidden_actions=tuple(str(item) for item in objective_value["forbidden_actions"]),
        )
        nodes = tuple(
            SubtaskNode(
                node_id=str(value["node_id"]),
                parent_objective_id=str(value["parent_objective_id"]),
                role=AgentRole(str(value["role"])),
                instruction=str(value["instruction"]),
                dependencies=tuple(str(item) for item in value["dependencies"]),
                repository=str(value["repository"]),
                branch_scope=str(value["branch_scope"]),
                input_evidence_refs=tuple(str(item) for item in value["input_evidence_refs"]),
                expected_output_evidence=tuple(
                    str(item) for item in value["expected_output_evidence"]
                ),
                budget=_parse_budget(value["budget"]),
                mutation_class=MutationClass(str(value["mutation_class"])),
                completion_criteria=tuple(str(item) for item in value["completion_criteria"]),
                abstention_criteria=tuple(str(item) for item in value["abstention_criteria"]),
                task_kind=TaskKind(str(value["task_kind"])),
                needs_tools=bool(value["needs_tools"]),
                needs_vision=bool(value["needs_vision"]),
                minimum_context_tokens=int(value["minimum_context_tokens"]),
            )
            for value in nodes_value
            if isinstance(value, Mapping)
        )
    except (KeyError, TypeError, ValueError) as exc:
        raise GraphStateError("supervision plan could not be reconstructed") from exc
    graph = DependencyGraph(objective=objective, nodes=nodes)
    supplied = payload.get("graph_fingerprint")
    if supplied != graph.graph_fingerprint:
        raise GraphStateError("supervision graph fingerprint changed during reconstruction")
    return graph


def _parse_supervisor_event(payload: Mapping[str, Any]) -> SupervisorEvent:
    try:
        reserved_value = payload.get("reserved_budget")
        reserved = _parse_budget(reserved_value) if reserved_value is not None else None
        event = SupervisorEvent(
            sequence=int(payload["sequence"]),
            event_type=SupervisorEventType(str(payload["event_type"])),
            node_id=str(payload["node_id"]),
            model_name=(str(payload["model_name"]) if payload.get("model_name") is not None else None),
            model_provider=(
                str(payload["model_provider"])
                if payload.get("model_provider") is not None
                else None
            ),
            evidence_refs=tuple(str(item) for item in payload.get("evidence_refs", [])),
            reserved_budget=reserved,
        )
    except (KeyError, TypeError, ValueError) as exc:
        raise GraphStateError("supervision event could not be reconstructed") from exc
    if payload.get("event_fingerprint") != event.event_fingerprint:
        raise GraphStateError("supervision event fingerprint changed during reconstruction")
    return event


def _parse_coordination_plan(payload: Mapping[str, Any]) -> CrossProjectPlan:
    values = payload.get("items")
    if not isinstance(values, list):
        raise GraphStateError("coordination plan projection is invalid")
    try:
        items = tuple(
            ProjectWorkItem(
                item_id=str(value["item_id"]),
                project=MusicProject(str(value["project"])),
                repository=str(value["repository"]),
                expected_base_sha=str(value["expected_base_sha"]),
                instruction=str(value["instruction"]),
                dependencies=tuple(str(item) for item in value["dependencies"]),
                required_upstream_evidence=tuple(
                    str(item) for item in value["required_upstream_evidence"]
                ),
                produces_evidence=tuple(str(item) for item in value["produces_evidence"]),
                mutation_class=MutationClass(str(value["mutation_class"])),
            )
            for value in values
            if isinstance(value, Mapping)
        )
        plan = CrossProjectPlan(plan_id=str(payload["plan_id"]), items=items)
    except (KeyError, TypeError, ValueError) as exc:
        raise GraphStateError("coordination plan could not be reconstructed") from exc
    if payload.get("plan_fingerprint") != plan.plan_fingerprint:
        raise GraphStateError("coordination plan fingerprint changed during reconstruction")
    return plan


def _parse_receipt(payload: Mapping[str, Any]) -> ProjectCompletionReceipt:
    try:
        receipt = ProjectCompletionReceipt(
            item_id=str(payload["item_id"]),
            project=MusicProject(str(payload["project"])),
            repository=str(payload["repository"]),
            base_sha=str(payload["base_sha"]),
            head_sha=str(payload["head_sha"]),
            artifact_sha256=str(payload["artifact_sha256"]),
            verification_sha256=str(payload["verification_sha256"]),
            produced_evidence=tuple(str(item) for item in payload["produced_evidence"]),
            source=str(payload["source"]),
        )
    except (KeyError, TypeError, ValueError) as exc:
        raise GraphStateError("coordination receipt could not be reconstructed") from exc
    if payload.get("receipt_fingerprint") != receipt.receipt_fingerprint:
        raise GraphStateError("coordination receipt fingerprint changed during reconstruction")
    return receipt


def _parse_coordination_event(payload: Mapping[str, Any]) -> CoordinationEvent:
    receipt_value = payload.get("receipt")
    if receipt_value is not None and not isinstance(receipt_value, Mapping):
        raise GraphStateError("coordination event receipt projection is invalid")
    try:
        event = CoordinationEvent(
            sequence=int(payload["sequence"]),
            event_type=CoordinationEventType(str(payload["event_type"])),
            item_id=str(payload["item_id"]),
            receipt=_parse_receipt(receipt_value) if isinstance(receipt_value, Mapping) else None,
            evidence_ref=(
                str(payload["evidence_ref"])
                if payload.get("evidence_ref") is not None
                else None
            ),
        )
    except (KeyError, TypeError, ValueError) as exc:
        raise GraphStateError("coordination event could not be reconstructed") from exc
    if payload.get("event_fingerprint") != event.event_fingerprint:
        raise GraphStateError("coordination event fingerprint changed during reconstruction")
    return event
