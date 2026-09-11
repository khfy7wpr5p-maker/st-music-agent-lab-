from __future__ import annotations

from collections.abc import Mapping
from typing import Any

import pytest

from st_music_agent.agent_tools import ToolCallStatus, ToolRegistry
from st_music_agent.openhands_bridge import (
    STBridgePolicy,
    STBridgeProtocolError,
    STToolBridge,
)


def registry_with_echo() -> ToolRegistry:
    registry = ToolRegistry()
    registry.register(
        "repo.echo",
        lambda arguments: {"value": arguments["value"]},
        description="Echo one value.",
        parameters={
            "type": "object",
            "properties": {"value": {"type": "string"}},
            "required": ["value"],
            "additionalProperties": False,
        },
    )
    return registry


def test_bridge_exports_mcp_style_tools_from_registry_only() -> None:
    bridge = STToolBridge(registry_with_echo())

    assert bridge.list_tools() == (
        {
            "name": "repo.echo",
            "description": "Echo one value.",
            "inputSchema": {
                "type": "object",
                "properties": {"value": {"type": "string"}},
                "required": ["value"],
                "additionalProperties": False,
            },
        },
    )


def test_bridge_dispatches_through_registry_and_returns_mcp_projection() -> None:
    bridge = STToolBridge(registry_with_echo())

    result = bridge.call_tool("repo.echo", {"value": "hello"})

    assert result.result.status is ToolCallStatus.SUCCESS
    assert result.result.output == {"value": "hello"}
    assert result.budget_snapshot.tool_calls == 1
    mcp_result = result.as_mcp_result()
    assert mcp_result["isError"] is False
    assert mcp_result["structuredContent"]["output"] == {"value": "hello"}
    assert mcp_result["content"][0]["type"] == "text"


def test_bridge_unknown_tool_is_rejected_by_registry_not_dynamic_resolution() -> None:
    bridge = STToolBridge(registry_with_echo())

    result = bridge.call_tool("os.system", {"command": "rm -rf /"})

    assert result.result.status is ToolCallStatus.REJECTED
    assert result.result.error == "unknown or unregistered tool"
    assert result.as_mcp_result()["isError"] is True


def test_bridge_argument_size_fails_before_handler_execution() -> None:
    calls = 0

    def handler(arguments: Mapping[str, Any]) -> Mapping[str, Any]:
        nonlocal calls
        calls += 1
        return dict(arguments)

    registry = ToolRegistry()
    registry.register("repo.echo", handler)
    bridge = STToolBridge(registry, STBridgePolicy(max_argument_bytes=256))

    with pytest.raises(STBridgeProtocolError, match="byte limit"):
        bridge.call_tool("repo.echo", {"value": "x" * 400})

    assert calls == 0
    assert bridge.budget_snapshot().tool_calls == 0


def test_bridge_tool_call_budget_fails_before_extra_dispatch() -> None:
    calls = 0

    def handler(arguments: Mapping[str, Any]) -> Mapping[str, Any]:
        nonlocal calls
        calls += 1
        return dict(arguments)

    registry = ToolRegistry()
    registry.register("repo.echo", handler)
    bridge = STToolBridge(registry, STBridgePolicy(max_tool_calls=1))

    bridge.call_tool("repo.echo", {})
    with pytest.raises(STBridgeProtocolError, match="tool-call budget"):
        bridge.call_tool("repo.echo", {})

    assert calls == 1


def test_bridge_rejects_non_mcp_compatible_registry_tool_names() -> None:
    registry = ToolRegistry()
    registry.register("bad tool", lambda arguments: dict(arguments))
    bridge = STToolBridge(registry)

    with pytest.raises(STBridgeProtocolError, match="MCP-compatible"):
        bridge.list_tools()
    with pytest.raises(STBridgeProtocolError, match="MCP-compatible"):
        bridge.call_tool("bad tool", {})


def test_bridge_keeps_registry_output_sanitization() -> None:
    registry = ToolRegistry()
    registry.register(
        "repo.secret_probe",
        lambda arguments: {"api_key": "secret-value", "safe": "ok"},
    )
    bridge = STToolBridge(registry)

    result = bridge.call_tool("repo.secret_probe", {})

    assert result.result.output["api_key"] == "[REDACTED]"
    assert result.result.output["safe"] == "ok"
