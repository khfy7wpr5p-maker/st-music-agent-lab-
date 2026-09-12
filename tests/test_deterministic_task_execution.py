from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any

import pytest

from st_music_agent.deterministic_task_execution import DeterministicApp3TaskService
from st_music_agent.policy import AutonomyDecision
from st_music_agent.task_execution import TaskExecutionConfig, TaskExecutionError
from st_music_agent.tools import ActionApproval, ActionResult


@dataclass
class RepoState:
    base_sha: str = "a" * 40
    head_sha: str = "a" * 40
    branch: str | None = None
    blob_sha: str = "c" * 40
    content: str = "before\n"
    writes: list[dict[str, Any]] = field(default_factory=list)


class FakeReadClient:
    def __init__(self, state: RepoState) -> None:
        self.state = state

    def repository_metadata(self):
        return {"full_name": "owner/repo", "default_branch": "main"}

    def repository_tree(self, ref="main"):
        head = self.state.head_sha if ref == self.state.branch else self.state.base_sha
        return {
            "ref": ref,
            "commit_sha": head,
            "files": [
                {
                    "path": "README.md",
                    "sha": self.state.blob_sha,
                    "size": len(self.state.content),
                }
            ],
        }

    def read_file(self, path, ref=None):
        assert path == "README.md"
        return {
            "path": path,
            "ref": ref,
            "content": self.state.content,
            "truncated": False,
            "sha": self.state.blob_sha,
        }

    def branch_info(self, branch):
        if branch == "main":
            return {"name": branch, "protected": True, "commit_sha": self.state.base_sha}
        if branch == self.state.branch:
            return {"name": branch, "protected": False, "commit_sha": self.state.head_sha}
        raise RuntimeError("branch not found")

    def workflow_runs(self, head_sha=None):
        return {"workflow_runs": []}

    def compare_commits(self, base_sha, head_sha):
        return {
            "base_sha": base_sha,
            "head_sha": head_sha,
            "status": "ahead",
            "ahead_by": 1,
            "behind_by": 0,
            "total_commits": 1,
            "files": [
                {
                    "path": "README.md",
                    "status": "modified",
                    "additions": 1,
                    "deletions": 1,
                    "changes": 2,
                }
            ],
        }


class FakeMutationClient:
    def __init__(self, state: RepoState) -> None:
        self.state = state

    def create_branch(self, branch, base_sha, approval=None):
        assert approval is None
        assert base_sha == self.state.base_sha
        self.state.branch = branch
        self.state.head_sha = base_sha
        return ActionResult(
            decision=AutonomyDecision.AUTO_EXECUTE,
            executed=True,
            value={"ref": f"refs/heads/{branch}", "sha": base_sha},
        )

    def write_file(
        self,
        *,
        path,
        content,
        commit_message,
        branch,
        sha=None,
        approval: ActionApproval | None = None,
    ):
        assert approval is None
        assert branch == self.state.branch
        self.state.writes.append(
            {
                "path": path,
                "content": content,
                "commit_message": commit_message,
                "branch": branch,
                "sha": sha,
            }
        )
        self.state.content = content
        self.state.blob_sha = "d" * 40
        self.state.head_sha = "b" * 40
        return ActionResult(
            decision=AutonomyDecision.AUTO_EXECUTE,
            executed=True,
            value={
                "path": path,
                "branch": branch,
                "commit_sha": self.state.head_sha,
                "content_sha": self.state.blob_sha,
            },
        )

    def open_pull_request(self, **kwargs):
        raise AssertionError("PR is not part of deterministic run")


class ScriptedProvider:
    profile_name = "GLM-5.1"
    feature_branch = ""

    def __init__(self, second_message=None) -> None:
        self.calls = []
        self.second_message = second_message

    def complete_with_tools(self, messages, tools):
        self.calls.append((messages, tools))
        if len(self.calls) == 1:
            return {
                "role": "assistant",
                "content": json.dumps({"read_paths": ["README.md"]}),
            }
        if self.second_message is not None:
            return self.second_message
        return {
            "role": "assistant",
            "content": json.dumps(
                {
                    "repository": "owner/repo",
                    "base_sha": "a" * 40,
                    "feature_branch": self.feature_branch,
                    "changes": [
                        {
                            "path": "README.md",
                            "operation": "update",
                            "expected_blob_sha": "c" * 40,
                            "content": "after\n",
                            "commit_message": "Update README deterministically",
                        }
                    ],
                    "validation_targets": [
                        "python -m pytest -q tests/test_deterministic_task_execution.py"
                    ],
                    "summary": "Update README with host-side deterministic execution",
                }
            ),
        }


