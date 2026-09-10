from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from .contracts import ActionRequest, RiskLevel


class AutonomyDecision(str, Enum):
    AUTO_EXECUTE = "auto_execute"
    REQUIRE_HUMAN = "require_human"
    DENY = "deny"


@dataclass(frozen=True, slots=True)
class AutonomyPolicy:
    """Minimal guardrail for autonomous engineering actions.

    The default policy intentionally separates ordinary reversible development work
    from destructive, credential-sensitive, protected-branch, and external actions.
    """

    protected_branches: frozenset[str] = frozenset({"main", "master"})

    def decide(self, action: ActionRequest) -> AutonomyDecision:
        metadata = action.metadata

        if metadata.get("contains_secret") or metadata.get("requests_secret"):
            return AutonomyDecision.DENY

        if metadata.get("human_required"):
            return AutonomyDecision.REQUIRE_HUMAN

        if action.risk in {RiskLevel.DESTRUCTIVE, RiskLevel.EXTERNAL_SIDE_EFFECT}:
            return AutonomyDecision.REQUIRE_HUMAN

        branch = str(metadata.get("branch", "")).strip()
        if action.risk is RiskLevel.REVERSIBLE_WRITE and branch in self.protected_branches:
            return AutonomyDecision.REQUIRE_HUMAN

        return AutonomyDecision.AUTO_EXECUTE
