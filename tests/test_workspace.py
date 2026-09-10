from pathlib import Path

import pytest

from st_music_agent.tools import ActionApproval
from st_music_agent.workspace import GuardedWorkspace, WorkspacePathError


def test_feature_branch_read_and_write_stay_inside_workspace(tmp_path: Path) -> None:
    root = tmp_path / "repo"
    root.mkdir()
    (root / "input.txt").write_text("hello", encoding="utf-8")
    workspace = GuardedWorkspace(root=root, branch="feature/test")

    read = workspace.read_text("input.txt")
    write = workspace.write_text("nested/output.txt", "world")

    assert read.executed is True
    assert read.value == "hello"
    assert write.executed is True
    assert (root / "nested/output.txt").read_text(encoding="utf-8") == "world"


def test_main_write_requires_exact_approval(tmp_path: Path) -> None:
    root = tmp_path / "repo"
    root.mkdir()
    workspace = GuardedWorkspace(root=root, branch="main")

    blocked = workspace.write_text("output.txt", "blocked")
    approved = workspace.write_text(
        "output.txt",
        "allowed",
        approval=ActionApproval("workspace.write_text", "output.txt"),
    )

    assert blocked.executed is False
    assert approved.executed is True
    assert (root / "output.txt").read_text(encoding="utf-8") == "allowed"


def test_delete_requires_approval_even_on_feature_branch(tmp_path: Path) -> None:
    root = tmp_path / "repo"
    root.mkdir()
    target = root / "remove.txt"
    target.write_text("data", encoding="utf-8")
    workspace = GuardedWorkspace(root=root, branch="feature/test")

    blocked = workspace.delete_file("remove.txt")
    approved = workspace.delete_file(
        "remove.txt",
        approval=ActionApproval("workspace.delete_file", "remove.txt"),
    )

    assert blocked.executed is False
    assert target.exists() is False
    assert approved.executed is True


def test_parent_traversal_and_absolute_paths_are_rejected(tmp_path: Path) -> None:
    root = tmp_path / "repo"
    root.mkdir()
    workspace = GuardedWorkspace(root=root, branch="feature/test")

    with pytest.raises(WorkspacePathError):
        workspace.resolve("../outside.txt")
    with pytest.raises(WorkspacePathError):
        workspace.resolve(str((tmp_path / "outside.txt").resolve()))


def test_symlink_escape_is_rejected(tmp_path: Path) -> None:
    root = tmp_path / "repo"
    outside = tmp_path / "outside"
    root.mkdir()
    outside.mkdir()
    (root / "link").symlink_to(outside, target_is_directory=True)
    workspace = GuardedWorkspace(root=root, branch="feature/test")

    with pytest.raises(WorkspacePathError):
        workspace.resolve("link/escape.txt")
