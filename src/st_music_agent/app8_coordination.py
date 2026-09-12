from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from .app8_execution import ImplementationDisposition, ImplementationExecutionRecord
from .app8_reliability import GateDisposition, GateReport
from .app8_supervision import MutationClass
from .music_evidence import MusicProject

APP8_COORDINATION_SCHEMA_VERSION = "1.0.0"
APP8_COORDINATION_POLICY_VERSION = "2026-09-12.app8d.v1"

_SHA = re.compile(r"^[0-9a-f]{40}$")
_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}$")
_EVIDENCE_KEY = re.compile(r"^[a-z0-9][a-z0-9_.:-]{0,127}$")

PROJECT_REPOSITORIES = {
    MusicProject.SCORE_RESTORE: "khfy7wpr5p-maker/st-score-restore-engine",
    MusicProject.MUSICXML_GUITAR_TAB: "khfy7wpr5p-maker/musicxml-to-guitar-tab-engine",
    MusicProject.SCORE_EDITOR: "khfy7wpr5p-maker/st-score-editor-core",
    MusicProject.REAL_TIME_SCORE_FOLLOWING: "khfy7wpr5p-maker/st-real-time-score-following-lab",
}


class CoordinationContractError(ValueError):
    pass


class CoordinationStateError(RuntimeError):
    pass


class CoordinationItemState(str, Enum):
    PENDING = "pending"
    READY = "ready"
    RUNNING = "running"
    ACCEPTED = "accepted"
    REVIEW_REQUIRED = "review_required"
    ABSTAINED = "abstained"
    FAILED = "failed"
    BLOCKED = "blocked"


class CoordinationOutcome(str, Enum):
    REVIEW_REQUIRED = "review_required"
    ABSTAINED = "abstained"
    FAILED = "failed"


class CoordinationDisposition(str, Enum):
    CONTINUE = "continue"
    COMPLETE = "complete"
    REVIEW_REQUIRED = "review_required"
    ABSTAINED = "abstained"
    FAILED = "failed"
    BLOCKED = "blocked"


class CoordinationEventType(str, Enum):
    ITEM_SCHEDULED = "item_scheduled"
    ITEM_ACCEPTED = "item_accepted"
    ITEM_REVIEW_REQUIRED = "item_review_required"
    ITEM_ABSTAINED = "item_abstained"
    ITEM_FAILED = "item_failed"


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
    if not _SHA.fullmatch(value):
        raise CoordinationContractError(f"{label} must be a full lowercase 40-hex SHA")


def _require_sha256(value: str, label: str) -> None:
    if not _SHA256.fullmatch(value):
        raise CoordinationContractError(f"{label} must be a lowercase SHA-256 digest")


def _require_evidence_keys(values: tuple[str, ...], label: str, *, allow_empty: bool) -> None:
    if not allow_empty and not values:
        raise CoordinationContractError(f"{label} must not be empty")
    if len(set(values)) != len(values):
        raise CoordinationContractError(f"{label} must be unique")
    if any(not _EVIDENCE_KEY.fullmatch(value) for value in values):
        raise CoordinationContractError(f"{label} contains an invalid evidence key")


