from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any

import pytest

from st_music_agent.agent_tools import ToolRegistry
from st_music_agent.tool_loop import ToolLoopBudget, ToolLoopBudgetExceeded, ToolLoopRunner


@dataclass
class RecordingClient:
    responses: list[Mapping[str, Any]]
    calls: list[tuple[list[Mapping[str, Any]], list[Mapping[str, Any]]]] = field(
        default_factory=list
    )

    def complete_with_tools(
        self,
        messages: Sequence[Mapping[str, Any]],
        tools: Sequence[Mapping[str, Any]],
    ) -> Mapping[str, Any]:
        self.calls.append((list(messages), list(tools)))
        return self.responses.pop(0)


def test_tool_loop_exposes_run_budget_snapshot_on_success() -> None:
    client = RecordingClient([{"role": "assistant", "content": "done"}])
    result = ToolLoopRunner(client, ToolRegistry()).run("hello")

    assert result.final_message == {"role": "assistant", "content": "done"}
    assert result.budget_snapshot is not None
    assert result.budget_snapshot.model_turns == 1
    assert result.budget_snapshot.tool_calls == 0
    assert result.budget_snapshot.model_facing_bytes > 0


def test_tool_loop_byte_budget_fails_before_provider_call() -> None:
    client = RecordingClient([{"role": "assistant", "content": "must not run"}])
    runner = ToolLoopRunner(
        client,
        ToolRegistry(),
        budget=ToolLoopBudget(max_model_facing_bytes=1024),
    )

    with pytest.raises(ToolLoopBudgetExceeded, match="byte budget"):
        runner.run("x" * 2000)

    assert client.calls == []


def test_tool_loop_cumulative_payload_budget_counts_replayed_history() -> None:
    client = RecordingClient(
        [
            {
                "role": "assistant",
                "content": None,
                "tool_calls": [
                    {
                        "id": "call-1",
                        "type": "function",
                        "function": {"name": "repo.echo", "arguments": '{"value":"x"}'},
                    }
                ],
            },
            {"role": "assistant", "content": "done"},
        ]
    )
    registry = ToolRegistry()
    registry.register(
        "repo.echo",
        lambda arguments: {"value": arguments["value"]},
        description="Echo a value.",
        parameters={
            "type": "object",
            "properties": {"value": {"type": "string"}},
            "required": ["value"],
        },
    )
    runner = ToolLoopRunner(
        client,
        registry,
        budget=ToolLoopBudget(max_model_facing_bytes=1024),
    )

    result = runner.run("use echo")

    assert result.budget_snapshot is not None
    assert result.budget_snapshot.model_turns == 2
    assert result.budget_snapshot.tool_calls == 1
    assert len(client.calls) == 2
