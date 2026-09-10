from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any, Protocol

from .agent_tools import ToolCallRequest, ToolRegistry
from .journal import RunJournal
from .output import OutputSanitizer


class ToolCallProtocolError(RuntimeError):
    pass


class ToolLoopBudgetExceeded(RuntimeError):
    pass


class ToolCallingClient(Protocol):
    def complete_with_tools(
        self,
        messages: Sequence[Mapping[str, Any]],
        tools: Sequence[Mapping[str, Any]],
    ) -> Mapping[str, Any]: ...


@dataclass(frozen=True, slots=True)
class ToolLoopBudget:
    max_turns: int = 8
    max_tool_calls: int = 16
    max_argument_chars: int = 32_768
    max_call_id_chars: int = 256
    max_tool_name_chars: int = 128

    def __post_init__(self) -> None:
        if self.max_turns < 1:
            raise ValueError("max_turns must be >= 1")
        if self.max_tool_calls < 1:
            raise ValueError("max_tool_calls must be >= 1")
        if self.max_argument_chars < 256:
            raise ValueError("max_argument_chars must be >= 256")
        if self.max_call_id_chars < 8:
            raise ValueError("max_call_id_chars must be >= 8")
        if self.max_tool_name_chars < 8:
            raise ValueError("max_tool_name_chars must be >= 8")


@dataclass(frozen=True, slots=True)
class ToolLoopResult:
    final_message: Mapping[str, Any]
    turns: int
    tool_calls: int


