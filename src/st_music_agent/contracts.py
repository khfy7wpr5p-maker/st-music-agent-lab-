from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Protocol


class TaskKind(str, Enum):
    CODE = "code"
    PLANNING = "planning"
    SCORE_VISION = "score_vision"
    RESEARCH = "research"
    GENERAL = "general"


class RiskLevel(str, Enum):
    READ_ONLY = "read_only"
    REVERSIBLE_WRITE = "reversible_write"
    DESTRUCTIVE = "destructive"
    EXTERNAL_SIDE_EFFECT = "external_side_effect"


@dataclass(frozen=True, slots=True)
class AgentTask:
    instruction: str
    kind: TaskKind = TaskKind.GENERAL
    needs_tools: bool = True
    needs_vision: bool = False
    minimum_context_tokens: int = 0

    def __post_init__(self) -> None:
        if not self.instruction.strip():
            raise ValueError("instruction must not be empty")
        if self.minimum_context_tokens < 0:
            raise ValueError("minimum_context_tokens must be >= 0")


@dataclass(frozen=True, slots=True)
class ModelProfile:
    name: str
    provider: str
    task_kinds: frozenset[TaskKind]
    context_window_tokens: int
    supports_tools: bool = True
    supports_vision: bool = False
    preference: int = 0

    def supports(self, task: AgentTask) -> bool:
        return (
            task.kind in self.task_kinds
            and (not task.needs_tools or self.supports_tools)
            and (not task.needs_vision or self.supports_vision)
            and self.context_window_tokens >= task.minimum_context_tokens
        )


@dataclass(frozen=True, slots=True)
class ActionRequest:
    name: str
    risk: RiskLevel
    target: str = ""
    metadata: Mapping[str, Any] = field(default_factory=dict)


class ModelClient(Protocol):
    """Smallest provider contract the orchestration layer depends on."""

    @property
    def profile(self) -> ModelProfile: ...

    def complete(self, messages: Sequence[Mapping[str, Any]]) -> Mapping[str, Any]: ...
