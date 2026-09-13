from __future__ import annotations

import pytest

from st_music_agent.deterministic_task_execution import DeterministicApp3TaskService
from st_music_agent.policy import AutonomyDecision
from st_music_agent.task_execution import TaskExecutionConfig, TaskExecutionError
from st_music_agent.tools import ActionResult

REPOSITORY = "khfy7wpr5p-maker/st-score-restore-engine"
BASE = "a" * 40


class TimeoutRead:
    def __init__(self) -> None:
        self.branch = None

    def repository_metadata(self):
        return {"full_name": REPOSITORY, "default_branch": "main"}

    def branch_info(self, branch):
        if branch == "main":
            return {"name": branch, "protected": True, "commit_sha": BASE}
        if branch == self.branch:
            return {"name": branch, "protected": False, "commit_sha": BASE}
        raise RuntimeError("branch not found")

    def repository_tree(self, ref="main"):
        return {
            "ref": ref,
            "commit_sha": BASE,
            "files": [{"path": "README.md", "sha": "b" * 40, "size": 10}],
        }

    def read_file(self, path, ref=None):
        return {
            "path": path,
            "ref": ref,
            "content": "before\n",
            "truncated": False,
            "sha": "b" * 40,
        }

    def workflow_runs(self, head_sha=None):
        return {"workflow_runs": []}

    def compare_commits(self, base_sha, head_sha):
        raise AssertionError("timeout must occur before compare")


class TimeoutMutation:
    def __init__(self, read: TimeoutRead) -> None:
        self.read = read

    def create_branch(self, branch, base_sha, approval=None):
        assert approval is None
        assert base_sha == BASE
        self.read.branch = branch
        return ActionResult(
            decision=AutonomyDecision.AUTO_EXECUTE,
            executed=True,
            value={"ref": f"refs/heads/{branch}", "sha": base_sha},
        )

    def write_file(self, **kwargs):
        raise AssertionError("provider timeout must not reach mutation")

    def open_pull_request(self, **kwargs):
        raise AssertionError("provider timeout must not reach PR")


class TimeoutProvider:
    profile_name = "Local-Qwen3-Test"

    def complete_with_tools(self, messages, tools):
        raise TimeoutError("local provider timed out")


def test_provider_timeout_persists_failed_task_instead_of_leaving_agent_running(tmp_path) -> None:
    read = TimeoutRead()
    mutation = TimeoutMutation(read)
    config = TaskExecutionConfig(
        enabled=True,
        profile_name="Local-Qwen3-Test",
        provider_base_url="http://127.0.0.1:11434/v1",
        provider_model="qwen3:1.7b",
        provider_api_key_env="OLLAMA_API_KEY",
    )
    service = DeterministicApp3TaskService(
        config,
        state_path=tmp_path / "task-events.jsonl",
        read_factory=lambda repository: read,
        mutation_factory=lambda repository: mutation,
        provider_client=TimeoutProvider(),
    )
    preview = service.preview("score_restore", "Create one safe documentation file")

    with pytest.raises(TaskExecutionError, match="deterministic planner failed"):
        service.run(preview.task_id)

    status = service.status(preview.task_id)
    events = service.store.task_events(preview.task_id)

    assert status["stage"] == "FAILED"
    assert status["outcome"] == "FAILED"
    assert any(item["event"] == "PLANNER_FAILURE" for item in events)
    assert any(item["event"] == "FAILED" for item in events)
    assert not any(item["event"] == "PLAN_VALIDATED" for item in events)