@dataclass(frozen=True, slots=True)
class ProjectWorkItem:
    item_id: str
    project: MusicProject
    repository: str
    expected_base_sha: str
    instruction: str
    dependencies: tuple[str, ...]
    required_upstream_evidence: tuple[str, ...]
    produces_evidence: tuple[str, ...]
    mutation_class: MutationClass
    instruction_fingerprint: str = field(init=False)
    item_fingerprint: str = field(init=False)

    def __post_init__(self) -> None:
        if not _ID.fullmatch(self.item_id):
            raise CoordinationContractError("item_id has an invalid format")
        expected_repo = PROJECT_REPOSITORIES[self.project]
        if self.repository != expected_repo:
            raise CoordinationContractError("work item repository does not match project binding")
        _require_sha(self.expected_base_sha, "expected_base_sha")
        if not self.instruction.strip():
            raise CoordinationContractError("work item instruction must not be empty")
        if len(set(self.dependencies)) != len(self.dependencies):
            raise CoordinationContractError("work item dependencies must be unique")
        if any(not _ID.fullmatch(value) for value in self.dependencies):
            raise CoordinationContractError("work item dependency has an invalid format")
        _require_evidence_keys(
            self.required_upstream_evidence,
            "required_upstream_evidence",
            allow_empty=True,
        )
        _require_evidence_keys(self.produces_evidence, "produces_evidence", allow_empty=False)
        if self.mutation_class not in {
            MutationClass.READ_ONLY,
            MutationClass.REVERSIBLE_FEATURE_BRANCH,
        }:
            raise CoordinationContractError(
                "APP8D work items must be read-only or reversible feature-branch work"
            )
        instruction_fingerprint = _canonical_hash(
            {"project": self.project.value, "instruction": self.instruction}
        )
        object.__setattr__(self, "instruction_fingerprint", instruction_fingerprint)
        object.__setattr__(self, "item_fingerprint", _canonical_hash(self._base_dict()))

    def _base_dict(self) -> dict[str, Any]:
        return {
            "schema_version": APP8_COORDINATION_SCHEMA_VERSION,
            "item_id": self.item_id,
            "project": self.project.value,
            "repository": self.repository,
            "expected_base_sha": self.expected_base_sha,
            "instruction": self.instruction,
            "instruction_fingerprint": self.instruction_fingerprint,
            "dependencies": list(self.dependencies),
            "required_upstream_evidence": list(self.required_upstream_evidence),
            "produces_evidence": list(self.produces_evidence),
            "mutation_class": self.mutation_class.value,
        }

    def as_dict(self) -> dict[str, Any]:
        return {**self._base_dict(), "item_fingerprint": self.item_fingerprint}


@dataclass(frozen=True, slots=True)
class CrossProjectPlan:
    plan_id: str
    items: tuple[ProjectWorkItem, ...]
    plan_fingerprint: str = field(init=False)

    def __post_init__(self) -> None:
        if not _ID.fullmatch(self.plan_id):
            raise CoordinationContractError("plan_id has an invalid format")
        if len(self.items) < 2:
            raise CoordinationContractError("cross-project plan requires at least two work items")
        ids = [item.item_id for item in self.items]
        if len(set(ids)) != len(ids):
            raise CoordinationContractError("work item ids must be unique")
        projects = [item.project for item in self.items]
        if len(set(projects)) != len(projects):
            raise CoordinationContractError(
                "APP8D v1 allows at most one work item per music project"
            )
        by_id = {item.item_id: item for item in self.items}
        for item in self.items:
            unknown = set(item.dependencies) - set(by_id)
            if unknown:
                raise CoordinationContractError(
                    f"work item {item.item_id} has unknown dependencies: {sorted(unknown)}"
                )
            if item.item_id in item.dependencies:
                raise CoordinationContractError("work item cannot depend on itself")
            if not item.dependencies and item.required_upstream_evidence:
                raise CoordinationContractError(
                    "root work item cannot require upstream evidence"
                )
            available = {
                key
                for dependency_id in item.dependencies
                for key in by_id[dependency_id].produces_evidence
            }
            missing = set(item.required_upstream_evidence) - available
            if missing:
                raise CoordinationContractError(
                    f"work item {item.item_id} requires undeclared upstream evidence: "
                    f"{sorted(missing)}"
                )
        self._assert_acyclic(by_id)
        object.__setattr__(self, "plan_fingerprint", _canonical_hash(self._base_dict()))

    @staticmethod
    def _assert_acyclic(by_id: dict[str, ProjectWorkItem]) -> None:
        visiting: set[str] = set()
        visited: set[str] = set()

        def visit(item_id: str) -> None:
            if item_id in visited:
                return
            if item_id in visiting:
                raise CoordinationContractError("cross-project plan contains a dependency cycle")
            visiting.add(item_id)
            for dependency_id in by_id[item_id].dependencies:
                visit(dependency_id)
            visiting.remove(item_id)
            visited.add(item_id)

        for item_id in sorted(by_id):
            visit(item_id)

    def item(self, item_id: str) -> ProjectWorkItem:
        for item in self.items:
            if item.item_id == item_id:
                return item
        raise KeyError(item_id)

    def _base_dict(self) -> dict[str, Any]:
        return {
            "schema_version": APP8_COORDINATION_SCHEMA_VERSION,
            "policy_version": APP8_COORDINATION_POLICY_VERSION,
            "plan_id": self.plan_id,
            "items": [item.as_dict() for item in sorted(self.items, key=lambda value: value.item_id)],
            "execution_authorized": False,
            "repository_mutation_authorized": False,
            "pr_open_authorized": False,
            "merge_authorized": False,
            "production_actions_authorized": False,
        }

    def as_dict(self) -> dict[str, Any]:
        return {**self._base_dict(), "plan_fingerprint": self.plan_fingerprint}


