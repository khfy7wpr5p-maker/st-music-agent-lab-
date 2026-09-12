from __future__ import annotations

import json

import pytest

from st_music_agent.deterministic_executor import (
    DeterministicExecutor,
    PlanValidationError,
    SmallModelPlanner,
    parse_execution_plan,
)
from st_music_agent.policy import AutonomyDecision
from st_music_agent.tools import ActionResult

REPO = "owner/repo"
BASE = "a" * 40
BRANCH = "fix/deterministic"
OLD_BLOB = "b" * 40
NEW_BLOB = "c" * 40
NEW_HEAD = "d" * 40


def _plan(**overrides):
    value = {
        "repository": REPO,
        "base_sha": BASE,
        "feature_branch": BRANCH,
        "changes": [
            {
                "path": "src/a.py",
                "operation": "update",
                "expected_blob_sha": OLD_BLOB,
                "content": "print('new')\n",
                "commit_message": "Update a deterministically",
            }
        ],
        "validation_targets": ["python -m pytest -q tests/test_a.py"],
        "summary": "Update a.py",
    }
    value.update(overrides)
    return value


def _parse(value=None, **kwargs):
    return parse_execution_plan(
        json.dumps(value or _plan()),
        expected_repository=REPO,
        expected_base_sha=BASE,
        expected_feature_branch=BRANCH,
        allowed_update_paths=frozenset({"src/a.py"}),
        existing_paths=frozenset({"src/a.py"}),
        **kwargs,
    )


def test_plan_rejects_unknown_fields() -> None:
    value = _plan(extra=True)
    with pytest.raises(PlanValidationError, match="fields are invalid"):
        _parse(value)


def test_plan_rejects_protected_bound_branch() -> None:
    value = _plan(feature_branch="main")
    with pytest.raises(PlanValidationError, match="protected branch"):
        parse_execution_plan(
            json.dumps(value),
            expected_repository=REPO,
            expected_base_sha=BASE,
            expected_feature_branch="main",
            allowed_update_paths=frozenset({"src/a.py"}),
            existing_paths=frozenset({"src/a.py"}),
        )


def test_plan_rejects_path_traversal_and_sensitive_control_path() -> None:
    for path in ("../x.py", ".github/workflows/ci.yml", ".env"):
        value = _plan()
        value["changes"][0]["path"] = path
        with pytest.raises(PlanValidationError):
            _parse(value)


def test_plan_rejects_update_without_full_read_evidence() -> None:
    with pytest.raises(PlanValidationError, match="not supplied as full read evidence"):
        parse_execution_plan(
            json.dumps(_plan()),
            expected_repository=REPO,
            expected_base_sha=BASE,
            expected_feature_branch=BRANCH,
            allowed_update_paths=frozenset(),
            existing_paths=frozenset({"src/a.py"}),
        )


def test_plan_rejects_too_many_changes() -> None:
    value = _plan()
    value["changes"] = value["changes"] * 4
    for index, change in enumerate(value["changes"]):
        change["path"] = f"src/a{index}.py"
    with pytest.raises(PlanValidationError, match="maximum changed-file count"):
        parse_execution_plan(
            json.dumps(value),
            expected_repository=REPO,
            expected_base_sha=BASE,
            expected_feature_branch=BRANCH,
            allowed_update_paths=frozenset(change["path"] for change in value["changes"]),
            existing_paths=frozenset(change["path"] for change in value["changes"]),
        )


class FakeRead:
    def __init__(self) -> None:
        self.head = BASE
        self.files = {"src/a.py": {"sha": OLD_BLOB, "content": "print('old')\n"}}

    def repository_metadata(self):
        return {"full_name": REPO}

    def repository_tree(self, ref="main"):
        return {
            "ref": ref,
            "commit_sha": self.head,
            "files": [
                {"path": path, "sha": value["sha"], "size": len(value["content"])}
                for path, value in sorted(self.files.items())
            ],
        }

    def read_file(self, path, ref=None):
        value = self.files[path]
        return {
            "path": path,
            "ref": ref,
            "content": value["content"],
            "truncated": False,
            "sha": value["sha"],
        }

    def branch_info(self, branch):
        return {"name": branch, "protected": False, "commit_sha": self.head}

    def workflow_runs(self, head_sha=None):
        return {"workflow_runs": []}


