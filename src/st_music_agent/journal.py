from __future__ import annotations

import hashlib
import json
import os
import threading
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .output import OutputSanitizer


class JournalIntegrityError(RuntimeError):
    pass


@dataclass(frozen=True, slots=True)
class JournalEvent:
    sequence: int
    run_id: str
    event_type: str
    timestamp: str
    payload: Any
    previous_hash: str
    event_hash: str

    def as_dict(self) -> dict[str, Any]:
        return {
            "sequence": self.sequence,
            "run_id": self.run_id,
            "event_type": self.event_type,
            "timestamp": self.timestamp,
            "payload": self.payload,
            "previous_hash": self.previous_hash,
            "event_hash": self.event_hash,
        }


class RunJournal:
    """Process-local append-only JSONL journal with a SHA-256 hash chain."""

    def __init__(
        self,
        path: Path,
        run_id: str,
        sanitizer: OutputSanitizer | None = None,
    ) -> None:
        if not run_id.strip():
            raise ValueError("run_id must not be empty")
        self.path = path
        self.run_id = run_id
        self.sanitizer = sanitizer or OutputSanitizer()
        self._lock = threading.Lock()
        self._sequence = 0
        self._previous_hash = ""
        self.path.parent.mkdir(parents=True, exist_ok=True)
        if self.path.exists():
            self._verify_existing()

    def append(self, event_type: str, payload: Any) -> JournalEvent:
        if not event_type.strip():
            raise ValueError("event_type must not be empty")
        sanitized_payload = self.sanitizer.sanitize_value(payload)

        with self._lock:
            sequence = self._sequence + 1
            base = {
                "sequence": sequence,
                "run_id": self.run_id,
                "event_type": event_type,
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "payload": sanitized_payload,
                "previous_hash": self._previous_hash,
            }
            event_hash = self._hash_record(base)
            event = JournalEvent(event_hash=event_hash, **base)
            line = self._canonical_json(event.as_dict())
            with self.path.open("a", encoding="utf-8") as handle:
                handle.write(f"{line}\n")
                handle.flush()
                os.fsync(handle.fileno())
            self._sequence = sequence
            self._previous_hash = event_hash
            return event

    def read_events(self) -> tuple[JournalEvent, ...]:
        if not self.path.exists():
            return ()
        events: list[JournalEvent] = []
        with self.path.open("r", encoding="utf-8") as handle:
            for line_number, line in enumerate(handle, start=1):
                if not line.strip():
                    raise JournalIntegrityError(f"blank journal line at {line_number}")
                record = self._decode_record(line, line_number)
                events.append(self._event_from_record(record, line_number))
        return tuple(events)

    def _verify_existing(self) -> None:
        previous_hash = ""
        expected_sequence = 1
        events = self.read_events()
        for event in events:
            if event.run_id != self.run_id:
                raise JournalIntegrityError("journal run_id does not match requested run")
            if event.sequence != expected_sequence:
                raise JournalIntegrityError("journal sequence is not contiguous")
            if event.previous_hash != previous_hash:
                raise JournalIntegrityError("journal hash chain is broken")
            base = {
                "sequence": event.sequence,
                "run_id": event.run_id,
                "event_type": event.event_type,
                "timestamp": event.timestamp,
                "payload": event.payload,
                "previous_hash": event.previous_hash,
            }
            if event.event_hash != self._hash_record(base):
                raise JournalIntegrityError("journal event hash does not verify")
            previous_hash = event.event_hash
            expected_sequence += 1

        self._sequence = len(events)
        self._previous_hash = previous_hash

    @classmethod
    def _hash_record(cls, record: dict[str, Any]) -> str:
        encoded = cls._canonical_json(record).encode("utf-8")
        return hashlib.sha256(encoded).hexdigest()

    @staticmethod
    def _canonical_json(record: dict[str, Any]) -> str:
        return json.dumps(
            record,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        )

    @staticmethod
    def _decode_record(line: str, line_number: int) -> dict[str, Any]:
        try:
            record = json.loads(line)
        except json.JSONDecodeError as exc:
            raise JournalIntegrityError(f"invalid JSON at journal line {line_number}") from exc
        if not isinstance(record, dict):
            raise JournalIntegrityError(f"journal line {line_number} is not an object")
        return record

    @staticmethod
    def _event_from_record(record: dict[str, Any], line_number: int) -> JournalEvent:
        required = {
            "sequence",
            "run_id",
            "event_type",
            "timestamp",
            "payload",
            "previous_hash",
            "event_hash",
        }
        if set(record) != required:
            raise JournalIntegrityError(f"journal line {line_number} has an invalid schema")
        try:
            return JournalEvent(
                sequence=int(record["sequence"]),
                run_id=str(record["run_id"]),
                event_type=str(record["event_type"]),
                timestamp=str(record["timestamp"]),
                payload=record["payload"],
                previous_hash=str(record["previous_hash"]),
                event_hash=str(record["event_hash"]),
            )
        except (TypeError, ValueError) as exc:
            raise JournalIntegrityError(f"journal line {line_number} has invalid field types") from exc
