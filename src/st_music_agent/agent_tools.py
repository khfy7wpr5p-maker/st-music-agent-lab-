from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from enum import Enum
from typing import Any

from .journal import RunJournal
from .output import OutputSanitizer

ToolHandler = Callable[[Mapping[str, Any]], Mapping[str, Any]]


class ToolCallStatus(str, Enum):
    SUCCESS = "success"
    REJECTED = "rejected"
    ERROR = "error"


@dataclass(frozen=True, slots=True)
class ToolDefinition:
    name: str
    description: str
    parameters: Mapping[str, Any]

    def as_openai_tool(self) -> dict[str, Any]:
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": dict(self.parameters),
            },
        }


@dataclass(frozen=True, slots=True)
class ToolCallRequest:
    call_id: str
    tool_name: str
    arguments: Mapping[str, Any]

    def __post_init__(self) -> None:
        if not self.call_id.strip():
            raise ValueError("call_id must not be empty")
        if not self.tool_name.strip():
            raise ValueError("tool_name must not be empty")


@dataclass(frozen=True, slots=True)
class ToolCallResult:
    call_id: str
    tool_name: str
    status: ToolCallStatus
    output: Mapping[str, Any]
    error: str | None = None

    def as_dict(self) -> dict[str, Any]:
        return {
            "call_id": self.call_id,
            "tool_name": self.tool_name,
            "status": self.status.value,
            "output": dict(self.output),
            "error": self.error,
        }


class ToolRegistry:
    """Explicit allowlist of ST-owned tool handlers and provider schemas."""

    def __init__(
        self,
        sanitizer: OutputSanitizer | None = None,
        journal: RunJournal | None = None,
    ) -> None:
        self._handlers: dict[str, ToolHandler] = {}
        self._definitions: dict[str, ToolDefinition] = {}
        self._sanitizer = sanitizer or OutputSanitizer()
        self._journal = journal

    def register(
        self,
        name: str,
        handler: ToolHandler,
        *,
        description: str = "",
        parameters: Mapping[str, Any] | None = None,
    ) -> None:
        if not name.strip():
            raise ValueError("tool name must not be empty")
        if name in self._handlers:
            raise ValueError(f"tool is already registered: {name}")
        schema = parameters or {"type": "object", "properties": {}}
        self._handlers[name] = handler
        self._definitions[name] = ToolDefinition(name, description, schema)

    def dispatch(self, request: ToolCallRequest) -> ToolCallResult:
        self._record(
            "tool_call_requested",
            {
                "call_id": request.call_id,
                "tool_name": request.tool_name,
                "arguments": dict(request.arguments),
            },
        )

        handler = self._handlers.get(request.tool_name)
        if handler is None:
            result = ToolCallResult(
                call_id=request.call_id,
                tool_name=request.tool_name,
                status=ToolCallStatus.REJECTED,
                output={},
                error="unknown or unregistered tool",
            )
            self._record("tool_call_completed", result.as_dict())
            return result

        try:
            raw_output = handler(request.arguments)
            sanitized_output = self._sanitizer.sanitize_value(raw_output)
            if not isinstance(sanitized_output, dict):
                raise TypeError("tool handler output must be a mapping")
            result = ToolCallResult(
                call_id=request.call_id,
                tool_name=request.tool_name,
                status=ToolCallStatus.SUCCESS,
                output=sanitized_output,
            )
        except Exception as exc:  # noqa: BLE001 - boundary must contain handler failures
            result = ToolCallResult(
                call_id=request.call_id,
                tool_name=request.tool_name,
                status=ToolCallStatus.ERROR,
                output={},
                error=self._sanitizer.sanitize_text(str(exc)),
            )

        self._record("tool_call_completed", result.as_dict())
        return result

    def names(self) -> tuple[str, ...]:
        return tuple(sorted(self._handlers))

    def provider_tools(self) -> tuple[dict[str, Any], ...]:
        return tuple(
            self._definitions[name].as_openai_tool()
            for name in sorted(self._definitions)
        )

    def _record(self, event_type: str, payload: Mapping[str, Any]) -> None:
        if self._journal is not None:
            self._journal.append(event_type, payload)
