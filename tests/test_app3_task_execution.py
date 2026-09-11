from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any

import pytest

from st_music_agent.app3_task_execution import App3TaskService
from st_music_agent.policy import AutonomyDecision
from st_music_agent.task_execution import TaskExecutionConfig, TaskExecutionError
from st_music_agent.task_state import ProjectExecutionProfile
from st_music_agent.tools import ActionApproval, ActionResult


@dataclass
class RepoState:
    base_sha: str = "a" * 40
    head_sha: str = "a" * 40
    branch: str | None = None
    workflow_head: str | None = None
    workflow_status: str = "completed"
    workflow_conclusion: str | None = "success"
    writes: list[dict[str, Any]] = field(default_factory=list)
    prs: list[dict[str, Any]] = field(default_factory=list)


class FakeReadClient:
    def __init__(self, state: RepoState) -> None:
        self.state = state

    def repository_metadata(self) -> dict[str, Any]:
        return {"full_name": "owner/repo", "default_branch": "main"}

    def repository_tree(self, ref: str = "main") -> dict[str, Any]:
        sha = self.state.head_sha if ref == self.state.branch else self.state.base_sha
        return {
            "ref": ref,
            "commit_sha": sha,
            "files": [{"path": "README.md", "sha": "c" * 40, "size": 20}],
        }

    def read_file(self, path: str, ref: str | None = None) -> dict[str, Any]:
        return {
            "path": path,
            "ref": ref,
            "content": "before\n",
            "truncated": False,
            "sha": "c" * 40,
        }

    def branch_info(self, branch: str) -> dict[str, Any]:
        if branch == "main":
            return {"name": "main", "protected": True, "commit_sha": self.state.base_sha}
        if branch == self.state.branch:
            return {"name": branch, "protected": False, "commit_sha": self.state.head_sha}
        raise RuntimeError("branch not found")

    def workflow_runs(self, head_sha: str | None = None) -> dict[str, Any]:
        workflow_head = self.state.workflow_head or head_sha
        return {
            "workflow_runs": [
                {
                    "id": 91,
                    "name": "core-ci",
                    "event": "push",
                    "status": self.state.workflow_status,
                    "conclusion": self.state.workflow_conclusion,
                    "head_sha": workflow_head,
                    "html_url": "https://example.invalid/run/91",
                }
            ]
        }

    def compare_commits(self, base_sha: str, head_sha: str) -> dict[str, Any]:
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

    def pull_request(self, number: int) -> dict[str, Any]:
        return {
            "number": number,
            "state": "open",
            "draft": False,
            "mergeable": True,
            "head_ref": self.state.branch,
            "head_sha": self.state.head_sha,
            "base_ref": "main",
            "base_sha": self.state.base_sha,
        }


class FakeMutationClient:
    def __init__(self, state: RepoState) -> None:
        self.state = state

    def create_branch(
        self,
        branch: str,
        base_sha: str,
        approval: ActionApproval | None = None,
    ) -> ActionResult:
        assert approval is None
        assert base_sha == self.state.base_sha
        self.state.branch = branch
        return ActionResult(
            decision=AutonomyDecision.AUTO_EXECUTE,
            executed=True,
            value={"ref": f"refs/heads/{branch}", "sha": base_sha},
        )

    def write_file(
        self,
        *,
        path: str,
        content: str,
        commit_message: str,
        branch: str,
        sha: str | None = None,
        approval: ActionApproval | None = None,
    ) -> ActionResult:
        assert approval is None
        assert branch == self.state.branch
        self.state.writes.append(
            {"path": path, "content": content, "commit_message": commit_message, "sha": sha}
        )
        self.state.head_sha = "b" * 40
        return ActionResult(
            decision=AutonomyDecision.AUTO_EXECUTE,
            executed=True,
            value={"path": path, "branch": branch, "commit_sha": self.state.head_sha},
        )

    def open_pull_request(
        self,
        *,
        title: str,
        head: str,
        base: str,
        body: str = "",
        approval: ActionApproval | None = None,
    ) -> ActionResult:
        target = f"{head}->{base}"
        assert approval == ActionApproval("github.open_pull_request", target)
        self.state.prs.append({"title": title, "head": head, "base": base, "body": body})
        return ActionResult(
            decision=AutonomyDecision.REQUIRE_HUMAN,
            executed=True,
            value={
                "number": 31,
                "state": "open",
                "html_url": "https://example.invalid/pr/31",
            },
        )


