from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from .contracts import AgentTask, ModelClient
from .router import ModelRouter


class MissingModelClientError(LookupError):
    pass


@dataclass(frozen=True, slots=True)
class ExecutionResult:
    model_name: str
    message: Mapping[str, Any]


class DirectAgentRunner:
    """Route a task and execute one provider-backed model turn."""

    def __init__(self, router: ModelRouter, clients: Mapping[str, ModelClient]) -> None:
        self._router = router
        self._clients = dict(clients)

    def run(self, task: AgentTask) -> ExecutionResult:
        profile = self._router.select(task)
        client = self._clients.get(profile.name)
        if client is None:
            raise MissingModelClientError(f"no configured client for routed model: {profile.name}")

        message = client.complete(({"role": "user", "content": task.instruction},))
        return ExecutionResult(model_name=profile.name, message=message)
