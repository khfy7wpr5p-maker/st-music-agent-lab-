from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Iterable, Mapping

from .contracts import AgentTask, TaskKind
from .router import ModelRouter

APP8_SUPERVISION_SCHEMA_VERSION = "1.0.0"
APP8_SUPERVISION_POLICY_VERSION = "2026-09-12.app8a.v1"

_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}$")
_REPOSITORY = re.compile(r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$")
_BRANCH = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._/-]{0,255}$")
_PROTECTED_BRANCHES = frozenset({"main", "master"})
_REQUIRED_FORBIDDEN_ACTIONS = frozenset(
    {
        "protected_branch_write",
        "pr_approval",
        "merge",
        "auto_merge",
        "review_thread_mutation",
        "release",
        "deployment",
        "training_execution",
        "production_model_activation",
        "canonicalization",
        "rollback_execution",
        "privilege_self_modification",
        "secret_mutation",
    }
)


class SupervisorContractError(ValueError):
    pass


class SupervisorGraphError(ValueError):
    pass


class SupervisorStateError(RuntimeError):
    pass


class SupervisorBudgetError(RuntimeError):
    pass


class AgentRole(str, Enum):
    EVIDENCE = "evidence"
    IMPLEMENTATION = "implementation"
    VALIDATION = "validation"
    CRITIC = "critic"


class MutationClass(str, Enum):
    READ_ONLY = "read_only"
    REVERSIBLE_FEATURE_BRANCH = "reversible_feature_branch"
    HUMAN_GATED = "human_gated"


class NodeState(str, Enum):
    PENDING = "pending"
    READY = "ready"
    RUNNING = "running"
    PASS = "pass"
    FAIL = "fail"
    ABSTAIN = "abstain"
    REVIEW_REQUIRED = "review_required"
    BLOCKED = "blocked"


class NodeOutcome(str, Enum):
    PASS = "pass"
    FAIL = "fail"
    ABSTAIN = "abstain"
    REVIEW_REQUIRED = "review_required"


class SupervisorDisposition(str, Enum):
    CONTINUE = "continue"
    COMPLETE = "complete"
    FAIL = "fail"
    ABSTAIN = "abstain"
    REVIEW_REQUIRED = "review_required"
    HUMAN_GATE_REQUIRED = "human_gate_required"
    BLOCKED = "blocked"


class SupervisorEventType(str, Enum):
    NODE_SCHEDULED = "node_scheduled"
    NODE_COMPLETED = "node_completed"
    NODE_FAILED = "node_failed"
    NODE_ABSTAINED = "node_abstained"
    NODE_REVIEW_REQUIRED = "node_review_required"


def _canonical_hash(value: Any) -> str:
    encoded = json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _require_nonempty(values: tuple[str, ...], name: str) -> None:
    if not values or any(not value.strip() for value in values):
        raise SupervisorContractError(f"{name} must contain non-empty values")


@dataclass(frozen=True, slots=True)
class BudgetEnvelope:
    max_elapsed_seconds: float
    max_model_turns: int
    max_tool_calls: int
    max_model_facing_bytes: int

    def __post_init__(self) -> None:
        if self.max_elapsed_seconds <= 0:
            raise SupervisorContractError("max_elapsed_seconds must be positive")
        if self.max_model_turns < 1:
            raise SupervisorContractError("max_model_turns must be >= 1")
        if self.max_tool_calls < 0:
            raise SupervisorContractError("max_tool_calls must be >= 0")
        if self.max_model_facing_bytes < 1024:
            raise SupervisorContractError("max_model_facing_bytes must be >= 1024")

    def as_dict(self) -> dict[str, int | float]:
        return {
            "max_elapsed_seconds": self.max_elapsed_seconds,
            "max_model_turns": self.max_model_turns,
            "max_tool_calls": self.max_tool_calls,
            "max_model_facing_bytes": self.max_model_facing_bytes,
        }


