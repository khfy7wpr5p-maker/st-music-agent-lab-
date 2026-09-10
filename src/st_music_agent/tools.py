from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from .contracts import ActionRequest
from .policy import AutonomyDecision, AutonomyPolicy


@dataclass(frozen=True, slots=True)
class ActionApproval:
    action_name: str
    target: str

    def matches(self, action: ActionRequest) -> bool:
        return self.action_name == action.name and self.target == action.target


@dataclass(frozen=True, slots=True)
class ActionResult:
    decision: AutonomyDecision
    executed: bool
    value: Any = None


class GuardedActionExecutor:
    """Apply deterministic autonomy policy before a tool performs side effects."""

    def __init__(self, policy: AutonomyPolicy | None = None) -> None:
        self._policy = policy or AutonomyPolicy()

    def execute(
        self,
        action: ActionRequest,
        operation: Callable[[], Any],
        approval: ActionApproval | None = None,
    ) -> ActionResult:
        decision = self._policy.decide(action)

        if decision is AutonomyDecision.DENY:
            return ActionResult(decision=decision, executed=False)

        if decision is AutonomyDecision.REQUIRE_HUMAN and (
            approval is None or not approval.matches(action)
        ):
            return ActionResult(decision=decision, executed=False)

        value = operation()
        return ActionResult(decision=decision, executed=True, value=value)
