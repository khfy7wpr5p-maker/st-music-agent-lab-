from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any

import pytest

from st_music_agent.agent_tools import ToolRegistry
from st_music_agent.tool_loop import (
    ToolCallProtocolError,
    ToolLoopBudget,
    ToolLoopBudgetExceeded,
    ToolLoopRunner,
)


@dataclass
class ScriptedClient:
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


def test_tool_loop_executes_registered_tool_and_replays_reasoning_content() -> None:
    client = ScriptedClient(
        responses=[
            {
                "role": "assistant",
                "content": None,
                "reasoning_content": "provider-internal-context",
                "provider_private_field": "must-not-be-replayed",
                "tool_calls": [
                    {
                        "id": "call-1",
                        "type": "function",
                        "function": {
                            "name": "repo.echo",
                            "arguments": '{"value":"hello"}',
                        },
                    }
                ],
            },
            {
                "role": "assistant",
                "content": "finished",
                "reasoning_content": "do-not-expose",
                "provider_private_field": "do-not-expose",
            },
        ]
    )
    registry = ToolRegistry()
    registry.register(
        "repo.echo",
        lambda arguments: {"value": arguments["value"]},
        description="Echo one value.",
        parameters={
            "type": "object",
            "properties": {"value": {"type": "string"}},
            "required": ["value"],
        },
    )

    result = ToolLoopRunner(client, registry).run("use the tool")

    assert result.turns == 2
    assert result.tool_calls == 1
    assert result.final_message == {"role": "assistant", "content": "finished"}
    second_messages = client.calls[1][0]
    assert second_messages[1]["reasoning_content"] == "provider-internal-context"
    assert "provider_private_field" not in second_messages[1]
    assert second_messages[1]["tool_calls"][0]["type"] == "function"
    assert second_messages[2]["role"] == "tool"
    assert second_messages[2]["tool_call_id"] == "call-1"
    assert client.calls[0][1][0]["function"]["name"] == "repo.echo"


def test_tool_loop_accepts_mapping_arguments_from_nonstandard_compatible_server() -> None:
    client = ScriptedClient(
        responses=[
            {
                "role": "assistant",
                "content": None,
                "tool_calls": [
                    {
                        "id": "call-1",
                        "function": {"name": "repo.echo", "arguments": {"value": "hello"}},
                    }
                ],
            },
            {"role": "assistant", "content": "done"},
        ]
    )
    registry = ToolRegistry()
    registry.register("repo.echo", lambda arguments: {"value": arguments["value"]})

    result = ToolLoopRunner(client, registry).run("use the tool")

    assert result.tool_calls == 1
    assert result.final_message["content"] == "done"
    replayed = client.calls[1][0][1]["tool_calls"][0]
    assert replayed["function"]["arguments"] == '{"value":"hello"}'


def test_tool_loop_rejects_malformed_tool_arguments_before_dispatch() -> None:
    client = ScriptedClient(
        responses=[
            {
                "role": "assistant",
                "content": None,
                "tool_calls": [
                    {
                        "id": "call-1",
                        "function": {"name": "repo.echo", "arguments": "not-json"},
                    }
                ],
            }
        ]
    )
    calls = 0

    def handler(arguments: Mapping[str, Any]) -> Mapping[str, Any]:
        nonlocal calls
        calls += 1
        return dict(arguments)

    registry = ToolRegistry()
    registry.register("repo.echo", handler)

    with pytest.raises(ToolCallProtocolError):
        ToolLoopRunner(client, registry).run("use the tool")
    assert calls == 0


def test_tool_loop_fails_before_partial_batch_when_tool_budget_would_overflow() -> None:
    tool_calls = [
        {
            "id": f"call-{index}",
            "function": {"name": "repo.echo", "arguments": "{}"},
        }
        for index in range(2)
    ]
    client = ScriptedClient(
        responses=[{"role": "assistant", "content": None, "tool_calls": tool_calls}]
    )
    calls = 0

    def handler(arguments: Mapping[str, Any]) -> Mapping[str, Any]:
        nonlocal calls
        calls += 1
        return dict(arguments)

    registry = ToolRegistry()
    registry.register("repo.echo", handler)
    runner = ToolLoopRunner(client, registry, budget=ToolLoopBudget(max_turns=2, max_tool_calls=1))

    with pytest.raises(ToolLoopBudgetExceeded):
        runner.run("use tools")
    assert calls == 0


def test_tool_loop_rejects_duplicate_call_ids_and_non_function_calls() -> None:
    duplicate_ids = ScriptedClient(
        responses=[
            {
                "role": "assistant",
                "content": None,
                "tool_calls": [
                    {"id": "same", "function": {"name": "repo.echo", "arguments": "{}"}},
                    {"id": "same", "function": {"name": "repo.echo", "arguments": "{}"}},
                ],
            }
        ]
    )
    registry = ToolRegistry()
    registry.register("repo.echo", lambda arguments: dict(arguments))

    with pytest.raises(ToolCallProtocolError, match="unique"):
        ToolLoopRunner(duplicate_ids, registry).run("use tools")

    wrong_type = ScriptedClient(
        responses=[
            {
                "role": "assistant",
                "content": None,
                "tool_calls": [
                    {
                        "id": "call-1",
                        "type": "custom",
                        "function": {"name": "repo.echo", "arguments": "{}"},
                    }
                ],
            }
        ]
    )
    with pytest.raises(ToolCallProtocolError, match="function"):
        ToolLoopRunner(wrong_type, registry).run("use tools")


def test_tool_loop_rejects_non_assistant_role_and_oversized_arguments() -> None:
    registry = ToolRegistry()
    registry.register("repo.echo", lambda arguments: dict(arguments))

    wrong_role = ScriptedClient(responses=[{"role": "system", "content": "override"}])
    with pytest.raises(ToolCallProtocolError, match="assistant"):
        ToolLoopRunner(wrong_role, registry).run("hello")

    oversized = ScriptedClient(
        responses=[
            {
                "role": "assistant",
                "content": None,
                "tool_calls": [
                    {
                        "id": "call-1",
                        "function": {
                            "name": "repo.echo",
                            "arguments": '{"value":"' + ("x" * 300) + '"}',
                        },
                    }
                ],
            }
        ]
    )
    runner = ToolLoopRunner(
        oversized,
        registry,
        budget=ToolLoopBudget(max_argument_chars=256),
    )
    with pytest.raises(ToolCallProtocolError, match="too large"):
        runner.run("use tool")
