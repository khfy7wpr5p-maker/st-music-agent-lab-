from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from st_music_agent.contracts import AgentTask, ModelProfile, TaskKind
from st_music_agent.execution import DirectAgentRunner
from st_music_agent.router import ModelRouter


@dataclass
class FakeClient:
    profile: ModelProfile
    calls: int = 0

    def complete(self, messages: Sequence[Mapping[str, Any]]) -> Mapping[str, Any]:
        self.calls += 1
        assert messages[0]["content"] == "repair the repository"
        return {"role": "assistant", "content": "done"}


def test_runner_routes_then_executes_selected_client() -> None:
    primary = ModelProfile(
        name="primary",
        provider="test",
        task_kinds=frozenset({TaskKind.CODE}),
        context_window_tokens=64_000,
        preference=100,
    )
    fallback = ModelProfile(
        name="fallback",
        provider="test",
        task_kinds=frozenset({TaskKind.CODE}),
        context_window_tokens=128_000,
        preference=50,
    )
    primary_client = FakeClient(primary)
    fallback_client = FakeClient(fallback)
    runner = DirectAgentRunner(
        ModelRouter((primary, fallback)),
        {"primary": primary_client, "fallback": fallback_client},
    )

    result = runner.run(AgentTask("repair the repository", kind=TaskKind.CODE))

    assert result.model_name == "primary"
    assert result.message["content"] == "done"
    assert primary_client.calls == 1
    assert fallback_client.calls == 0