@dataclass(frozen=True, slots=True)
class BudgetReservation:
    elapsed_seconds: float = 0.0
    model_turns: int = 0
    tool_calls: int = 0
    model_facing_bytes: int = 0

    def __post_init__(self) -> None:
        if self.elapsed_seconds < 0:
            raise SupervisorContractError("reserved elapsed_seconds must be >= 0")
        if self.model_turns < 0:
            raise SupervisorContractError("reserved model_turns must be >= 0")
        if self.tool_calls < 0:
            raise SupervisorContractError("reserved tool_calls must be >= 0")
        if self.model_facing_bytes < 0:
            raise SupervisorContractError("reserved model_facing_bytes must be >= 0")

    @classmethod
    def from_envelope(cls, value: BudgetEnvelope) -> BudgetReservation:
        return cls(
            elapsed_seconds=value.max_elapsed_seconds,
            model_turns=value.max_model_turns,
            tool_calls=value.max_tool_calls,
            model_facing_bytes=value.max_model_facing_bytes,
        )

    def plus(self, other: BudgetReservation) -> BudgetReservation:
        return BudgetReservation(
            elapsed_seconds=self.elapsed_seconds + other.elapsed_seconds,
            model_turns=self.model_turns + other.model_turns,
            tool_calls=self.tool_calls + other.tool_calls,
            model_facing_bytes=self.model_facing_bytes + other.model_facing_bytes,
        )

    def fits_within(self, limit: BudgetEnvelope) -> bool:
        return (
            self.elapsed_seconds <= limit.max_elapsed_seconds
            and self.model_turns <= limit.max_model_turns
            and self.tool_calls <= limit.max_tool_calls
            and self.model_facing_bytes <= limit.max_model_facing_bytes
        )

    def as_dict(self) -> dict[str, int | float]:
        return {
            "elapsed_seconds": self.elapsed_seconds,
            "model_turns": self.model_turns,
            "tool_calls": self.tool_calls,
            "model_facing_bytes": self.model_facing_bytes,
        }


@dataclass(frozen=True, slots=True)
class RoleCapability:
    role: AgentRole
    mutation_classes: frozenset[MutationClass]
    task_kinds: frozenset[TaskKind]


ROLE_CAPABILITIES: Mapping[AgentRole, RoleCapability] = {
    AgentRole.EVIDENCE: RoleCapability(
        role=AgentRole.EVIDENCE,
        mutation_classes=frozenset(
            {MutationClass.READ_ONLY, MutationClass.HUMAN_GATED}
        ),
        task_kinds=frozenset(
            {
                TaskKind.RESEARCH,
                TaskKind.PLANNING,
                TaskKind.GENERAL,
                TaskKind.SCORE_VISION,
            }
        ),
    ),
    AgentRole.IMPLEMENTATION: RoleCapability(
        role=AgentRole.IMPLEMENTATION,
        mutation_classes=frozenset(
            {
                MutationClass.READ_ONLY,
                MutationClass.REVERSIBLE_FEATURE_BRANCH,
                MutationClass.HUMAN_GATED,
            }
        ),
        task_kinds=frozenset({TaskKind.CODE, TaskKind.GENERAL}),
    ),
    AgentRole.VALIDATION: RoleCapability(
        role=AgentRole.VALIDATION,
        mutation_classes=frozenset(
            {MutationClass.READ_ONLY, MutationClass.HUMAN_GATED}
        ),
        task_kinds=frozenset(
            {TaskKind.CODE, TaskKind.RESEARCH, TaskKind.GENERAL, TaskKind.SCORE_VISION}
        ),
    ),
    AgentRole.CRITIC: RoleCapability(
        role=AgentRole.CRITIC,
        mutation_classes=frozenset(
            {MutationClass.READ_ONLY, MutationClass.HUMAN_GATED}
        ),
        task_kinds=frozenset(
            {TaskKind.CODE, TaskKind.RESEARCH, TaskKind.PLANNING, TaskKind.GENERAL}
        ),
    ),
}


