from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Callable, Mapping

from .models import RunState, TaskSpec

Clock = Callable[[], datetime]


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


@dataclass(frozen=True, slots=True)
class LedgerEvent:
    sequence: int
    timestamp: str
    kind: str
    status: str
    evidence: Mapping[str, object] = field(default_factory=dict)


class RunLedger:
    """Structured audit evidence; never stores hidden reasoning or chain-of-thought."""

    def __init__(self, run_id: str, task: TaskSpec, clock: Clock = utc_now) -> None:
        if not run_id.strip():
            raise ValueError("run_id must be non-empty")
        self.run_id = run_id
        self.task = task
        self._clock = clock
        self._events: list[LedgerEvent] = []
        self._final_state: RunState | None = None

    @property
    def events(self) -> tuple[LedgerEvent, ...]:
        return tuple(self._events)

    def record(self, kind: str, status: str, evidence: Mapping[str, object] | None = None) -> LedgerEvent:
        event = LedgerEvent(
            sequence=len(self._events) + 1,
            timestamp=self._clock().astimezone(timezone.utc).isoformat(),
            kind=kind,
            status=status,
            evidence=dict(evidence or {}),
        )
        self._events.append(event)
        return event

    def finalize(self, state: RunState) -> None:
        if self._final_state is not None:
            raise RuntimeError("run ledger is already finalized")
        self._final_state = state

    def to_dict(self) -> dict[str, object]:
        return {
            "schema_version": "0.1.0",
            "run_id": self.run_id,
            "task_id": self.task.task_id,
            "objective": self.task.objective,
            "target_repository": self.task.target_repository,
            "base_ref": self.task.base_ref,
            "mode": self.task.mode.value,
            "capabilities": sorted(capability.value for capability in self.task.capabilities),
            "events": [asdict(event) for event in self._events],
            "final_state": self._final_state.value if self._final_state else None,
        }
