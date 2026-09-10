from __future__ import annotations

import pytest

from st_music_agent.run_budget import RunBudgetExceeded, RunBudgetPolicy, RunBudgetTracker


class FakeClock:
    def __init__(self) -> None:
        self.value = 100.0

    def __call__(self) -> float:
        return self.value

    def advance(self, seconds: float) -> None:
        self.value += seconds


def test_tracker_counts_turns_tools_bytes_and_elapsed() -> None:
    clock = FakeClock()
    tracker = RunBudgetTracker(
        RunBudgetPolicy(
            max_elapsed_seconds=30.0,
            max_model_turns=3,
            max_tool_calls=4,
            max_model_facing_bytes=4096,
        ),
        clock=clock,
    )

    tracker.consume_model_turn()
    tracker.consume_tool_calls(2)
    charged = tracker.consume_model_payload(
        [{"role": "user", "content": "hello"}],
        [{"type": "function", "function": {"name": "tool", "parameters": {}}}],
    )
    clock.advance(2.5)

    snapshot = tracker.snapshot()
    assert charged > 0
    assert snapshot.model_turns == 1
    assert snapshot.tool_calls == 2
    assert snapshot.model_facing_bytes == charged
    assert snapshot.elapsed_seconds == 2.5


def test_turn_and_tool_budgets_fail_before_counter_overflow() -> None:
    tracker = RunBudgetTracker(
        RunBudgetPolicy(max_model_turns=1, max_tool_calls=1, max_model_facing_bytes=4096)
    )

    tracker.consume_model_turn()
    tracker.consume_tool_calls(1)
    with pytest.raises(RunBudgetExceeded, match="model-turn"):
        tracker.consume_model_turn()
    with pytest.raises(RunBudgetExceeded, match="tool-call"):
        tracker.consume_tool_calls(1)

    snapshot = tracker.snapshot()
    assert snapshot.model_turns == 1
    assert snapshot.tool_calls == 1


def test_model_facing_byte_budget_is_cumulative() -> None:
    tracker = RunBudgetTracker(
        RunBudgetPolicy(max_model_facing_bytes=1024, max_model_turns=4, max_tool_calls=4)
    )
    messages = [{"role": "user", "content": "x" * 500}]

    first = tracker.consume_model_payload(messages, [])
    assert first < 1024
    with pytest.raises(RunBudgetExceeded, match="byte budget"):
        tracker.consume_model_payload(messages, [])

    assert tracker.snapshot().model_facing_bytes == first


def test_elapsed_budget_uses_monotonic_clock_and_fails_closed() -> None:
    clock = FakeClock()
    tracker = RunBudgetTracker(
        RunBudgetPolicy(max_elapsed_seconds=5.0, max_model_facing_bytes=4096),
        clock=clock,
    )
    clock.advance(5.01)

    with pytest.raises(RunBudgetExceeded, match="elapsed-time"):
        tracker.check_elapsed()
    with pytest.raises(RunBudgetExceeded, match="elapsed-time"):
        tracker.consume_model_turn()
