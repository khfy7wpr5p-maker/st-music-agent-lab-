from pathlib import Path

import pytest

from st_music_agent.agent_tools import (
    ToolCallRequest,
    ToolCallStatus,
    ToolRegistry,
)
from st_music_agent.journal import RunJournal
from st_music_agent.output import OutputSanitizer


def test_registered_tool_executes_and_output_is_sanitized() -> None:
    registry = ToolRegistry(sanitizer=OutputSanitizer(sensitive_values=("private-value",)))
    registry.register(
        "repo.inspect",
        lambda arguments: {
            "path": arguments["path"],
            "token": "private-value",
            "message": "ok",
        },
    )

    result = registry.dispatch(
        ToolCallRequest(
            call_id="call-1",
            tool_name="repo.inspect",
            arguments={"path": "README.md"},
        )
    )

    assert result.status is ToolCallStatus.SUCCESS
    assert result.output == {
        "path": "README.md",
        "token": "[REDACTED]",
        "message": "ok",
    }


def test_unknown_tool_is_rejected_without_dynamic_execution() -> None:
    registry = ToolRegistry()

    result = registry.dispatch(
        ToolCallRequest(call_id="call-1", tool_name="os.system", arguments={"cmd": "id"})
    )

    assert result.status is ToolCallStatus.REJECTED
    assert result.output == {}
    assert result.error == "unknown or unregistered tool"


def test_duplicate_registration_is_rejected() -> None:
    registry = ToolRegistry()
    registry.register("repo.inspect", lambda arguments: dict(arguments))

    with pytest.raises(ValueError, match="already registered"):
        registry.register("repo.inspect", lambda arguments: dict(arguments))


def test_handler_exception_is_sanitized_without_traceback() -> None:
    registry = ToolRegistry(sanitizer=OutputSanitizer(sensitive_values=("private-value",)))

    def broken_handler(arguments: object) -> dict[str, object]:
        del arguments
        raise RuntimeError("provider failed with token=private-value")

    registry.register("repo.inspect", broken_handler)
    result = registry.dispatch(
        ToolCallRequest(call_id="call-1", tool_name="repo.inspect", arguments={})
    )

    assert result.status is ToolCallStatus.ERROR
    assert result.error is not None
    assert "private-value" not in result.error
    assert "Traceback" not in result.error


def test_tool_calls_are_recorded_in_verified_journal(tmp_path: Path) -> None:
    journal = RunJournal(tmp_path / "run.jsonl", run_id="run-1")
    registry = ToolRegistry(journal=journal)
    registry.register("repo.inspect", lambda arguments: {"path": arguments["path"]})

    registry.dispatch(
        ToolCallRequest(
            call_id="call-1",
            tool_name="repo.inspect",
            arguments={"path": "README.md"},
        )
    )

    events = journal.read_events()
    assert [event.event_type for event in events] == [
        "tool_call_requested",
        "tool_call_completed",
    ]
    assert events[0].payload["tool_name"] == "repo.inspect"
    assert events[1].payload["status"] == "success"