@dataclass(slots=True)
class ToolLoopRunner:
    client: ToolCallingClient
    registry: ToolRegistry
    budget: ToolLoopBudget = field(default_factory=ToolLoopBudget)
    sanitizer: OutputSanitizer = field(default_factory=OutputSanitizer)
    journal: RunJournal | None = None

    def run(self, instruction: str) -> ToolLoopResult:
        if not instruction.strip():
            raise ValueError("instruction must not be empty")

        messages: list[Mapping[str, Any]] = [{"role": "user", "content": instruction}]
        tool_call_count = 0
        provider_tools = self.registry.provider_tools()

        for turn in range(1, self.budget.max_turns + 1):
            self._record("model_turn_started", {"turn": turn})
            raw_message = self.client.complete_with_tools(messages, provider_tools)
            history_message = self._history_message(raw_message)
            tool_calls = self._parse_tool_calls(history_message)
            self._record(
                "model_turn_completed",
                {
                    "turn": turn,
                    "tool_call_count": len(tool_calls),
                    "has_content": history_message.get("content") is not None,
                },
            )

            if not tool_calls:
                final_message = self._public_message(history_message)
                self._record(
                    "agent_completed",
                    {"turns": turn, "tool_calls": tool_call_count},
                )
                return ToolLoopResult(
                    final_message=final_message,
                    turns=turn,
                    tool_calls=tool_call_count,
                )

            if tool_call_count + len(tool_calls) > self.budget.max_tool_calls:
                raise ToolLoopBudgetExceeded("tool-call budget would be exceeded")

            messages.append(history_message)
            for request in tool_calls:
                result = self.registry.dispatch(request)
                tool_call_count += 1
                messages.append(
                    {
                        "role": "tool",
                        "tool_call_id": request.call_id,
                        "content": json.dumps(
                            result.as_dict(),
                            ensure_ascii=False,
                            sort_keys=True,
                            separators=(",", ":"),
                        ),
                    }
                )

        raise ToolLoopBudgetExceeded("model-turn budget was exhausted")

    def _history_message(self, message: Mapping[str, Any]) -> dict[str, Any]:
        role = message.get("role", "assistant")
        if role != "assistant":
            raise ToolCallProtocolError("provider message role must be assistant")

        history: dict[str, Any] = {
            "role": "assistant",
            "content": message.get("content"),
        }
        if "reasoning_content" in message:
            reasoning_content = message.get("reasoning_content")
            if reasoning_content is not None and not isinstance(reasoning_content, str):
                raise ToolCallProtocolError("reasoning_content must be text when provided")
            history["reasoning_content"] = reasoning_content
        if "tool_calls" in message:
            history["tool_calls"] = self._canonical_tool_calls(message.get("tool_calls"))
        return history

    def _canonical_tool_calls(self, raw_calls: Any) -> list[dict[str, Any]]:
        if not isinstance(raw_calls, list):
            raise ToolCallProtocolError("assistant tool_calls must be a list")

        canonical: list[dict[str, Any]] = []
        seen_ids: set[str] = set()
        for raw_call in raw_calls:
            if not isinstance(raw_call, Mapping):
                raise ToolCallProtocolError("tool call must be an object")
            call_id = raw_call.get("id")
            if not isinstance(call_id, str) or not call_id:
                raise ToolCallProtocolError("tool call id is missing")
            if len(call_id) > self.budget.max_call_id_chars:
                raise ToolCallProtocolError("tool call id is too long")
            if call_id in seen_ids:
                raise ToolCallProtocolError("tool call ids must be unique within a turn")
            seen_ids.add(call_id)

            call_type = raw_call.get("type", "function")
            if call_type != "function":
                raise ToolCallProtocolError("only function tool calls are supported")
            function = raw_call.get("function")
            if not isinstance(function, Mapping):
                raise ToolCallProtocolError("tool call function is missing")
            name = function.get("name")
            if not isinstance(name, str) or not name:
                raise ToolCallProtocolError("tool call function name is missing")
            if len(name) > self.budget.max_tool_name_chars:
                raise ToolCallProtocolError("tool call function name is too long")

            arguments = self._parse_arguments(function.get("arguments"))
            argument_text = json.dumps(
                dict(arguments),
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
            )
            canonical.append(
                {
                    "id": call_id,
                    "type": "function",
                    "function": {"name": name, "arguments": argument_text},
                }
            )
        return canonical

    def _parse_tool_calls(self, message: Mapping[str, Any]) -> tuple[ToolCallRequest, ...]:
        raw_calls = message.get("tool_calls")
        if raw_calls is None:
            return ()
        if not isinstance(raw_calls, list):
            raise ToolCallProtocolError("assistant tool_calls must be a list")

        parsed: list[ToolCallRequest] = []
        for raw_call in raw_calls:
            function = raw_call["function"]
            parsed.append(
                ToolCallRequest(
                    call_id=raw_call["id"],
                    tool_name=function["name"],
                    arguments=self._parse_arguments(function["arguments"]),
                )
            )
        return tuple(parsed)

    def _parse_arguments(self, raw_arguments: Any) -> Mapping[str, Any]:
        if isinstance(raw_arguments, Mapping):
            try:
                encoded = json.dumps(raw_arguments, ensure_ascii=False, separators=(",", ":"))
            except (TypeError, ValueError) as exc:
                raise ToolCallProtocolError("tool call arguments must be JSON-serializable") from exc
            if len(encoded) > self.budget.max_argument_chars:
                raise ToolCallProtocolError("tool call arguments are too large")
            return dict(raw_arguments)
        if not isinstance(raw_arguments, str):
            raise ToolCallProtocolError("tool call arguments must be JSON text or an object")
        if len(raw_arguments) > self.budget.max_argument_chars:
            raise ToolCallProtocolError("tool call arguments are too large")
        try:
            decoded = json.loads(raw_arguments)
        except json.JSONDecodeError as exc:
            raise ToolCallProtocolError("tool call arguments contain invalid JSON") from exc
        if not isinstance(decoded, dict):
            raise ToolCallProtocolError("tool call arguments JSON must decode to an object")
        return decoded

    def _public_message(self, message: Mapping[str, Any]) -> Mapping[str, Any]:
        public = {"role": "assistant", "content": message.get("content")}
        sanitized = self.sanitizer.sanitize_value(public)
        if not isinstance(sanitized, dict):
            raise ToolCallProtocolError("assistant message must sanitize to an object")
        return sanitized

    def _record(self, event_type: str, payload: Mapping[str, Any]) -> None:
        if self.journal is not None:
            self.journal.append(event_type, payload)