@dataclass(frozen=True, slots=True)
class ProjectCompletionReceipt:
    item_id: str
    project: MusicProject
    repository: str
    base_sha: str
    head_sha: str
    artifact_sha256: str
    verification_sha256: str
    produced_evidence: tuple[str, ...]
    source: str
    receipt_fingerprint: str = field(init=False)
    execution_authorized: bool = False
    repository_mutation_authorized: bool = False
    pr_open_authorized: bool = False
    merge_authorized: bool = False
    production_actions_authorized: bool = False

    def __post_init__(self) -> None:
        if not _ID.fullmatch(self.item_id):
            raise CoordinationContractError("receipt item_id has an invalid format")
        if self.repository != PROJECT_REPOSITORIES[self.project]:
            raise CoordinationContractError("receipt repository does not match project binding")
        _require_sha(self.base_sha, "receipt base_sha")
        _require_sha(self.head_sha, "receipt head_sha")
        _require_sha256(self.artifact_sha256, "receipt artifact_sha256")
        _require_sha256(self.verification_sha256, "receipt verification_sha256")
        _require_evidence_keys(self.produced_evidence, "produced_evidence", allow_empty=False)
        if self.source not in {"app8c_verified_cycle", "host_verified_read_only"}:
            raise CoordinationContractError("receipt source is unsupported")
        object.__setattr__(self, "receipt_fingerprint", _canonical_hash(self._base_dict()))

    def _base_dict(self) -> dict[str, Any]:
        return {
            "schema_version": APP8_COORDINATION_SCHEMA_VERSION,
            "item_id": self.item_id,
            "project": self.project.value,
            "repository": self.repository,
            "base_sha": self.base_sha,
            "head_sha": self.head_sha,
            "artifact_sha256": self.artifact_sha256,
            "verification_sha256": self.verification_sha256,
            "produced_evidence": list(self.produced_evidence),
            "source": self.source,
            "execution_authorized": False,
            "repository_mutation_authorized": False,
            "pr_open_authorized": False,
            "merge_authorized": False,
            "production_actions_authorized": False,
        }

    def as_dict(self) -> dict[str, Any]:
        return {**self._base_dict(), "receipt_fingerprint": self.receipt_fingerprint}

    @classmethod
    def from_app8c(
        cls,
        item: ProjectWorkItem,
        implementation: ImplementationExecutionRecord,
        gate: GateReport,
        *,
        produced_evidence: tuple[str, ...],
    ) -> ProjectCompletionReceipt:
        if item.mutation_class is not MutationClass.REVERSIBLE_FEATURE_BRANCH:
            raise CoordinationContractError("APP8C receipt requires reversible feature-branch item")
        if implementation.disposition is not ImplementationDisposition.VERIFIED:
            raise CoordinationContractError("APP8C implementation must be VERIFIED")
        if implementation.repository != item.repository:
            raise CoordinationContractError("APP8C implementation repository mismatch")
        if implementation.base_sha != item.expected_base_sha:
            raise CoordinationContractError("APP8C implementation base SHA mismatch")
        if gate.disposition is not GateDisposition.ACCEPT:
            raise CoordinationContractError("APP8C gate must ACCEPT before coordination receipt")
        if (
            gate.repository != implementation.repository
            or gate.commit_sha != implementation.head_sha
            or gate.artifact_sha256 != implementation.artifact_sha256
        ):
            raise CoordinationContractError("APP8C gate binding differs from implementation")
        missing = set(item.produces_evidence) - set(produced_evidence)
        if missing:
            raise CoordinationContractError(
                f"APP8C receipt is missing declared produced evidence: {sorted(missing)}"
            )
        return cls(
            item_id=item.item_id,
            project=item.project,
            repository=item.repository,
            base_sha=implementation.base_sha,
            head_sha=implementation.head_sha,
            artifact_sha256=implementation.artifact_sha256,
            verification_sha256=gate.report_fingerprint,
            produced_evidence=produced_evidence,
            source="app8c_verified_cycle",
        )

    @classmethod
    def from_host_verified_read_only(
        cls,
        item: ProjectWorkItem,
        *,
        exact_sha: str,
        artifact_sha256: str,
        verification_sha256: str,
        produced_evidence: tuple[str, ...],
    ) -> ProjectCompletionReceipt:
        if item.mutation_class is not MutationClass.READ_ONLY:
            raise CoordinationContractError("host read-only receipt requires READ_ONLY work item")
        if exact_sha != item.expected_base_sha:
            raise CoordinationContractError("read-only receipt must remain on expected exact SHA")
        missing = set(item.produces_evidence) - set(produced_evidence)
        if missing:
            raise CoordinationContractError(
                f"read-only receipt is missing declared produced evidence: {sorted(missing)}"
            )
        return cls(
            item_id=item.item_id,
            project=item.project,
            repository=item.repository,
            base_sha=exact_sha,
            head_sha=exact_sha,
            artifact_sha256=artifact_sha256,
            verification_sha256=verification_sha256,
            produced_evidence=produced_evidence,
            source="host_verified_read_only",
        )