@dataclass(frozen=True, slots=True)
class ObjectiveContract:
    objective_id: str
    instruction: str
    repositories: tuple[str, ...]
    allowed_change_classes: tuple[MutationClass, ...]
    success_evidence: tuple[str, ...]
    max_agent_count: int
    total_budget: BudgetEnvelope
    human_gates: tuple[str, ...]
    stop_conditions: tuple[str, ...]
    forbidden_actions: tuple[str, ...] = ()
    objective_fingerprint: str = field(init=False)

    def __post_init__(self) -> None:
        if not _ID.fullmatch(self.objective_id):
            raise SupervisorContractError("objective_id has an invalid format")
        if not self.instruction.strip():
            raise SupervisorContractError("objective instruction must not be empty")
        _require_nonempty(self.repositories, "repositories")
        if len(set(self.repositories)) != len(self.repositories):
            raise SupervisorContractError("repositories must be unique")
        if any(not _REPOSITORY.fullmatch(repo) for repo in self.repositories):
            raise SupervisorContractError("repository must use owner/name form")
        if not self.allowed_change_classes:
            raise SupervisorContractError("allowed_change_classes must not be empty")
        if len(set(self.allowed_change_classes)) != len(self.allowed_change_classes):
            raise SupervisorContractError("allowed_change_classes must be unique")
        _require_nonempty(self.success_evidence, "success_evidence")
        if self.max_agent_count < 1 or self.max_agent_count > len(AgentRole):
            raise SupervisorContractError(
                f"max_agent_count must be between 1 and {len(AgentRole)}"
            )
        _require_nonempty(self.human_gates, "human_gates")
        _require_nonempty(self.stop_conditions, "stop_conditions")
        forbidden = tuple(sorted(set(self.forbidden_actions) | _REQUIRED_FORBIDDEN_ACTIONS))
        if any(not action.strip() for action in forbidden):
            raise SupervisorContractError("forbidden_actions must not contain empty values")
        object.__setattr__(self, "forbidden_actions", forbidden)
        object.__setattr__(self, "objective_fingerprint", _canonical_hash(self._base_dict()))

    def _base_dict(self) -> dict[str, Any]:
        return {
            "schema_version": APP8_SUPERVISION_SCHEMA_VERSION,
            "policy_version": APP8_SUPERVISION_POLICY_VERSION,
            "objective_id": self.objective_id,
            "instruction": self.instruction,
            "repositories": list(self.repositories),
            "allowed_change_classes": [item.value for item in self.allowed_change_classes],
            "success_evidence": list(self.success_evidence),
            "max_agent_count": self.max_agent_count,
            "total_budget": self.total_budget.as_dict(),
            "human_gates": list(self.human_gates),
            "stop_conditions": list(self.stop_conditions),
            "forbidden_actions": list(self.forbidden_actions),
            "execution_authorized": False,
            "merge_authorized": False,
            "production_actions_authorized": False,
        }

    def as_dict(self) -> dict[str, Any]:
        return {**self._base_dict(), "objective_fingerprint": self.objective_fingerprint}


