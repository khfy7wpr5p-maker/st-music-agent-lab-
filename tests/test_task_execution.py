from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any

import pytest

from st_music_agent.policy import AutonomyDecision
from st_music_agent.task_execution import (
    BoundTaskWriteToolset,
    GuardedTaskService,
    TaskExecutionConfig,
    TaskExecutionError,
    TaskGitHubReadClient,
)
from st_music_agent.tools import ActionApproval, ActionResult
from st_music_agent.transport import JsonRequest, JsonResponse


@dataclass
class SharedRepoState:
    base_sha: str = "a" * 40
    head_sha: str = "a" * 40
    branch: str | None = None
    writes: list[dict[str, Any]] = field(default_factory=list)
    prs: list[dict[str, Any]] = field(default_factory=list)


class FakeReadClient:
    def __init__(self, state: SharedRepoState) -> None:
        self.state = state

    def repository_metadata(self) -> dict[str, Any]:
        return {"full_name": "owner/repo", "default_branch": "main"}

    def repository_tree(self, ref: str = "main") -> dict[str, Any]:
        return {
            "ref": ref,
            "commit_sha": self.state.head_sha if ref == self.state.branch else self.state.base_sha,
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
        return {
            "workflow_runs": [
                {
                    "id": 7,
                    "name": "core-ci",
                    "event": "push",
                    "status": "completed",
                    "conclusion": "success",
                    "head_sha": head_sha,
                    "html_url": "https://example.invalid/run/7",
                }
            ]
        }


class FakeMutationClient:
    def __init__(self, state: SharedRepoState) -> None:
        self.state = state

    def create_branch(
        self,
        branch: str,
        base_sha: str,
        approval: ActionApproval | None = None,
    ) -> ActionResult:
        assert approval is None
        assert base_sha == self.state.base_sha
        assert branch.startswith("st-agent/")
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
        assert branch not in {"main", "master"}
        self.state.writes.append(
            {
                "path": path,
                "content": content,
                "commit_message": commit_message,
                "branch": branch,
                "sha": sha,
            }
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
            value={"number": 12, "title": title, "state": "open", "html_url": "https://example.invalid/pr/12"},
        )


class ScriptedProvider:
    profile_name = "GLM-5.1"

    def __init__(self) -> None:
        self.turn = 0

    def complete_with_tools(self, messages, tools):
        names = {tool["function"]["name"] for tool in tools}
        assert "task.write_file" in names
        assert "github.tree" in names
        assert "github.create_branch" not in names
        assert "github.open_pull_request" not in names
        self.turn += 1
        if self.turn == 1:
            return {
                "role": "assistant",
                "content": None,
                "tool_calls": [
                    {
                        "id": "tree-1",
                        "type": "function",
                        "function": {"name": "github.tree", "arguments": json.dumps({"ref": "main"})},
                    }
                ],
            }
        if self.turn == 2:
            return {
                "role": "assistant",
                "content": None,
                "tool_calls": [
                    {
                        "id": "read-1",
                        "type": "function",
                        "function": {
                            "name": "github.read_file",
                            "arguments": json.dumps({"path": "README.md", "ref": "main"}),
                        },
                    }
                ],
            }
        if self.turn == 3:
            return {
                "role": "assistant",
                "content": None,
                "tool_calls": [
                    {
                        "id": "write-1",
                        "type": "function",
                        "function": {
                            "name": "task.write_file",
                            "arguments": json.dumps(
                                {
                                    "path": "README.md",
                                    "content": "after\n",
                                    "commit_message": "Update README",
                                    "sha": "c" * 40,
                                }
                            ),
                        },
                    }
                ],
            }
        return {"role": "assistant", "content": "Updated README on the task branch."}


def _service(enabled: bool = True):
    state = SharedRepoState()
    read = FakeReadClient(state)
    mutation = FakeMutationClient(state)
    provider = ScriptedProvider()
    config = TaskExecutionConfig(
        enabled=enabled,
        provider_base_url="https://provider.invalid/v1" if enabled else None,
        provider_model="test-model" if enabled else None,
        provider_api_key_env="TEST_PROVIDER_KEY" if enabled else None,
    )
    service = GuardedTaskService(
        config,
        read_factory=lambda repository: read,
        mutation_factory=lambda repository: mutation,
        provider_client=provider,
    )
    return service, state


def test_preview_is_deterministic_and_policy_keeps_pr_human_gated() -> None:
    service, _state = _service(enabled=False)
    first = service.preview("score_restore", "Update documentation")
    second = service.preview("score_restore", "  Update   documentation  ")

    assert first == second
    assert first.feature_branch.startswith("st-agent/score_restore/")
    assert first.feature_branch not in {"main", "master"}
    assert first.create_branch_decision is AutonomyDecision.AUTO_EXECUTE
    assert first.write_file_decision is AutonomyDecision.AUTO_EXECUTE
    assert first.pull_request_decision is AutonomyDecision.REQUIRE_HUMAN
    assert first.production_actions_authorized is False


def test_run_is_disabled_by_default_even_after_valid_preview() -> None:
    service, state = _service(enabled=False)
    preview = service.preview("score_editor", "Change one file")

    with pytest.raises(TaskExecutionError, match="--enable-writes"):
        service.run(preview.task_id)

    assert state.branch is None
    assert state.writes == []


def test_agent_can_write_only_to_host_bound_feature_branch() -> None:
    service, state = _service(enabled=True)
    preview = service.preview("musicxml_guitar_tab", "Update README wording")
    record = service.run(preview.task_id)

    assert state.branch == preview.feature_branch
    assert record.head_sha == "b" * 40
    assert record.tool_calls == 3
    assert len(state.writes) == 1
    assert state.writes[0]["branch"] == preview.feature_branch
    assert record.workflow_runs[0]["conclusion"] == "success"
    assert record.as_dict()["merge_authorized"] is False


def test_bound_write_tool_has_no_branch_argument() -> None:
    _service_instance, state = _service(enabled=True)
    mutation = FakeMutationClient(state)
    toolset = BoundTaskWriteToolset(mutation, "st-agent/test/fixed")
    from st_music_agent.agent_tools import ToolCallRequest, ToolCallStatus, ToolRegistry

    registry = ToolRegistry()
    toolset.register_into(registry)
    result = registry.dispatch(
        ToolCallRequest(
            call_id="bad-branch",
            tool_name="task.write_file",
            arguments={
                "path": "README.md",
                "content": "x",
                "commit_message": "x" * 32,
                "branch": "main",
            },
        )
    )

    assert result.status is ToolCallStatus.ERROR
    assert "unsupported fields" in (result.error or "")
    assert state.writes == []


def test_pull_request_is_only_opened_by_explicit_host_method_after_run() -> None:
    service, state = _service(enabled=True)
    preview = service.preview("score_restore", "Update README wording")

    with pytest.raises(TaskExecutionError, match="run successfully"):
        service.open_pull_request(preview.task_id)

    service.run(preview.task_id)
    pr = service.open_pull_request(preview.task_id)

    assert pr["number"] == 12
    assert len(state.prs) == 1
    assert state.prs[0]["head"] == preview.feature_branch
    assert state.prs[0]["base"] == "main"


@dataclass
class QueueTransport:
    responses: list[JsonResponse]
    requests: list[JsonRequest] = field(default_factory=list)

    def request(self, request: JsonRequest) -> JsonResponse:
        self.requests.append(request)
        return self.responses.pop(0)


def test_repository_tree_is_bounded_and_filters_sensitive_paths() -> None:
    transport = QueueTransport(
        [
            JsonResponse(
                status_code=200,
                payload={"name": "main", "protected": True, "commit": {"sha": "a" * 40}},
            ),
            JsonResponse(
                status_code=200,
                payload={
                    "truncated": False,
                    "tree": [
                        {"path": "README.md", "type": "blob", "sha": "b" * 40, "size": 12},
                        {"path": ".env", "type": "blob", "sha": "c" * 40, "size": 12},
                        {"path": ".ssh/id_rsa", "type": "blob", "sha": "d" * 40, "size": 12},
                        {"path": "docs/guide.md", "type": "blob", "sha": "e" * 40, "size": 20},
                    ],
                },
            ),
        ]
    )
    client = TaskGitHubReadClient(
        __import__("st_music_agent.github_read", fromlist=["GitHubReadConfig"]).GitHubReadConfig(
            repository="owner/repo"
        ),
        transport,
    )

    result = client.repository_tree("main")

    assert [item["path"] for item in result["files"]] == ["README.md", "docs/guide.md"]
    assert "recursive=1" in transport.requests[1].url


def test_repository_tree_rejects_github_truncation() -> None:
    transport = QueueTransport(
        [
            JsonResponse(
                status_code=200,
                payload={"name": "main", "protected": True, "commit": {"sha": "a" * 40}},
            ),
            JsonResponse(status_code=200, payload={"truncated": True, "tree": []}),
        ]
    )
    from st_music_agent.github_read import GitHubReadConfig, GitHubReadError

    client = TaskGitHubReadClient(GitHubReadConfig(repository="owner/repo"), transport)
    with pytest.raises(GitHubReadError, match="truncated"):
        client.repository_tree("main")