def _service(tmp_path, state, provider):
    read = FakeReadClient(state)
    mutation = FakeMutationClient(state)
    config = TaskExecutionConfig(
        enabled=True,
        provider_base_url="https://provider.invalid/v1",
        provider_model="test-model",
        provider_api_key_env="TEST_PROVIDER_KEY",
    )
    return DeterministicApp3TaskService(
        config,
        state_path=tmp_path / "task-events.jsonl",
        read_factory=lambda repository: read,
        mutation_factory=lambda repository: mutation,
        provider_client=provider,
    )


def test_deterministic_app3_uses_planner_without_write_tools(tmp_path) -> None:
    state = RepoState()
    provider = ScriptedProvider()
    service = _service(tmp_path, state, provider)
    preview = service.preview("score_restore", "Update README wording")
    provider.feature_branch = preview.feature_branch

    record = service.run(preview.task_id)
    status = service.status(preview.task_id)

    assert record.head_sha == "b" * 40
    assert record.turns == 2
    assert record.tool_calls == 0
    assert status["stage"] == "CI_PENDING"
    assert status["commit"]["execution_mode"] == "MODEL_PLANS_HOST_EXECUTES"
    assert state.writes == [
        {
            "path": "README.md",
            "content": "after\n",
            "commit_message": "Update README deterministically",
            "branch": preview.feature_branch,
            "sha": "c" * 40,
        }
    ]
    assert len(provider.calls) == 2
    assert all(tools == [] for _, tools in provider.calls)
    events = service.store.task_events(preview.task_id)
    assert any(item["event"] == "PLAN_VALIDATED" for item in events)
    assert any(item["event"] == "EXECUTOR_CHECKPOINT" for item in events)


def test_invalid_planner_json_fails_closed_without_write(tmp_path) -> None:
    state = RepoState()
    provider = ScriptedProvider({"role": "assistant", "content": "not-json"})
    service = _service(tmp_path, state, provider)
    preview = service.preview("score_editor", "Update README wording")
    provider.feature_branch = preview.feature_branch

    with pytest.raises(TaskExecutionError, match="deterministic planner failed"):
        service.run(preview.task_id)

    status = service.status(preview.task_id)
    assert status["stage"] == "FAILED"
    assert status["outcome"] == "FAILED"
    assert state.writes == []


def test_stale_planner_blob_fails_closed_before_mutation(tmp_path) -> None:
    state = RepoState()
    provider = ScriptedProvider()
    service = _service(tmp_path, state, provider)
    preview = service.preview("score_restore", "Update README wording")
    provider.feature_branch = preview.feature_branch

    original_complete = provider.complete_with_tools

    def stale_complete(messages, tools):
        result = original_complete(messages, tools)
        if len(provider.calls) == 2:
            payload = json.loads(result["content"])
            payload["changes"][0]["expected_blob_sha"] = "e" * 40
            return {"role": "assistant", "content": json.dumps(payload)}
        return result

    provider.complete_with_tools = stale_complete

    with pytest.raises(TaskExecutionError, match="stale blob mismatch"):
        service.run(preview.task_id)

    assert state.writes == []
    status = service.status(preview.task_id)
    assert status["stage"] == "FAILED"


def test_empty_plan_is_bounded_failure_without_retry_or_write(tmp_path) -> None:
    state = RepoState()
    provider = ScriptedProvider()
    service = _service(tmp_path, state, provider)
    preview = service.preview("score_restore", "Inspect only")
    provider.feature_branch = preview.feature_branch

    original_complete = provider.complete_with_tools

    def empty_complete(messages, tools):
        result = original_complete(messages, tools)
        if len(provider.calls) == 2:
            payload = json.loads(result["content"])
            payload["changes"] = []
            payload["summary"] = "No safe change proposed"
            return {"role": "assistant", "content": json.dumps(payload)}
        return result

    provider.complete_with_tools = empty_complete

    with pytest.raises(TaskExecutionError, match="plan contains no file changes"):
        service.run(preview.task_id)

    assert len(provider.calls) == 2
    assert state.writes == []
    with pytest.raises(TaskExecutionError, match="failed task attempt cannot be rewritten"):
        service.run(preview.task_id)