@dataclass(frozen=True, slots=True)
class CoordinationEvent:
    sequence: int
    event_type: CoordinationEventType
    item_id: str
    receipt: ProjectCompletionReceipt | None = None
    evidence_ref: str | None = None
    event_fingerprint: str = field(init=False)

    def __post_init__(self) -> None:
        if self.sequence < 1:
            raise CoordinationStateError("coordination event sequence must be positive")
        if not _ID.fullmatch(self.item_id):
            raise CoordinationStateError("coordination event item_id is invalid")
        if self.event_type is CoordinationEventType.ITEM_ACCEPTED:
            if self.receipt is None or self.evidence_ref is not None:
                raise CoordinationStateError("accepted event requires only a completion receipt")
        elif self.event_type is CoordinationEventType.ITEM_SCHEDULED:
            if self.receipt is not None or self.evidence_ref is not None:
                raise CoordinationStateError("scheduled event cannot contain result evidence")
        else:
            if self.receipt is not None:
                raise CoordinationStateError("non-accepted result cannot contain completion receipt")
            if not isinstance(self.evidence_ref, str) or not self.evidence_ref.strip():
                raise CoordinationStateError("non-accepted result requires an evidence reference")
        object.__setattr__(self, "event_fingerprint", _canonical_hash(self._base_dict()))

    def _base_dict(self) -> dict[str, Any]:
        return {
            "schema_version": APP8_COORDINATION_SCHEMA_VERSION,
            "sequence": self.sequence,
            "event_type": self.event_type.value,
            "item_id": self.item_id,
            "receipt": self.receipt.as_dict() if self.receipt is not None else None,
            "evidence_ref": self.evidence_ref,
        }

    def as_dict(self) -> dict[str, Any]:
        return {**self._base_dict(), "event_fingerprint": self.event_fingerprint}


