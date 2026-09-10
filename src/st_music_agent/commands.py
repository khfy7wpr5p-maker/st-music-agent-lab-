from __future__ import annotations

import subprocess
from collections.abc import Sequence
from dataclasses import dataclass, field
from pathlib import Path

from .contracts import ActionRequest, RiskLevel
from .tools import ActionApproval, ActionResult, GuardedActionExecutor


class UnsupportedCommandError(ValueError):
    pass


class ProcessExecutionDisabledError(RuntimeError):
    pass


@dataclass(frozen=True, slots=True)
class CommandResult:
    returncode: int
    stdout: str
    stderr: str


@dataclass(slots=True)
class GuardedCommandRunner:
    root: Path
    branch: str
    executor: GuardedActionExecutor = field(default_factory=GuardedActionExecutor)
    timeout_seconds: float = 120.0
    process_execution_enabled: bool = False

    _READ_ONLY_GIT = frozenset({"diff", "log", "rev-parse", "show", "status"})
    _FORBIDDEN_GIT_FLAGS = ("--ext-diff", "--no-index", "--output", "--textconv")

    def __post_init__(self) -> None:
        self.root = self.root.resolve()
        if not self.root.is_dir():
            raise ValueError(f"command root is not a directory: {self.root}")
        if not self.branch.strip():
            raise ValueError("branch must not be empty")

    def classify(self, argv: Sequence[str]) -> RiskLevel:
        args = tuple(argv)
        if len(args) >= 2 and args[0] == "git" and args[1] in self._READ_ONLY_GIT:
            if any(
                arg == forbidden or arg.startswith(f"{forbidden}=")
                for arg in args[2:]
                for forbidden in self._FORBIDDEN_GIT_FLAGS
            ):
                raise UnsupportedCommandError("git command contains a workspace-escape or side-effect flag")
            return RiskLevel.READ_ONLY
        if args and args[0] == "pytest":
            return RiskLevel.REVERSIBLE_WRITE
        if len(args) >= 2 and args[0] == "ruff" and args[1] == "check":
            return RiskLevel.REVERSIBLE_WRITE
        if len(args) >= 3 and args[:3] == ("python", "-m", "pytest"):
            return RiskLevel.REVERSIBLE_WRITE
        raise UnsupportedCommandError("command is outside the allowlisted validation/read-only set")

    def run(
        self,
        argv: Sequence[str],
        approval: ActionApproval | None = None,
    ) -> ActionResult:
        args = tuple(argv)
        if not args:
            raise UnsupportedCommandError("command must not be empty")
        if not self.process_execution_enabled:
            raise ProcessExecutionDisabledError(
                "process execution requires an externally isolated workspace"
            )

        risk = self.classify(args)
        action = ActionRequest(
            name="workspace.run_command",
            target=" ".join(args),
            risk=risk,
            metadata={"branch": self.branch},
        )

        def operation() -> CommandResult:
            completed = subprocess.run(
                args,
                cwd=self.root,
                capture_output=True,
                check=False,
                text=True,
                timeout=self.timeout_seconds,
            )
            return CommandResult(
                returncode=completed.returncode,
                stdout=completed.stdout,
                stderr=completed.stderr,
            )

        return self.executor.execute(action, operation, approval)
