from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any

import pytest

from st_music_agent.deterministic_task_execution import DeterministicApp3TaskService
from st_music_agent.policy import AutonomyDecision
from st_music_agent.task_execution import TaskExecutionConfig, TaskExecutionError
from st_music_agent.task_state import ProjectExecutionProfile
from st_music_agent.tools import ActionApproval, ActionResult


@dataclass
class RepoState:
    base_sha: str = "a" * 40
    head_sha: str = "a" * 40
    branch: str | None = None
    blob_sha: str = "c" * 40
    content: str = "before\n"
    workflow_runs: list[dict[str, Any]] = field(default_factory=list)
    prs: list[dict[str, Any]] = field(default_factory=list)


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
        return {"workflow_runs": list(self.state.workflow_runs)}

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

    def pull_request(self, number):
        return {
            "number": number,
            "state": "open",
            "draft": False,
            "mergeable": None,
            "head_ref": self.state.branch,
            "head_sha": self.state.head_sha,
            "base_ref": "main",
            "base_sha": self.state.base_sha,
        }


class FakeMutationClient:
    def __init__(self, state: RepoState) -> None:
        self.state = state

    def create_branch(self, branch, base_sha, approval=None):
        assert approval is None
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
        approval=None,
    ):
        assert approval is None
        assert branch == self.state.branch
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

    def open_pull_request(
        self,
        *,
        title,
        head,
        base,
        body="",
        approval: ActionApproval | None = None,
    ):
        target = f"{head}->{base}"
        assert approval == ActionApproval("github.open_pull_request", target)
        self.state.prs.append(
            {"title": title, "head": head, "base": base, "body": body}
        )
        return ActionResult(
            decision=AutonomyDecision.REQUIRE_HUMAN,
            executed=True,
            value={
                "number": 41,
                "state": "open",
                "html_url": "https://example.invalid/pr/41",
            },
        )


class PlannerProvider:
    profile_name = "GLM-5.1"

    def __init__(self) -> None:
        self.calls = 0
        self.repository = ""
        self.feature_branch = ""

    def complete_with_tools(self, messages, tools):
        self.calls += 1
        assert tools == []
        if self.calls == 1:
            return {
                "role": "assistant",
                "content": json.dumps({"read_paths": ["README.md"]}),
            }
        return {
            "role": "assistant",
            "content": json.dumps(
                {
                    "repository": self.repository,
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
                    "validation_targets": [],
                    "summary": "Update README",
                }
            ),
        }


def _service(tmp_path, state: RepoState, *, profiles=None):
    read = FakeReadClient(state)
    mutation = FakeMutationClient(state)
    provider = PlannerProvider()
    service = DeterministicApp3TaskService(
        TaskExecutionConfig(
            enabled=True,
            provider_base_url="https://provider.invalid/v1",
            provider_model="test-model",
            provider_api_key_env="TEST_PROVIDER_KEY",
        ),
        state_path=tmp_path / "task-events.jsonl",
        read_factory=lambda repository: read,
        mutation_factory=lambda repository: mutation,
        provider_client=provider,
        profiles=profiles,
    )
    return service, provider


def _run_task(service, provider):
    preview = service.preview("score_restore", "Update README wording")
    provider.repository = preview.repository
    provider.feature_branch = preview.feature_branch
    service.run(preview.task_id)
    return preview


def test_human_validation_pr_breaks_pull_request_ci_deadlock(tmp_path) -> None:
    state = RepoState()
    service, provider = _service(tmp_path, state)
    preview = _run_task(service, provider)

    pending = service.refresh_evidence(preview.task_id)
    assert pending["stage"] == "CI_PENDING"
    assert pending["ci"]["state"] == "pending"
    assert {item["status"] for item in pending["validators"]} == {"PASS"}

    pr = service.open_pull_request(preview.task_id)
    after_pr = service.status(preview.task_id)

    assert pr["number"] == 41
    assert pr["validation_only"] is True
    assert pr["verification_status"] == "PENDING_CI"
    assert pr["merge_authorized"] is False
    assert after_pr["stage"] == "CI_PENDING"
    assert after_pr["outcome"] == "WORKING"
    assert after_pr["pull_request"]["number"] == 41
    assert len(state.prs) == 1

    state.workflow_runs = [
        {
            "id": 91,
            "name": "core-ci",
            "event": "pull_request",
            "status": "completed",
            "conclusion": "success",
            "head_sha": state.head_sha,
            "html_url": "https://example.invalid/run/91",
        }
    ]

    verified = service.refresh_evidence(preview.task_id)

    assert verified["stage"] == "VERIFIED_SUCCESS"
    assert verified["outcome"] == "VERIFIED_SUCCESS"
    assert verified["pull_request"]["number"] == 41
    assert service.open_pull_request(preview.task_id)["number"] == 41
    assert len(state.prs) == 1


def test_validation_pr_requires_all_configured_host_validators_to_pass(tmp_path) -> None:
    state = RepoState()
    profiles = {
        "score_restore": ProjectExecutionProfile(
            project="score_restore",
            validator_names=("exact_commit_binding", "domain_music_validator"),
        )
    }
    service, provider = _service(tmp_path, state, profiles=profiles)
    preview = _run_task(service, provider)

    pending = service.refresh_evidence(preview.task_id)
    assert any(item["status"] == "UNAVAILABLE" for item in pending["validators"])

    with pytest.raises(TaskExecutionError, match="all configured host validators"):
        service.open_pull_request(preview.task_id)

    assert state.prs == []