@dataclass(frozen=True, slots=True)
class CoordinationRuntimeItem:
    item_id: str
    project: MusicProject
    state: CoordinationItemState
    receipt_fingerprint: str | None


@dataclass(frozen=True, slots=True)
class CoordinationReplay:
    plan_fingerprint: str
    items: tuple[CoordinationRuntimeItem, ...]
    disposition: CoordinationDisposition
    event_count: int
    last_event_fingerprint: str | None
    replay_fingerprint: str
    execution_authorized: bool = False
    repository_mutation_authorized: bool = False
    pr_open_authorized: bool = False
    merge_authorized: bool = False
    production_actions_authorized: bool = False

    def state_for(self, item_id: str) -> CoordinationRuntimeItem:
        for item in self.items:
            if item.item_id == item_id:
                return item
        raise KeyError(item_id)

    def as_dict(self) -> dict[str, Any]:
        return {
            "schema_version": APP8_COORDINATION_SCHEMA_VERSION,
            "plan_fingerprint": self.plan_fingerprint,
            "items": [
                {
                    "item_id": item.item_id,
                    "project": item.project.value,
                    "state": item.state.value,
                    "receipt_fingerprint": item.receipt_fingerprint,
                }
                for item in self.items
            ],
            "disposition": self.disposition.value,
            "event_count": self.event_count,
            "last_event_fingerprint": self.last_event_fingerprint,
            "replay_fingerprint": self.replay_fingerprint,
            "execution_authorized": False,
            "repository_mutation_authorized": False,
            "pr_open_authorized": False,
            "merge_authorized": False,
            "production_actions_authorized": False,
        }


@dataclass(frozen=True, slots=True)
class CoordinationDecision:
    item_id: str
    project: MusicProject
    repository: str
    expected_base_sha: str
    mutation_class: MutationClass
    required_upstream_evidence: tuple[str, ...]
    plan_fingerprint: str
    coordination_only: bool = True
    execution_authorized: bool = False
    repository_mutation_authorized: bool = False
    pr_open_authorized: bool = False
    merge_authorized: bool = False
    production_actions_authorized: bool = False


class CrossProjectCoordinator:
    """Deterministic receipt-driven coordination; never invokes project execution itself."""

    def __init__(self, plan: CrossProjectPlan) -> None:
        self.plan = plan
        self._events: list[CoordinationEvent] = []

    @property
    def events(self) -> tuple[CoordinationEvent, ...]:
        return tuple(self._events)

    def replay(self) -> CoordinationReplay:
        return replay_coordination(self.plan, self._events)

    def schedule_next(self) -> CoordinationDecision | None:
        replay = self.replay()
        if any(item.state is CoordinationItemState.RUNNING for item in replay.items):
            raise CoordinationStateError("a cross-project work item is already running")
        ready = [
            self.plan.item(runtime.item_id)
            for runtime in replay.items
            if runtime.state is CoordinationItemState.READY
        ]
        if not ready:
            return None
        item = min(ready, key=lambda value: (value.project.value, value.item_id))
        self._events.append(
            CoordinationEvent(
                sequence=len(self._events) + 1,
                event_type=CoordinationEventType.ITEM_SCHEDULED,
                item_id=item.item_id,
            )
        )
        return CoordinationDecision(
            item_id=item.item_id,
            project=item.project,
            repository=item.repository,
            expected_base_sha=item.expected_base_sha,
            mutation_class=item.mutation_class,
            required_upstream_evidence=item.required_upstream_evidence,
            plan_fingerprint=self.plan.plan_fingerprint,
        )

    def record_receipt(self, receipt: ProjectCompletionReceipt) -> CoordinationReplay:
        replay = self.replay()
        runtime = replay.state_for(receipt.item_id)
        if runtime.state is not CoordinationItemState.RUNNING:
            raise CoordinationStateError("completion receipt requires a running work item")
        item = self.plan.item(receipt.item_id)
        _validate_receipt_binding(item, receipt)
        self._events.append(
            CoordinationEvent(
                sequence=len(self._events) + 1,
                event_type=CoordinationEventType.ITEM_ACCEPTED,
                item_id=item.item_id,
                receipt=receipt,
            )
        )
        return self.replay()

    def record_nonpass(
        self,
        item_id: str,
        outcome: CoordinationOutcome,
        *,
        evidence_ref: str,
    ) -> CoordinationReplay:
        replay = self.replay()
        if replay.state_for(item_id).state is not CoordinationItemState.RUNNING:
            raise CoordinationStateError("non-pass result requires a running work item")
        event_type = {
            CoordinationOutcome.REVIEW_REQUIRED: CoordinationEventType.ITEM_REVIEW_REQUIRED,
            CoordinationOutcome.ABSTAINED: CoordinationEventType.ITEM_ABSTAINED,
            CoordinationOutcome.FAILED: CoordinationEventType.ITEM_FAILED,
        }[outcome]
        self._events.append(
            CoordinationEvent(
                sequence=len(self._events) + 1,
                event_type=event_type,
                item_id=item_id,
                evidence_ref=evidence_ref,
            )
        )
        return self.replay()


