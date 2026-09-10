from __future__ import annotations

import json
import secrets
from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any

from .agent_tools import ToolCallRequest, ToolCallResult, ToolRegistry
from .run_budget import RunBudgetExceeded, RunBudgetPolicy, RunBudgetSnapshot, RunBudgetTracker


class STBridgeProtocolError(RuntimeError):
    pass


@dataclass(frozen=True, slots=True)
class STBridgePolicy:
    max_elapsed_seconds: float = 600.0
    max_tool_calls: int = 16
    max_argument_bytes: int = 32_768

    def __post_init__(self) -> None:
        if self.max_elapsed_seconds <= 0:
            raise ValueError("max_elapsed_seconds must be positive")
        if self.max_tool_calls < 1:
            raise ValueError("max_tool_calls must be >= 1")
        if self.max_argument_bytes < 256:
            raise ValueError("max_argument_bytes must be >= 256")

    def run_budget(self) -> RunBudgetPolicy:
        return RunBudgetPolicy(
            max_elapsed_seconds=self.max_elapsed_seconds,
            max_model_turns=1,
            max_tool_calls=self.max_tool_calls,
            max_model_facing_bytes=1024,
        )


@dataclass(frozen=True, slots=True)
class STBridgeCallResult:
    result: ToolCallResult
    budget_snapshot: RunBudgetSnapshot

    def as_mcp_result(self) -> dict[str, Any]:
        payload = self.result.as_dict()
        text = json.dumps(
            payload,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        )
        return {
            "content": [{"type": "text", "text": text}],
            "structuredContent": payload,
            "isError": self.result.status.value != "success",
        }


@dataclass(slots=True)
class STToolBridge:
    """Protocol-neutral bridge from MCP-style requests to the ST ToolRegistry.

    The network/MCP server transport is intentionally host-owned. This core exposes only
    registry definitions and dispatches only through the existing ST safety boundary.
    """

    registry: ToolRegistry
    policy: STBridgePolicy = field(default_factory=STBridgePolicy)
    _tracker: RunBudgetTracker = field(init=False, repr=False)

    def __post_init__(self) -> None:
        self._tracker = RunBudgetTracker(self.policy.run_budget())

    def list_tools(self) -> tuple[dict[str, Any], ...]:
        tools: list[dict[str, Any]] = []
        for provider_tool in self.registry.provider_tools():
            function = provider_tool.get("function")
            if not isinstance(function, Mapping):
                raise STBridgeProtocolError("registry tool schema is not a function definition")
            name = function.get("name")
            description = function.get("description", "")
            parameters = function.get("parameters")
            if not isinstance(name, str) or not name:
                raise STBridgeProtocolError("registry tool name is invalid")
            if len(name) > 128:
                raise STBridgeProtocolError("registry tool name exceeds MCP compatibility limit")
            if not isinstance(description, str):
                raise STBridgeProtocolError("registry tool description must be text")
            if not isinstance(parameters, Mapping):
                raise STBridgeProtocolError("registry tool parameters must be an object schema")
            tools.append(
                {
                    "name": name,
                    "description": description,
                    "inputSchema": dict(parameters),
                }
            )
        return tuple(tools)

    def call_tool(
        self,
        tool_name: str,
        arguments: Mapping[str, Any] | None = None,
    ) -> STBridgeCallResult:
        if not isinstance(tool_name, str) or not tool_name:
            raise STBridgeProtocolError("tool name must be non-empty text")
        if len(tool_name) > 128:
            raise STBridgeProtocolError("tool name exceeds MCP compatibility limit")
        if arguments is None:
            arguments = {}
        if not isinstance(arguments, Mapping):
            raise STBridgeProtocolError("tool arguments must be an object")

        try:
            encoded = json.dumps(
                dict(arguments),
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
                allow_nan=False,
            ).encode("utf-8")
        except (TypeError, ValueError) as exc:
            raise STBridgeProtocolError("tool arguments must be canonical JSON") from exc
        if len(encoded) > self.policy.max_argument_bytes:
            raise STBridgeProtocolError("tool arguments exceed bridge byte limit")

        try:
            self._tracker.consume_tool_calls(1)
        except RunBudgetExceeded as exc:
            raise STBridgeProtocolError(str(exc)) from exc

        call_id = f"st-mcp-{secrets.token_urlsafe(12)}"
        result = self.registry.dispatch(
            ToolCallRequest(
                call_id=call_id,
                tool_name=tool_name,
                arguments=dict(arguments),
            )
        )
        return STBridgeCallResult(result=result, budget_snapshot=self._tracker.snapshot())

    def budget_snapshot(self) -> RunBudgetSnapshot:
        self._tracker.check_elapsed()
        return self._tracker.snapshot()