@dataclass(frozen=True, slots=True)
class SubtaskNode:
    node_id: str
    parent_objective_id: str
    role: AgentRole
    instruction: str
    dependencies: tuple[str, ...]
    repository: str
    branch_scope: str
    input_evidence_refs: tuple[str, ...]
    expected_output_evidence: tuple[str, ...]
    budget: BudgetEnvelope
    mutation_class: MutationClass
    completion_criteria: tuple[str, ...]
    abstention_criteria: tuple[str, ...]
    task_kind: TaskKind = TaskKind.GENERAL
    needs_tools: bool = True
    needs_vision: bool = False
    minimum_context_tokens: int = 0
    instruction_fingerprint: str = field(init=False)
    node_fingerprint: str = field(init=False)

    def __post_init__(self) -> None:
        if not _ID.fullmatch(self.node_id):
            raise SupervisorContractError("node_id has an invalid format")
        if not _ID.fullmatch(self.parent_objective_id):
            raise SupervisorContractError("parent_objective_id has an invalid format")
        if not self.instruction.strip():
            raise SupervisorContractError("node instruction must not be empty")
        if len(set(self.dependencies)) != len(self.dependencies):
            raise SupervisorContractError("node dependencies must be unique")
        if any(not _ID.fullmatch(dep) for dep in self.dependencies):
            raise SupervisorContractError("node dependency has an invalid format")
        if not _REPOSITORY.fullmatch(self.repository):
            raise SupervisorContractError("node repository must use owner/name form")
        if not _BRANCH.fullmatch(self.branch_scope):
            raise SupervisorContractError("branch_scope has an invalid format")
        _require_nonempty(self.expected_output_evidence, "expected_output_evidence")
        if any(not value.strip() for value in self.input_evidence_refs):
            raise SupervisorContractError("input_evidence_refs must not contain empty values")
        _require_nonempty(self.completion_criteria, "completion_criteria")
        _require_nonempty(self.abstention_criteria, "abstention_criteria")
        if self.minimum_context_tokens < 0:
            raise SupervisorContractError("minimum_context_tokens must be >= 0")
        instruction_fingerprint = _canonical_hash(
            {
                "instruction": self.instruction,
                "task_kind": self.task_kind.value,
                "needs_tools": self.needs_tools,
                "needs_vision": self.needs_vision,
                "minimum_context_tokens": self.minimum_context_tokens,
            }
        )
        object.__setattr__(self, "instruction_fingerprint", instruction_fingerprint)
        object.__setattr__(self, "node_fingerprint", _canonical_hash(self._base_dict()))

    def _base_dict(self) -> dict[str, Any]:
        return {
            "schema_version": APP8_SUPERVISION_SCHEMA_VERSION,
            "node_id": self.node_id,
            "parent_objective_id": self.parent_objective_id,
            "role": self.role.value,
            "instruction": self.instruction,
            "instruction_fingerprint": self.instruction_fingerprint,
            "dependencies": list(self.dependencies),
            "repository": self.repository,
            "branch_scope": self.branch_scope,
            "input_evidence_refs": list(self.input_evidence_refs),
            "expected_output_evidence": list(self.expected_output_evidence),
            "budget": self.budget.as_dict(),
            "mutation_class": self.mutation_class.value,
            "completion_criteria": list(self.completion_criteria),
            "abstention_criteria": list(self.abstention_criteria),
            "task_kind": self.task_kind.value,
            "needs_tools": self.needs_tools,
            "needs_vision": self.needs_vision,
            "minimum_context_tokens": self.minimum_context_tokens,
        }

    def as_dict(self) -> dict[str, Any]:
        return {**self._base_dict(), "node_fingerprint": self.node_fingerprint}

    def agent_task(self) -> AgentTask:
        return AgentTask(
            instruction=self.instruction,
            kind=self.task_kind,
            needs_tools=self.needs_tools,
            needs_vision=self.needs_vision,
            minimum_context_tokens=self.minimum_context_tokens,
        )