class ScriptedProvider:
    profile_name = "GLM-5.1"

    def __init__(self) -> None:
        self.turn = 0

    def complete_with_tools(self, messages, tools):
        self.turn += 1
        if self.turn == 1:
            return {
                "role": "assistant",
                "content": None,
                "tool_calls": [
                    {
                        "id": "tree",
                        "type": "function",
                        "function": {
                            "name": "github.tree",
                            "arguments": json.dumps({"ref": "main"}),
                        },
                    }
                ],
            }
        if self.turn == 2:
            return {
                "role": "assistant",
                "content": None,
                "tool_calls": [
                    {
                        "id": "write",
                        "type": "function",
                        "function": {
                            "name": "task.write_file",
                            "arguments": json.dumps(
                                {
                                    "path": "README.md",
                                    "content": "after\n",
                                    "commit_message": "Update README wording safely",
                                    "sha": "c" * 40,
                                }
                            ),
                        },
                    }
                ],
            }
        return {"role": "assistant", "content": "Updated one bounded file."}


def _service(tmp_path, state: RepoState, *, profiles=None) -> App3TaskService:
    read = FakeReadClient(state)
    mutation = FakeMutationClient(state)
    config = TaskExecutionConfig(
        enabled=True,
        provider_base_url="https://provider.invalid/v1",
        provider_model="test-model",
        provider_api_key_env="TEST_PROVIDER_KEY",
    )
    return App3TaskService(
        config,
        state_path=tmp_path / "task-events.jsonl",
        read_factory=lambda repository: read,
        mutation_factory=lambda repository: mutation,
        provider_client=ScriptedProvider(),
        profiles=profiles,
    )


def test_app3_requires_exact_ci_and_validators_before_pr(tmp_path) -> None:
    state = RepoState()
    service = _service(tmp_path, state)
    preview = service.preview("score_restore", "Update README wording")

    record = service.run(preview.task_id)
    pending = service.status(preview.task_id)

    assert record.head_sha == "b" * 40
    assert pending["stage"] == "CI_PENDING"
    assert pending["outcome"] == "WORKING"
    assert pending["commit"]["changed_files"][0]["path"] == "README.md"
    with pytest.raises(TaskExecutionError, match="VERIFIED_SUCCESS"):
        service.open_pull_request(preview.task_id)

    verified = service.refresh_evidence(preview.task_id)

    assert verified["stage"] == "VERIFIED_SUCCESS"
    assert verified["outcome"] == "VERIFIED_SUCCESS"
    assert verified["ci"]["state"] == "success"
    assert {item["status"] for item in verified["validators"]} == {"PASS"}

    pr = service.open_pull_request(preview.task_id)
    final = service.status(preview.task_id)

    assert pr["number"] == 31
    assert pr["head_sha"] == "b" * 40
    assert pr["base_sha"] == "a" * 40
    assert final["stage"] == "PR_OPENED"
    assert final["merge_authorized"] is False


def test_ci_for_different_sha_cannot_verify_task(tmp_path) -> None:
    state = RepoState(workflow_head="d" * 40)
    service = _service(tmp_path, state)
    preview = service.preview("score_editor", "Update README wording")
    service.run(preview.task_id)

    status = service.refresh_evidence(preview.task_id)

    assert status["stage"] == "CI_PENDING"
    assert status["outcome"] == "WORKING"
    assert status["ci"]["state"] == "pending"
    assert status["ci"]["runs"] == []


def test_unavailable_configured_validator_never_becomes_pass(tmp_path) -> None:
    state = RepoState()
    profiles = {
        "score_restore": ProjectExecutionProfile(
            project="score_restore",
            validator_names=("exact_commit_binding", "domain_music_validator"),
        )
    }
    service = _service(tmp_path, state, profiles=profiles)
    preview = service.preview("score_restore", "Update README wording")
    service.run(preview.task_id)

    status = service.refresh_evidence(preview.task_id)

    assert status["stage"] == "VALIDATORS_REVIEWED"
    assert status["outcome"] == "REVIEW_REQUIRED"
    assert any(item["status"] == "UNAVAILABLE" for item in status["validators"])
    with pytest.raises(TaskExecutionError, match="VERIFIED_SUCCESS"):
        service.open_pull_request(preview.task_id)


def test_status_survives_service_restart(tmp_path) -> None:
    state = RepoState()
    service = _service(tmp_path, state)
    preview = service.preview("real_time_score_following", "Update README wording")
    service.run(preview.task_id)

    restarted = _service(tmp_path, state)
    status = restarted.status(preview.task_id)

    assert status["stage"] == "CI_PENDING"
    assert status["preview"]["instruction"] is None
    assert status["preview"]["resumed_from_persistent_state"] is True
    assert status["commit"]["head_sha"] == "b" * 40