def _validate_receipt_binding(item: ProjectWorkItem, receipt: ProjectCompletionReceipt) -> None:
    if receipt.item_id != item.item_id or receipt.project is not item.project:
        raise CoordinationStateError("completion receipt item/project binding mismatch")
    if receipt.repository != item.repository:
        raise CoordinationStateError("completion receipt repository mismatch")
    if receipt.base_sha != item.expected_base_sha:
        raise CoordinationStateError("completion receipt base SHA mismatch")
    missing = set(item.produces_evidence) - set(receipt.produced_evidence)
    if missing:
        raise CoordinationStateError(
            f"completion receipt missing declared output evidence: {sorted(missing)}"
        )
    if item.mutation_class is MutationClass.READ_ONLY:
        if receipt.source != "host_verified_read_only" or receipt.head_sha != item.expected_base_sha:
            raise CoordinationStateError("read-only receipt widened repository state")
    elif receipt.source != "app8c_verified_cycle":
        raise CoordinationStateError("writable item requires APP8C verified-cycle receipt")


def replay_coordination(
    plan: CrossProjectPlan,
    events: list[CoordinationEvent] | tuple[CoordinationEvent, ...],
) -> CoordinationReplay:
    event_list = tuple(events)
    state = {item.item_id: CoordinationItemState.PENDING for item in plan.items}
    receipts: dict[str, ProjectCompletionReceipt] = {}
    last_fingerprint: str | None = None

    for expected_sequence, event in enumerate(event_list, start=1):
        if event.sequence != expected_sequence:
            raise CoordinationStateError("coordination event sequence is not contiguous")
        try:
            item = plan.item(event.item_id)
        except KeyError as exc:
            raise CoordinationStateError("coordination event references unknown item") from exc
        _derive_coordination_states(plan, state, receipts)
        current = state[item.item_id]
        if event.event_type is CoordinationEventType.ITEM_SCHEDULED:
            if current is not CoordinationItemState.READY:
                raise CoordinationStateError("only dependency-ready work items can be scheduled")
            state[item.item_id] = CoordinationItemState.RUNNING
        else:
            if current is not CoordinationItemState.RUNNING:
                raise CoordinationStateError("result event requires a running work item")
            if event.event_type is CoordinationEventType.ITEM_ACCEPTED:
                assert event.receipt is not None
                _validate_receipt_binding(item, event.receipt)
                receipts[item.item_id] = event.receipt
                state[item.item_id] = CoordinationItemState.ACCEPTED
            elif event.event_type is CoordinationEventType.ITEM_REVIEW_REQUIRED:
                state[item.item_id] = CoordinationItemState.REVIEW_REQUIRED
            elif event.event_type is CoordinationEventType.ITEM_ABSTAINED:
                state[item.item_id] = CoordinationItemState.ABSTAINED
            elif event.event_type is CoordinationEventType.ITEM_FAILED:
                state[item.item_id] = CoordinationItemState.FAILED
        last_fingerprint = event.event_fingerprint

    _derive_coordination_states(plan, state, receipts)
    runtime = tuple(
        CoordinationRuntimeItem(
            item_id=item.item_id,
            project=item.project,
            state=state[item.item_id],
            receipt_fingerprint=(
                receipts[item.item_id].receipt_fingerprint if item.item_id in receipts else None
            ),
        )
        for item in sorted(plan.items, key=lambda value: value.item_id)
    )
    disposition = _coordination_disposition(runtime)
    material = {
        "schema_version": APP8_COORDINATION_SCHEMA_VERSION,
        "policy_version": APP8_COORDINATION_POLICY_VERSION,
        "plan_fingerprint": plan.plan_fingerprint,
        "events": [event.as_dict() for event in event_list],
        "items": [
            {
                "item_id": item.item_id,
                "project": item.project.value,
                "state": item.state.value,
                "receipt_fingerprint": item.receipt_fingerprint,
            }
            for item in runtime
        ],
        "disposition": disposition.value,
        "execution_authorized": False,
        "repository_mutation_authorized": False,
        "pr_open_authorized": False,
        "merge_authorized": False,
        "production_actions_authorized": False,
    }
    return CoordinationReplay(
        plan_fingerprint=plan.plan_fingerprint,
        items=runtime,
        disposition=disposition,
        event_count=len(event_list),
        last_event_fingerprint=last_fingerprint,
        replay_fingerprint=_canonical_hash(material),
    )