@dataclass(frozen=True, slots=True)
class DependencyGraph:
    objective: ObjectiveContract
    nodes: tuple[SubtaskNode, ...]
    graph_fingerprint: str = field(init=False)

    def __post_init__(self) -> None:
        if not self.nodes:
            raise SupervisorGraphError("graph must contain at least one node")
        ids = [node.node_id for node in self.nodes]
        if len(set(ids)) != len(ids):
            raise SupervisorGraphError("graph node ids must be unique")
        by_id = {node.node_id: node for node in self.nodes}
        roles = {node.role for node in self.nodes}
        if len(roles) > self.objective.max_agent_count:
            raise SupervisorGraphError("graph exceeds objective max_agent_count")
        for node in self.nodes:
            self._validate_node(node, by_id)
        self._assert_acyclic(by_id)
        object.__setattr__(self, "graph_fingerprint", _canonical_hash(self._base_dict()))

    def _validate_node(
        self,
        node: SubtaskNode,
        by_id: Mapping[str, SubtaskNode],
    ) -> None:
        if node.parent_objective_id != self.objective.objective_id:
            raise SupervisorGraphError("node parent objective does not match graph objective")
        if node.repository not in self.objective.repositories:
            raise SupervisorGraphError("node repository is outside objective repository set")
        if node.mutation_class not in self.objective.allowed_change_classes:
            raise SupervisorGraphError("node mutation class is outside objective allowance")
        capability = ROLE_CAPABILITIES[node.role]
        if node.mutation_class not in capability.mutation_classes:
            raise SupervisorGraphError("node mutation class is not allowed for its role")
        if node.task_kind not in capability.task_kinds:
            raise SupervisorGraphError("node task kind is not allowed for its role")
        if (
            node.mutation_class is MutationClass.REVERSIBLE_FEATURE_BRANCH
            and node.branch_scope in _PROTECTED_BRANCHES
        ):
            raise SupervisorGraphError("reversible write node cannot target a protected branch")
        if not BudgetReservation.from_envelope(node.budget).fits_within(
            self.objective.total_budget
        ):
            raise SupervisorGraphError("node budget exceeds objective total budget")
        unknown = set(node.dependencies) - set(by_id)
        if unknown:
            raise SupervisorGraphError(
                f"node {node.node_id} has unknown dependencies: {sorted(unknown)}"
            )
        if node.node_id in node.dependencies:
            raise SupervisorGraphError("node cannot depend on itself")
        required = {
            evidence
            for dep_id in node.dependencies
            for evidence in by_id[dep_id].expected_output_evidence
        }
        if not required.issubset(set(node.input_evidence_refs)):
            missing = sorted(required - set(node.input_evidence_refs))
            raise SupervisorGraphError(
                f"node {node.node_id} does not declare dependency evidence: {missing}"
            )

    @staticmethod
    def _assert_acyclic(by_id: Mapping[str, SubtaskNode]) -> None:
        visiting: set[str] = set()
        visited: set[str] = set()

        def visit(node_id: str) -> None:
            if node_id in visited:
                return
            if node_id in visiting:
                raise SupervisorGraphError("graph contains a dependency cycle")
            visiting.add(node_id)
            for dep in by_id[node_id].dependencies:
                visit(dep)
            visiting.remove(node_id)
            visited.add(node_id)

        for node_id in sorted(by_id):
            visit(node_id)

    def node(self, node_id: str) -> SubtaskNode:
        for node in self.nodes:
            if node.node_id == node_id:
                return node
        raise KeyError(node_id)

    def _base_dict(self) -> dict[str, Any]:
        return {
            "schema_version": APP8_SUPERVISION_SCHEMA_VERSION,
            "policy_version": APP8_SUPERVISION_POLICY_VERSION,
            "objective": self.objective.as_dict(),
            "nodes": [
                node.as_dict() for node in sorted(self.nodes, key=lambda item: item.node_id)
            ],
            "execution_authorized": False,
            "repository_mutation_authorized": False,
            "merge_authorized": False,
            "production_actions_authorized": False,
        }

    def as_dict(self) -> dict[str, Any]:
        return {**self._base_dict(), "graph_fingerprint": self.graph_fingerprint}


@dataclass(frozen=True, slots=True)
class SupervisorEvent:
    sequence: int
    event_type: SupervisorEventType
    node_id: str
    model_name: str | None = None
    model_provider: str | None = None
    evidence_refs: tuple[str, ...] = ()
    reserved_budget: BudgetEnvelope | None = None
    event_fingerprint: str = field(init=False)

    def __post_init__(self) -> None:
        if self.sequence < 1:
            raise SupervisorStateError("event sequence must be positive")
        if not _ID.fullmatch(self.node_id):
            raise SupervisorStateError("event node_id has an invalid format")
        if any(not ref.strip() for ref in self.evidence_refs):
            raise SupervisorStateError("event evidence refs must not contain empty values")
        if self.event_type is SupervisorEventType.NODE_SCHEDULED:
            if not self.model_name or not self.model_provider or self.reserved_budget is None:
                raise SupervisorStateError(
                    "scheduled event requires model identity and reserved budget"
                )
        elif (
            self.model_name is not None
            or self.model_provider is not None
            or self.reserved_budget is not None
        ):
            raise SupervisorStateError(
                "terminal events cannot change model identity or budget reservation"
            )
        object.__setattr__(self, "event_fingerprint", _canonical_hash(self._base_dict()))

    def _base_dict(self) -> dict[str, Any]:
        return {
            "schema_version": APP8_SUPERVISION_SCHEMA_VERSION,
            "sequence": self.sequence,
            "event_type": self.event_type.value,
            "node_id": self.node_id,
            "model_name": self.model_name,
            "model_provider": self.model_provider,
            "evidence_refs": list(self.evidence_refs),
            "reserved_budget": (
                self.reserved_budget.as_dict() if self.reserved_budget is not None else None
            ),
        }

    def as_dict(self) -> dict[str, Any]:
        return {**self._base_dict(), "event_fingerprint": self.event_fingerprint}


