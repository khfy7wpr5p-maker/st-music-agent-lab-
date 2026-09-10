import tempfile
import unittest
from pathlib import Path

from st_music_agent_lab import Action, SandboxRunner, TaskSpec


class SandboxRunnerTests(unittest.TestCase):
    def _task(self, command, retry_budget=0):
        return TaskSpec(
            task_id="a3-sandbox",
            objective="execute deterministic fixture tests",
            target_repository="fixture/repo",
            capabilities=frozenset({Action.RUN_BOUNDED_SANDBOX_TESTS}),
            allowed_commands=(tuple(command),),
            timeout_seconds=10,
            retry_budget=retry_budget,
        )

    def test_python_unittest_fixture_runs(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "test_fixture.py").write_text(
                "import unittest\n\nclass T(unittest.TestCase):\n    def test_ok(self): self.assertEqual(4, 2 + 2)\n",
                encoding="utf-8",
            )
            command = ("python", "-m", "unittest", "discover", "-s", ".")
            result = SandboxRunner().execute(self._task(command), root, command)
            self.assertTrue(result.succeeded, result.stderr)

    def test_arbitrary_python_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            command = ("python", "-c", "print('unsafe')")
            result = SandboxRunner().execute(self._task(command), Path(tmp), command)
            self.assertFalse(result.allowed)

    def test_non_granted_command_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            granted = ("python", "-m", "unittest", "discover")
            attempted = ("node", "--test")
            result = SandboxRunner().execute(self._task(granted), Path(tmp), attempted)
            self.assertFalse(result.allowed)

    def test_retry_budget_is_enforced(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            command = ("python", "-m", "unittest", "discover")
            result = SandboxRunner().execute(self._task(command, retry_budget=1), Path(tmp), command, attempt=2)
            self.assertFalse(result.allowed)
            self.assertIn("retry budget", result.reason)

    def test_secret_redaction(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "test_fixture.py").write_text(
                "import unittest\n\nclass T(unittest.TestCase):\n    def test_ok(self): print('TOKEN-123')\n",
                encoding="utf-8",
            )
            command = ("python", "-m", "unittest", "discover", "-s", ".")
            result = SandboxRunner().execute(self._task(command), root, command, secrets=("TOKEN-123",))
            self.assertNotIn("TOKEN-123", result.stdout)
            self.assertIn("***REDACTED***", result.stdout)


if __name__ == "__main__":
    unittest.main()