class FakeMutation:
    def __init__(self, read: FakeRead) -> None:
        self.read = read
        self.write_calls = []

    def create_branch(self, branch, base_sha, approval=None):
        raise AssertionError("not used")

    def write_file(self, *, path, content, commit_message, branch, sha=None, approval=None):
        self.write_calls.append(
            {
                "path": path,
                "content": content,
                "commit_message": commit_message,
                "branch": branch,
                "sha": sha,
            }
        )
        self.read.files[path] = {"sha": NEW_BLOB, "content": content}
        self.read.head = NEW_HEAD
        return ActionResult(
            decision=AutonomyDecision.AUTO_EXECUTE,
            executed=True,
            value={
                "path": path,
                "branch": branch,
                "commit_sha": NEW_HEAD,
                "content_sha": NEW_BLOB,
            },
        )

    def open_pull_request(self, **kwargs):
        raise AssertionError("not used")


def test_executor_applies_exact_update_and_verifies_read_back() -> None:
    read = FakeRead()
    mutation = FakeMutation(read)
    result = DeterministicExecutor(read, mutation).execute(_parse())
    assert result.applied is True
    assert result.head_sha == NEW_HEAD
    assert result.changed_files == ("src/a.py",)
    assert result.failure_reason is None
    assert result.checkpoints[0]["status"] == "APPLIED_VERIFIED"
    assert mutation.write_calls[0]["sha"] == OLD_BLOB
    assert mutation.write_calls[0]["branch"] == BRANCH


def test_executor_fails_closed_on_stale_blob_without_write() -> None:
    read = FakeRead()
    read.files["src/a.py"]["sha"] = "e" * 40
    mutation = FakeMutation(read)
    result = DeterministicExecutor(read, mutation).execute(_parse())
    assert result.applied is False
    assert "stale blob mismatch" in (result.failure_reason or "")
    assert mutation.write_calls == []
    assert result.head_sha == BASE


def test_executor_rejects_branch_that_moved_before_execution() -> None:
    read = FakeRead()
    read.head = "e" * 40
    mutation = FakeMutation(read)
    result = DeterministicExecutor(read, mutation).execute(_parse())
    assert result.applied is False
    assert "exact plan base SHA" in (result.failure_reason or "")
    assert mutation.write_calls == []


class ScriptedProvider:
    def __init__(self, messages):
        self.messages = list(messages)
        self.calls = []

    def complete_with_tools(self, messages, tools):
        self.calls.append((messages, tools))
        return self.messages.pop(0)


def test_small_model_planner_uses_two_tool_free_bounded_calls() -> None:
    read = FakeRead()
    provider = ScriptedProvider(
        [
            {"role": "assistant", "content": json.dumps({"read_paths": ["src/a.py"]})},
            {"role": "assistant", "content": json.dumps(_plan())},
        ]
    )
    result = SmallModelPlanner(provider).build_plan(
        repository=REPO,
        base_sha=BASE,
        feature_branch=BRANCH,
        instruction="Update src/a.py safely",
        read_client=read,
    )
    assert result.model_calls == 2
    assert result.selected_paths == ("src/a.py",)
    assert result.plan.changes[0].expected_blob_sha == OLD_BLOB
    assert all(tools == [] for _, tools in provider.calls)


def test_small_model_planner_rejects_tool_requests() -> None:
    read = FakeRead()
    provider = ScriptedProvider(
        [
            {
                "role": "assistant",
                "content": "{}",
                "tool_calls": [{"id": "x", "type": "function", "function": {"name": "write"}}],
            }
        ]
    )
    with pytest.raises(PlanValidationError, match="must not request tools"):
        SmallModelPlanner(provider).build_plan(
            repository=REPO,
            base_sha=BASE,
            feature_branch=BRANCH,
            instruction="do work",
            read_client=read,
        )