def _derive_coordination_states(
    plan: CrossProjectPlan,
    state: dict[str, CoordinationItemState],
    receipts: dict[str, ProjectCompletionReceipt],
) -> None:
    by_id = {item.item_id: item for item in plan.items}
    blocking = {
        CoordinationItemState.REVIEW_REQUIRED,
        CoordinationItemState.ABSTAINED,
        CoordinationItemState.FAILED,
        CoordinationItemState.BLOCKED,
    }
    changed = True
    while changed:
        changed = False
        for item in sorted(plan.items, key=lambda value: value.item_id):
            current = state[item.item_id]
            if current in {
                CoordinationItemState.RUNNING,
                CoordinationItemState.ACCEPTED,
                CoordinationItemState.REVIEW_REQUIRED,
                CoordinationItemState.ABSTAINED,
                CoordinationItemState.FAILED,
            }:
                continue
            dependency_states = [state[value] for value in item.dependencies]
            if any(value in blocking for value in dependency_states):
                desired = CoordinationItemState.BLOCKED
            elif all(value is CoordinationItemState.ACCEPTED for value in dependency_states):
                available = {
                    key
                    for dependency_id in item.dependencies
                    for key in receipts[dependency_id].produced_evidence
                }
                desired = (
                    CoordinationItemState.READY
                    if set(item.required_upstream_evidence).issubset(available)
                    else CoordinationItemState.BLOCKED
                )
            else:
                desired = CoordinationItemState.PENDING
            if desired is not current:
                state[item.item_id] = desired
                changed = True


def _coordination_disposition(
    items: tuple[CoordinationRuntimeItem, ...],
) -> CoordinationDisposition:
    states = {item.state for item in items}
    if states == {CoordinationItemState.ACCEPTED}:
        return CoordinationDisposition.COMPLETE
    if CoordinationItemState.FAILED in states:
        return CoordinationDisposition.FAILED
    if CoordinationItemState.REVIEW_REQUIRED in states:
        return CoordinationDisposition.REVIEW_REQUIRED
    if CoordinationItemState.ABSTAINED in states:
        return CoordinationDisposition.ABSTAINED
    if CoordinationItemState.BLOCKED in states and not states.intersection(
        {
            CoordinationItemState.RUNNING,
            CoordinationItemState.READY,
            CoordinationItemState.PENDING,
        }
    ):
        return CoordinationDisposition.BLOCKED
    return CoordinationDisposition.CONTINUE
