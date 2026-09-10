from __future__ import annotations

import json
import time
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any, Callable


class RunBudgetExceeded(RuntimeError):
    pass


@dataclass(frozen=True, slots=True)
class RunBudgetPolicy:
    max_elapsed_seconds: float = 600.0
    max_model_turns: int = 8
    max_tool_calls: int = 16
    max_model_facing_bytes: int = 2_000_000

    def __post_init__(self) -> None:
        if self.max_elapsed_seconds <= 0:
            raise ValueError("max_elapsed_seconds must be positive")
        if self.max_model_turns < 1:
            raise ValueError("max_model_turns must be >= 1")
        if self.max_tool_calls < 1:
            raise ValueError("max_tool_calls must be >= 1")
        if self.max_model_facing_bytes < 1024:
            raise ValueError("max_model_facing_bytes must be >= 1024")


@dataclass(frozen=True, slots=True)
class RunBudgetSnapshot:
    elapsed_seconds: float
    model_turns: int
    tool_calls: int
    model_facing_bytes: int


class RunBudgetTracker:
    """Per-run cumulative budget accounting independent from model behavior."""

    def __init__(
        self,
        policy: RunBudgetPolicy,
        *,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self.policy = policy
        self._clock = clock
        self._started_at = clock()
        self._model_turns = 0
        self._tool_calls = 0
        self._model_facing_bytes = 0

    def check_elapsed(self) -> None:
        if self._elapsed() > self.policy.max_elapsed_seconds:
            raise RunBudgetExceeded("run elapsed-time budget exceeded")

    def consume_model_turn(self) -> None:
        self.check_elapsed()
        if self._model_turns + 1 > self.policy.max_model_turns:
            raise RunBudgetExceeded("run model-turn budget exceeded")
        self._model_turns += 1

    def consume_tool_calls(self, count: int) -> None:
        if count < 0:
            raise ValueError("tool-call count must not be negative")
        self.check_elapsed()
        if self._tool_calls + count > self.policy.max_tool_calls:
            raise RunBudgetExceeded("run tool-call budget exceeded")
        self._tool_calls += count

    def consume_model_payload(
        self,
        messages: Sequence[Mapping[str, Any]],
        tools: Sequence[Mapping[str, Any]],
    ) -> int:
        self.check_elapsed()
        payload = {"messages": list(messages), "tools": list(tools)}
        try:
            encoded = json.dumps(
                payload,
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
                allow_nan=False,
            ).encode("utf-8")
        except (TypeError, ValueError) as exc:
            raise RunBudgetExceeded("model-facing payload is not canonical JSON") from exc
        size = len(encoded)
        if self._model_facing_bytes + size > self.policy.max_model_facing_bytes:
            raise RunBudgetExceeded("run model-facing byte budget exceeded")
        self._model_facing_bytes += size
        return size

    def snapshot(self) -> RunBudgetSnapshot:
        return RunBudgetSnapshot(
            elapsed_seconds=self._elapsed(),
            model_turns=self._model_turns,
            tool_calls=self._tool_calls,
            model_facing_bytes=self._model_facing_bytes,
        )

    def _elapsed(self) -> float:
        return max(0.0, self._clock() - self._started_at)
