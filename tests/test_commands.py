import subprocess
from pathlib import Path

import pytest

from st_music_agent.commands import (
    GuardedCommandRunner,
    ProcessExecutionDisabledError,
    UnsupportedCommandError,
)
from st_music_agent.contracts import RiskLevel


def test_process_execution_is_disabled_by_default(tmp_path: Path) -> None:
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


def test_enabled_isolated_runner_executes_without_shell(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[tuple[str, ...]] = []

    def fake_run(args: tuple[str, ...], **kwargs: object) -> subprocess.CompletedProcess[str]:
        calls.append(args)
        assert kwargs["cwd"] == tmp_path.resolve()
        assert kwargs["capture_output"] is True
        assert kwargs["check"] is False
        assert kwargs["text"] is True
        return subprocess.CompletedProcess(args, 0, stdout="passed", stderr="")

    monkeypatch.setattr("st_music_agent.commands.subprocess.run", fake_run)
    runner = GuardedCommandRunner(
        root=tmp_path,
        branch="feature/test",
        process_execution_enabled=True,
    )

    result = runner.run(("pytest", "-q"))

    assert result.executed is True
    assert result.value.returncode == 0
    assert result.value.stdout == "passed"
    assert calls == [("pytest", "-q")]
