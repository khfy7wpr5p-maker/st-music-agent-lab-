from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from .contracts import ActionRequest, RiskLevel
from .tools import ActionApproval, ActionResult, GuardedActionExecutor


class WorkspacePathError(ValueError):
    pass


@dataclass(slots=True)
class GuardedWorkspace:
    root: Path
    branch: str
    executor: GuardedActionExecutor = field(default_factory=GuardedActionExecutor)

    def __post_init__(self) -> None:
        self.root = self.root.resolve()
        if not self.root.is_dir():
            raise WorkspacePathError(f"workspace root is not a directory: {self.root}")
        if not self.branch.strip():
            raise ValueError("branch must not be empty")

    def resolve(self, relative_path: str) -> Path:
        path = Path(relative_path)
        if path.is_absolute():
            raise WorkspacePathError("absolute workspace paths are not allowed")

        target = (self.root / path).resolve(strict=False)
        try:
            target.relative_to(self.root)
        except ValueError as exc:
            raise WorkspacePathError("path escapes the workspace root") from exc
        return target

    def read_text(self, relative_path: str, encoding: str = "utf-8") -> ActionResult:
        target = self.resolve(relative_path)
        action = ActionRequest(
            name="workspace.read_text",
            target=relative_path,
            risk=RiskLevel.READ_ONLY,
            metadata={"branch": self.branch},
        )
        return self.executor.execute(action, lambda: target.read_text(encoding=encoding))

    def write_text(
        self,
        relative_path: str,
        content: str,
        approval: ActionApproval | None = None,
        encoding: str = "utf-8",
    ) -> ActionResult:
        target = self.resolve(relative_path)
        action = ActionRequest(
            name="workspace.write_text",
            target=relative_path,
            risk=RiskLevel.REVERSIBLE_WRITE,
            metadata={"branch": self.branch},
        )

        def operation() -> int:
            target.parent.mkdir(parents=True, exist_ok=True)
            return target.write_text(content, encoding=encoding)

        return self.executor.execute(action, operation, approval)

    def delete_file(
        self,
        relative_path: str,
        approval: ActionApproval | None = None,
    ) -> ActionResult:
        target = self.resolve(relative_path)
        action = ActionRequest(
            name="workspace.delete_file",
            target=relative_path,
            risk=RiskLevel.DESTRUCTIVE,
            metadata={"branch": self.branch},
        )

        def operation() -> None:
            target.unlink()

        return self.executor.execute(action, operation, approval)
