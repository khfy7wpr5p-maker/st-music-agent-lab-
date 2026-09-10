from __future__ import annotations

import base64
from dataclasses import dataclass, field

import pytest

from st_music_agent.agent_tools import ToolCallRequest, ToolCallStatus, ToolRegistry
from st_music_agent.github_read import GitHubReadClient, GitHubReadConfig, GitHubReadError, GitHubReadToolset
from st_music_agent.transport import JsonRequest, JsonResponse


@dataclass
class QueueTransport:
    responses: list[JsonResponse]
    requests: list[JsonRequest] = field(default_factory=list)

    def request(self, request: JsonRequest) -> JsonResponse:
        self.requests.append(request)
        return self.responses.pop(0)


def test_read_file_decodes_utf8_and_bounds_raw_file_content() -> None:
    content = "x" * 2000
    transport = QueueTransport(
        [
            JsonResponse(
                status_code=200,
                payload={
                    "type": "file",
                    "encoding": "base64",
                    "content": base64.b64encode(content.encode()).decode(),
                    "sha": "abc1234",
                },
            )
        ]
    )
    client = GitHubReadClient(
        GitHubReadConfig(repository="owner/repo", max_file_chars=1024),
        transport,
    )

    result = client.read_file("docs/file name.md", ref="feature/test")

    assert result["content"] == "x" * 1024
    assert result["truncated"] is True
    assert result["sha"] == "abc1234"
    request = transport.requests[0]
    assert "/contents/docs/file%20name.md" in request.url
    assert "ref=feature%2Ftest" in request.url
    assert "Authorization" not in request.headers


def test_read_file_rejects_sensitive_paths_before_network_access() -> None:
    transport = QueueTransport([])
    client = GitHubReadClient(GitHubReadConfig(repository="owner/repo"), transport)

    for path in (
        ".env",
        ".env.production",
        ".npmrc",
        "credentials.json",
        "certs/private.key",
        ".ssh/id_ed25519",
        ".aws/credentials",
    ):
        with pytest.raises(ValueError, match="credential-sensitive"):
            client.read_file(path)

    assert transport.requests == []


def test_read_file_rejects_invalid_base64_instead_of_best_effort_decoding() -> None:
    transport = QueueTransport(
        [
            JsonResponse(
                status_code=200,
                payload={
                    "type": "file",
                    "encoding": "base64",
                    "content": "not!!base64",
                    "sha": "abc1234",
                },
            )
        ]
    )
    client = GitHubReadClient(GitHubReadConfig(repository="owner/repo"), transport)

    with pytest.raises(GitHubReadError, match="base64"):
        client.read_file("README.md")


def test_toolset_registers_only_explicit_read_tools() -> None:
    transport = QueueTransport(
        [
            JsonResponse(
                status_code=200,
                payload={
                    "full_name": "owner/repo",
                    "default_branch": "main",
                    "visibility": "public",
                    "archived": False,
                    "language": "Python",
                },
            )
        ]
    )
    registry = ToolRegistry()
    GitHubReadToolset(
        GitHubReadClient(GitHubReadConfig(repository="owner/repo"), transport)
    ).register_into(registry)

    assert registry.names() == (
        "github.branch_info",
        "github.pull_request",
        "github.read_file",
        "github.repo_metadata",
        "github.workflow_runs",
    )
    result = registry.dispatch(
        ToolCallRequest(call_id="call-1", tool_name="github.repo_metadata", arguments={})
    )

    assert result.status is ToolCallStatus.SUCCESS
    assert result.output["default_branch"] == "main"
    assert all(tool["type"] == "function" for tool in registry.provider_tools())


def test_tool_handlers_reject_provider_schema_bypass_fields() -> None:
    registry = ToolRegistry()
    GitHubReadToolset(
        GitHubReadClient(GitHubReadConfig(repository="owner/repo"), QueueTransport([]))
    ).register_into(registry)

    result = registry.dispatch(
        ToolCallRequest(
            call_id="call-1",
            tool_name="github.repo_metadata",
            arguments={"unexpected": "value"},
        )
    )

    assert result.status is ToolCallStatus.ERROR
    assert "unsupported fields" in (result.error or "")


def test_pull_request_projection_drops_unbounded_remote_fields() -> None:
    transport = QueueTransport(
        [
            JsonResponse(
                status_code=200,
                payload={
                    "number": 7,
                    "title": "Feature",
                    "state": "open",
                    "draft": False,
                    "mergeable": True,
                    "body": "very large body that should not be returned",
                    "head": {"ref": "feature", "sha": "a" * 40},
                    "base": {"ref": "main", "sha": "b" * 40},
                },
            )
        ]
    )
    client = GitHubReadClient(GitHubReadConfig(repository="owner/repo"), transport)

    result = client.pull_request(7)

    assert result == {
        "number": 7,
        "title": "Feature",
        "state": "open",
        "draft": False,
        "mergeable": True,
        "head_ref": "feature",
        "head_sha": "a" * 40,
        "base_ref": "main",
        "base_sha": "b" * 40,
    }
    assert "body" not in result


def test_workflow_runs_are_limited_and_projected() -> None:
    remote_runs = [
        {
            "id": index,
            "name": "core-ci",
            "event": "pull_request",
            "status": "completed",
            "conclusion": "success",
            "head_sha": "a" * 40,
            "html_url": f"https://github.example/runs/{index}",
            "logs_url": "unneeded",
        }
        for index in range(15)
    ]
    transport = QueueTransport(
        [JsonResponse(status_code=200, payload={"workflow_runs": remote_runs})]
    )
    client = GitHubReadClient(GitHubReadConfig(repository="owner/repo"), transport)

    result = client.workflow_runs("a" * 40)

    assert len(result["workflow_runs"]) == 10
    assert "logs_url" not in result["workflow_runs"][0]
    assert "per_page=10" in transport.requests[0].url
    assert f"head_sha={'a' * 40}" in transport.requests[0].url