@dataclass(frozen=True, slots=True)
class NodeRuntime:
    node_id: str
    state: NodeState
    model_name: str | None
    model_provider: str | None
    evidence_refs: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class SupervisorReplay:
    graph_fingerprint: str
    nodes: tuple[NodeRuntime, ...]
    reserved_budget: BudgetReservation
    disposition: SupervisorDisposition
    event_count: int
    last_event_fingerprint: str | None
    replay_fingerprint: str
    execution_authorized: bool = False
    repository_mutation_authorized: bool = False
    merge_authorized: bool = False
    production_actions_authorized: bool = False

    def state_for(self, node_id: str) -> NodeRuntime:
        for node in self.nodes:
            if node.node_id == node_id:
                return node
        raise KeyError(node_id)

    def as_dict(self) -> dict[str, Any]:
        return {
            "schema_version": APP8_SUPERVISION_SCHEMA_VERSION,
            "graph_fingerprint": self.graph_fingerprint,
            "nodes": [
                {
                    "node_id": node.node_id,
                    "state": node.state.value,
                    "model_name": node.model_name,
                    "model_provider": node.model_provider,
                    "evidence_refs": list(node.evidence_refs),
                }
                for node in self.nodes
            ],
            "reserved_budget": self.reserved_budget.as_dict(),
            "disposition": self.disposition.value,
            "event_count": self.event_count,
            "last_event_fingerprint": self.last_event_fingerprint,
            "replay_fingerprint": self.replay_fingerprint,
            "execution_authorized": False,
            "repository_mutation_authorized": False,
            "merge_authorized": False,
            "production_actions_authorized": False,
        }


@dataclass(frozen=True, slots=True)
class ScheduleDecision:
    node_id: str
    role: AgentRole
    model_name: str
    model_provider: str
    mutation_class: MutationClass
    graph_fingerprint: str
    simulation_only: bool = True
    execution_authorized: bool = False
    repository_mutation_authorized: bool = False
    merge_authorized: bool = False
    production_actions_authorized: bool = False


class SupervisorSimulator:
    """Deterministic APP8A scheduler simulation with no external side effects."""

    def __init__(self, graph: DependencyGraph, router: ModelRouter) -> None:
        self.graph = graph
        self.router = router
        self._events: list[SupervisorEvent] = []

    @property
    def events(self) -> tuple[SupervisorEvent, ...]:
        return tuple(self._events)

    def replay(self, events: Iterable[SupervisorEvent] | None = None) -> SupervisorReplay:
        sequence = tuple(self._events if events is None else events)
        return replay_supervision(self.graph, sequence)

    def schedule_next(self) -> ScheduleDecision | None:
        replay = self.replay()
        if any(node.state is NodeState.RUNNING for node in replay.nodes):
            raise SupervisorStateError("a simulated node is already running")

        ready = [
            self.graph.node(runtime.node_id)
            for runtime in replay.nodes
            if runtime.state is NodeState.READY
            and self.graph.node(runtime.node_id).mutation_class is not MutationClass.HUMAN_GATED
        ]
        if not ready:
            return None

        node = sorted(ready, key=lambda item: item.node_id)[0]
        candidate_budget = replay.reserved_budget.plus(
            BudgetReservation.from_envelope(node.budget)
        )
        if not candidate_budget.fits_within(self.graph.objective.total_budget):
            raise SupervisorBudgetError("objective global budget would be exceeded")

        profile = self.router.select(node.agent_task())
        self._events.append(
            SupervisorEvent(
                sequence=len(self._events) + 1,
                event_type=SupervisorEventType.NODE_SCHEDULED,
                node_id=node.node_id,
                model_name=profile.name,
                model_provider=profile.provider,
                reserved_budget=node.budget,
            )
        )
        return ScheduleDecision(
            node_id=node.node_id,
            role=node.role,
            model_name=profile.name,
            model_provider=profile.provider,
            mutation_class=node.mutation_class,
            graph_fingerprint=self.graph.graph_fingerprint,
        )

    def record_result(
        self,
        node_id: str,
        outcome: NodeOutcome,
        *,
        evidence_refs: tuple[str, ...] = (),
    ) -> SupervisorReplay:
        replay = self.replay()
        runtime = replay.state_for(node_id)
        if runtime.state is not NodeState.RUNNING:
            raise SupervisorStateError("result requires a currently running simulated node")
        node = self.graph.node(node_id)
        if outcome is NodeOutcome.PASS:
            missing = set(node.expected_output_evidence) - set(evidence_refs)
            if missing:
                raise SupervisorStateError(
                    f"PASS result is missing expected evidence: {sorted(missing)}"
                )
        event_type = {
            NodeOutcome.PASS: SupervisorEventType.NODE_COMPLETED,
            NodeOutcome.FAIL: SupervisorEventType.NODE_FAILED,
            NodeOutcome.ABSTAIN: SupervisorEventType.NODE_ABSTAINED,
            NodeOutcome.REVIEW_REQUIRED: SupervisorEventType.NODE_REVIEW_REQUIRED,
        }[outcome]
        self._events.append(
            SupervisorEvent(
                sequence=len(self._events) + 1,
                event_type=event_type,
                node_id=node_id,
                evidence_refs=evidence_refs,
            )
        )
        return self.replay()


