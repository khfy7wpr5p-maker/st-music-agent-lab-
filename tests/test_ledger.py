import unittest
from datetime import datetime, timezone

from st_music_agent_lab import Action, RunLedger, RunState, TaskSpec


class RunLedgerTests(unittest.TestCase):
    def test_ledger_is_structured_and_finalizes_once(self) -> None:
        task = TaskSpec(
            task_id="a1-ledger",
            objective="record evidence",
            target_repository="fixture/repo",
            capabilities=frozenset({Action.PRODUCE_REPORTS}),
        )
        fixed = datetime(2026, 9, 10, 20, 0, tzinfo=timezone.utc)
        ledger = RunLedger("run-001", task, clock=lambda: fixed)
        ledger.record("policy", "PASS", {"action": "produce_reports"})
        ledger.finalize(RunState.SUCCEEDED)
        payload = ledger.to_dict()
        self.assertEqual("SUCCEEDED", payload["final_state"])
        self.assertEqual("2026-09-10T20:00:00+00:00", payload["events"][0]["timestamp"])
        with self.assertRaises(RuntimeError):
            ledger.finalize(RunState.BLOCKED)


if __name__ == "__main__":
    unittest.main()
