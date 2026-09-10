import json
from pathlib import Path

import pytest

from st_music_agent.journal import JournalIntegrityError, RunJournal
from st_music_agent.output import OutputSanitizer


def test_journal_appends_and_resumes_verified_chain(tmp_path: Path) -> None:
    path = tmp_path / "run.jsonl"
    journal = RunJournal(path, run_id="run-1")

    first = journal.append("task_started", {"task": "inspect"})
    second = journal.append("tool_call_completed", {"status": "ok"})

    assert first.sequence == 1
    assert first.previous_hash == ""
    assert second.sequence == 2
    assert second.previous_hash == first.event_hash

    resumed = RunJournal(path, run_id="run-1")
    third = resumed.append("task_completed", {"status": "done"})

    assert third.sequence == 3
    assert third.previous_hash == second.event_hash
    assert len(resumed.read_events()) == 3


def test_journal_redacts_payload_before_persistence(tmp_path: Path) -> None:
    path = tmp_path / "run.jsonl"
    journal = RunJournal(
        path,
        run_id="run-1",
        sanitizer=OutputSanitizer(sensitive_values=("private-value",)),
    )

    journal.append(
        "tool_call",
        {
            "api_key": "private-value",
            "message": "Bearer abcdefghijklmnop",
        },
    )

    raw = path.read_text(encoding="utf-8")
    assert "private-value" not in raw
    assert "abcdefghijklmnop" not in raw
    assert "[REDACTED]" in raw


def test_journal_detects_payload_tampering(tmp_path: Path) -> None:
    path = tmp_path / "run.jsonl"
    journal = RunJournal(path, run_id="run-1")
    journal.append("task_started", {"task": "inspect"})

    record = json.loads(path.read_text(encoding="utf-8"))
    record["payload"]["task"] = "tampered"
    path.write_text(json.dumps(record) + "\n", encoding="utf-8")

    with pytest.raises(JournalIntegrityError, match="hash"):
        RunJournal(path, run_id="run-1")


def test_journal_rejects_wrong_run_id(tmp_path: Path) -> None:
    path = tmp_path / "run.jsonl"
    RunJournal(path, run_id="run-1").append("task_started", {})

    with pytest.raises(JournalIntegrityError, match="run_id"):
        RunJournal(path, run_id="run-2")
