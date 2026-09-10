from __future__ import annotations

import os
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Sequence

from .models import Action, ActionRequest, TaskSpec
from .policy import PolicyEngine

SAFE_TEST_PREFIXES: tuple[tuple[str, ...], ...] = (
    ("python", "-m", "unittest"),
    ("python3", "-m", "unittest"),
    ("python", "-m", "pytest"),
    ("python3", "-m", "pytest"),
    ("node", "--test"),
)


@dataclass(frozen=True, slots=True)
class SandboxResult:
    command: tuple[str, ...]
    attempt: int
    returncode: int | None
    stdout: str
    stderr: str
    timed_out: bool
    allowed: bool
    reason: str

    @property
    def succeeded(self) -> bool:
        return self.allowed and not self.timed_out and self.returncode == 0


class SandboxRunner:
    """Execute only explicitly granted test commands in an isolated workspace."""

    def __init__(self, policy: PolicyEngine | None = None, max_output_bytes: int = 200_000) -> None:
        self.policy = policy or PolicyEngine()
        self.max_output_bytes = max_output_bytes

    def execute(
        self,
        task: TaskSpec,
        workspace: Path,
        command: Sequence[str],
        *,
        attempt: int = 0,
        secrets: Iterable[str] = (),
    ) -> SandboxResult:
        argv = tuple(command)
        decision = self.policy.evaluate(task, ActionRequest(Action.RUN_BOUNDED_SANDBOX_TESTS))
        if not decision.allowed:
            return self._denied(argv, attempt, decision.reason)
        if attempt < 0 or attempt > task.retry_budget:
            return self._denied(argv, attempt, "retry budget exceeded")
        if argv not in task.allowed_commands:
            return self._denied(argv, attempt, "command is not explicitly granted by TaskSpec")
        if not self._has_safe_test_prefix(argv):
            return self._denied(argv, attempt, "command is outside the bounded test-command allowlist")

        root = workspace.resolve(strict=True)
        if not root.is_dir():
            return self._denied(argv, attempt, "workspace must be a directory")

        env = self._sanitized_environment()
        try:
            completed = subprocess.run(
                argv,
                cwd=root,
                env=env,
                text=True,
                capture_output=True,
                timeout=task.timeout_seconds,
                check=False,
                shell=False,
            )
            stdout = self._sanitize(completed.stdout, secrets)
            stderr = self._sanitize(completed.stderr, secrets)
            return SandboxResult(
                command=argv,
                attempt=attempt,
                returncode=completed.returncode,
                stdout=self._truncate(stdout),
                stderr=self._truncate(stderr),
                timed_out=False,
                allowed=True,
                reason="bounded command executed",
            )
        except subprocess.TimeoutExpired as exc:
            stdout = self._sanitize(_to_text(exc.stdout), secrets)
            stderr = self._sanitize(_to_text(exc.stderr), secrets)
            return SandboxResult(
                command=argv,
                attempt=attempt,
                returncode=None,
                stdout=self._truncate(stdout),
                stderr=self._truncate(stderr),
                timed_out=True,
                allowed=True,
                reason="command timed out within configured sandbox budget",
            )

    def _denied(self, command: tuple[str, ...], attempt: int, reason: str) -> SandboxResult:
        return SandboxResult(command, attempt, None, "", "", False, False, reason)

    @staticmethod
    def _has_safe_test_prefix(command: tuple[str, ...]) -> bool:
        return any(command[: len(prefix)] == prefix for prefix in SAFE_TEST_PREFIXES)

    @staticmethod
    def _sanitized_environment() -> dict[str, str]:
        allowed_names = ("PATH", "SYSTEMROOT", "WINDIR", "TMP", "TEMP")
        env = {name: os.environ[name] for name in allowed_names if name in os.environ}
        env["PYTHONIOENCODING"] = "utf-8"
        env["PYTHONUNBUFFERED"] = "1"
        return env

    @staticmethod
    def _sanitize(text: str, secrets: Iterable[str]) -> str:
        clean = text
        for secret in secrets:
            if secret:
                clean = clean.replace(secret, "***REDACTED***")
        return clean

    def _truncate(self, text: str) -> str:
        encoded = text.encode("utf-8", errors="replace")
        if len(encoded) <= self.max_output_bytes:
            return text
        return encoded[: self.max_output_bytes].decode("utf-8", errors="ignore") + "\n...[truncated]"


def _to_text(value: str | bytes | None) -> str:
    if value is None:
        return ""
    if isinstance(value, bytes):
        return value.decode("utf-8", errors="replace")
    return value
