from pathlib import Path

import pytest

from st_music_agent.commands import (
    GuardedCommandRunner,
    ProcessExecutionDisabledError,
    UnsupportedCommandError,
)
from st_music_agent.contracts import RiskLevel
from st_music_agent.sandbox import SandboxResult


class RecordingSandbox:
    def __init__(self) -> None:
        self.calls: list[tuple[tuple[str, ...], Path, float, bool]] = []

    def execute(
        self,
        argv: tuple[str, ...],
        workspace_root: Path,
        timeout_seconds: float,
        *,
        workspace_writable: bool,
    ) -> SandboxResult:
        self.calls.append((argv, workspace_root, timeout_seconds, workspace_writable))
        return SandboxResult(returncode=0, stdout="passed", stderr="")


def test_process_execution_requires_sandbox_backend(tmp_path: Path) -> None:
    runner = GuardedCommandRunner(root=tmp_path, branch="feature/test")

    with pytest.raises(ProcessExecutionDisabledError):
        runner.run(("git", "status", "--short"))


def test_classifier_allows_read_only_git_and_validation_commands(tmp_path: Path) -> None:
    runner = GuardedCommandRunner(root=tmp_path, branch="feature/test")

    assert runner.classify(("git", "status", "--short")) is RiskLevel.READ_ONLY
    assert runner.classify(("git", "diff", "--stat")) is RiskLevel.READ_ONLY
    assert runner.classify(("pytest", "-q")) is RiskLevel.REVERSIBLE_WRITE
    assert runner.classify(("ruff", "check", "src")) is RiskLevel.REVERSIBLE_WRITE
    assert runner.classify(("python", "-m", "pytest", "-q")) is RiskLevel.REVERSIBLE_WRITE


def test_classifier_rejects_side_effect_or_escape_git_flags(tmp_path: Path) -> None:
    runner = GuardedCommandRunner(root=tmp_path, branch="feature/test")

    for command in (
        ("git", "diff", "--output=/tmp/leak"),
        ("git", "diff", "--ext-diff"),
        ("git", "diff", "--no-index", "/etc/passwd", "README.md"),
        ("git", "show", "--textconv"),
    ):
        with pytest.raises(UnsupportedCommandError):
            runner.classify(command)


def test_classifier_rejects_arbitrary_shell_or_python(tmp_path: Path) -> None:
    runner = GuardedCommandRunner(root=tmp_path, branch="feature/test")

    with pytest.raises(UnsupportedCommandError):
        runner.classify(("bash", "-c", "rm -rf ."))
    with pytest.raises(UnsupportedCommandError):
        runner.classify(("python", "-c", "print('unsafe')"))


def test_read_only_command_gets_read_only_workspace(tmp_path: Path) -> None:
    backend = RecordingSandbox()
    runner = GuardedCommandRunner(root=tmp_path, branch="feature/test", backend=backend)

    result = runner.run(("git", "status", "--short"))

    assert result.executed is True
    assert backend.calls == [
        (("git", "status", "--short"), tmp_path.resolve(), 120.0, False)
    ]


def test_validation_command_gets_writable_workspace(tmp_path: Path) -> None:
    backend = RecordingSandbox()
    runner = GuardedCommandRunner(
        root=tmp_path,
        branch="feature/test",
        backend=backend,
        timeout_seconds=42.0,
    )

    result = runner.run(("pytest", "-q"))

    assert result.executed is True
    assert result.value.returncode == 0
    assert result.value.stdout == "passed"
    assert backend.calls == [(("pytest", "-q"), tmp_path.resolve(), 42.0, True)]