def replay_supervision(
    graph: DependencyGraph,
    events: Iterable[SupervisorEvent],
) -> SupervisorReplay:
    event_list = tuple(events)
    by_id = {node.node_id: node for node in graph.nodes}
    state = {node.node_id: NodeState.PENDING for node in graph.nodes}
    model: dict[str, tuple[str, str] | None] = {
        node.node_id: None for node in graph.nodes
    }
    evidence: dict[str, tuple[str, ...]] = {node.node_id: () for node in graph.nodes}
    reserved = BudgetReservation()
    last_event_fingerprint: str | None = None

    for expected_sequence, event in enumerate(event_list, start=1):
        if event.sequence != expected_sequence:
            raise SupervisorStateError("event sequence is not contiguous")
        if event.node_id not in by_id:
            raise SupervisorStateError("event references an unknown node")

        _derive_nonrunning_states(graph, state, evidence)
        current = state[event.node_id]
        if event.event_type is SupervisorEventType.NODE_SCHEDULED:
            if current is not NodeState.READY:
                raise SupervisorStateError("only dependency-ready nodes can be scheduled")
            if by_id[event.node_id].mutation_class is MutationClass.HUMAN_GATED:
                raise SupervisorStateError("human-gated node cannot be scheduled autonomously")
            if event.reserved_budget != by_id[event.node_id].budget:
                raise SupervisorStateError("scheduled budget does not match node budget")
            assert event.reserved_budget is not None
            candidate_budget = reserved.plus(
                BudgetReservation.from_envelope(event.reserved_budget)
            )
            if not candidate_budget.fits_within(graph.objective.total_budget):
                raise SupervisorBudgetError("event stream exceeds objective global budget")
            reserved = candidate_budget
            state[event.node_id] = NodeState.RUNNING
            model[event.node_id] = (str(event.model_name), str(event.model_provider))
        else:
            if current is not NodeState.RUNNING:
                raise SupervisorStateError("terminal event requires a running node")
            if event.event_type is SupervisorEventType.NODE_COMPLETED:
                missing = set(by_id[event.node_id].expected_output_evidence) - set(
                    event.evidence_refs
                )
                if missing:
                    raise SupervisorStateError(
                        f"completed event is missing expected evidence: {sorted(missing)}"
                    )
                state[event.node_id] = NodeState.PASS
            elif event.event_type is SupervisorEventType.NODE_FAILED:
                state[event.node_id] = NodeState.FAIL
            elif event.event_type is SupervisorEventType.NODE_ABSTAINED:
                state[event.node_id] = NodeState.ABSTAIN
            elif event.event_type is SupervisorEventType.NODE_REVIEW_REQUIRED:
                state[event.node_id] = NodeState.REVIEW_REQUIRED
            evidence[event.node_id] = event.evidence_refs
        last_event_fingerprint = event.event_fingerprint

    _derive_nonrunning_states(graph, state, evidence)
    runtimes = tuple(
        NodeRuntime(
            node_id=node.node_id,
            state=state[node.node_id],
            model_name=(model[node.node_id][0] if model[node.node_id] is not None else None),
            model_provider=(
                model[node.node_id][1] if model[node.node_id] is not None else None
            ),
            evidence_refs=evidence[node.node_id],
        )
        for node in sorted(graph.nodes, key=lambda item: item.node_id)
    )
    disposition = _disposition(graph, runtimes)
    replay_base = {
        "schema_version": APP8_SUPERVISION_SCHEMA_VERSION,
        "policy_version": APP8_SUPERVISION_POLICY_VERSION,
        "graph_fingerprint": graph.graph_fingerprint,
        "events": [event.as_dict() for event in event_list],
        "nodes": [
            {
                "node_id": runtime.node_id,
                "state": runtime.state.value,
                "model_name": runtime.model_name,
                "model_provider": runtime.model_provider,
                "evidence_refs": list(runtime.evidence_refs),
            }
            for runtime in runtimes
        ],
        "reserved_budget": reserved.as_dict(),
        "disposition": disposition.value,
        "execution_authorized": False,
        "repository_mutation_authorized": False,
        "merge_authorized": False,
        "production_actions_authorized": False,
    }
    return SupervisorReplay(
        graph_fingerprint=graph.graph_fingerprint,
        nodes=runtimes,
        reserved_budget=reserved,
        disposition=disposition,
        event_count=len(event_list),
        last_event_fingerprint=last_event_fingerprint,
        replay_fingerprint=_canonical_hash(replay_base),
    )


