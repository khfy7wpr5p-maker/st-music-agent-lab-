from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, Mapping, Protocol

from .models import Action, ActionRequest, AgentPlan, PlannedAction, TaskSpec
from .policy import PolicyEngine

OPENMANUS_REPOSITORY = "FoundationAgents/OpenManus"
OPENMANUS_PIN = "3309bf4e416fb1c74b008f3e86494439a31bad53"


class PlanningBackend(Protocol):
    """Replaceable planning backend. It receives no direct execution authority."""

    def propose(self, prompt: str, exposed_actions: tuple[str, ...]) -> Iterable[Mapping[str, object]]:
        ...


@dataclass(frozen=True, slots=True)
class OpenManusIdentity:
    repository: str = OPENMANUS_REPOSITORY
    revision: str = OPENMANUS_PIN
    live_runtime_enabled: bool = False


class OpenManusAdapter:
    """Translate bounded ST tasks to/from an OpenManus-compatible planning boundary.

    The raw upstream Manus runtime is intentionally not instantiated here because its
    default tool collection includes executable Python and file editing. Those actions
    must first be mediated through ST-owned tools and PolicyEngine.
    """

    def __init__(self, policy: PolicyEngine | None = None) -> None:
        self.policy = policy or PolicyEngine()
        self.identity = OpenManusIdentity()

    def build_prompt(self, task: TaskSpec) -> str:
        return (
            "ST bounded engineering task. "
            f"Task ID: {task.task_id}. Objective: {task.objective}. "
            f"Target: {task.target_repository}@{task.base_ref}. "
            "Propose only actions exposed by the caller. Do not assume authority beyond them."
        )

    def exposed_actions(self, task: TaskSpec) -> tuple[str, ...]:
        hard_denied = {
            Action.DIRECT_DEFAULT_BRANCH_WRITE,
            Action.FORCE_PUSH,
            Action.AUTOMATIC_MERGE,
            Action.WEAKEN_VALIDATOR,
            Action.PRODUCTION_DEPLOYMENT,
            Action.SECRET_COMMIT,
            Action.PRIVATE_STUDENT_DATA_ACCESS,
        }
        return tuple(sorted(action.value for action in task.capabilities if action not in hard_denied))

    def plan(self, task: TaskSpec, backend: PlanningBackend) -> AgentPlan:
        allowed: list[PlannedAction] = []
        blocked: list[PlannedAction] = []
        proposals = backend.propose(self.build_prompt(task), self.exposed_actions(task))
        for proposal in proposals:
            try:
                action = Action(str(proposal["action"]))
            except (KeyError, ValueError):
                continue
            request = ActionRequest(
                action=action,
                target_branch=_as_optional_str(proposal.get("target_branch")),
                path=_as_optional_str(proposal.get("path")),
            )
            planned = PlannedAction(
                request=request,
                rationale=_as_optional_str(proposal.get("rationale")) or "",
            )
            decision = self.policy.evaluate(task, request)
            (allowed if decision.allowed else blocked).append(planned)
        return AgentPlan(actions=tuple(allowed), blocked_actions=tuple(blocked))


def _as_optional_str(value: object) -> str | None:
    return value if isinstance(value, str) else None