def _derive_nonrunning_states(
    graph: DependencyGraph,
    state: dict[str, NodeState],
    evidence: Mapping[str, tuple[str, ...]],
) -> None:
    by_id = {node.node_id: node for node in graph.nodes}
    terminal_bad = {
        NodeState.FAIL,
        NodeState.ABSTAIN,
        NodeState.REVIEW_REQUIRED,
        NodeState.BLOCKED,
    }
    changed = True
    while changed:
        changed = False
        for node in sorted(graph.nodes, key=lambda item: item.node_id):
            current = state[node.node_id]
            if current in {
                NodeState.RUNNING,
                NodeState.PASS,
                NodeState.FAIL,
                NodeState.ABSTAIN,
                NodeState.REVIEW_REQUIRED,
            }:
                continue
            dep_states = [state[dep] for dep in node.dependencies]
            if any(dep_state in terminal_bad for dep_state in dep_states):
                desired = NodeState.BLOCKED
            elif all(dep_state is NodeState.PASS for dep_state in dep_states):
                required = {
                    ref
                    for dep in node.dependencies
                    for ref in by_id[dep].expected_output_evidence
                }
                actual = {ref for dep in node.dependencies for ref in evidence[dep]}
                desired = NodeState.READY if required.issubset(actual) else NodeState.BLOCKED
            else:
                desired = NodeState.PENDING
            if desired is not current:
                state[node.node_id] = desired
                changed = True


def _disposition(
    graph: DependencyGraph,
    nodes: tuple[NodeRuntime, ...],
) -> SupervisorDisposition:
    states = {node.state for node in nodes}
    if states == {NodeState.PASS}:
        return SupervisorDisposition.COMPLETE
    if NodeState.FAIL in states:
        return SupervisorDisposition.FAIL
    if NodeState.REVIEW_REQUIRED in states:
        return SupervisorDisposition.REVIEW_REQUIRED
    if NodeState.ABSTAIN in states:
        return SupervisorDisposition.ABSTAIN
    if any(
        runtime.state is NodeState.READY
        and graph.node(runtime.node_id).mutation_class is MutationClass.HUMAN_GATED
        for runtime in nodes
    ):
        return SupervisorDisposition.HUMAN_GATE_REQUIRED
    if NodeState.BLOCKED in states and not states.intersection(
        {NodeState.RUNNING, NodeState.READY, NodeState.PENDING}
    ):
        return SupervisorDisposition.BLOCKED
    return SupervisorDisposition.CONTINUE
