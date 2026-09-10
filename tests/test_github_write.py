from __future__ import annotations

import base64
from dataclasses import dataclass, field

import pytest

from st_music_agent.agent_tools import ToolCallRequest, ToolCallStatus, ToolRegistry
from st_music_agent.github_write import (
    GitHubMutationClient,
    GitHubMutationConfig,
    GitHubMutationToolset,
)
from st_music_agent.policy import AutonomyDecision
from st_music_agent.tools import ActionApproval
from st_music_agent.transport import JsonRequest, JsonResponse


@dataclass
class QueueTransport:
    responses: list[JsonResponse]
    requests: list[JsonRequest] = field(default_factory=list)

    def request(self, request: JsonRequest) -> JsonResponse:
        self.requests.append(request)
        return self.responses.pop(0)


def config() -> GitHubMutationConfig:
    return GitHubMutationConfig(repository="owner/repo", token_env="ST_GITHUB_TOKEN")


def test_feature_branch_creation_auto_executes_and_keeps_token_at_transport_boundary(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("ST_GITHUB_TOKEN", "secret-token")
    transport = QueueTransport(
        [
            JsonResponse(
                status_code=201,
                payload={"ref": "refs/heads/feature/a9", "object": {"sha": "a" * 40}},
            )
        ]
    )
    client = GitHubMutationClient(config(), transport=transport)

    result = client.create_branch("feature/a9", "a" * 40)

    assert result.executed is True
    assert result.decision is AutonomyDecision.AUTO_EXECUTE
    assert result.value == {"ref": "refs/heads/feature/a9", "sha": "a" * 40}
    request = transport.requests[0]
    assert request.method == "POST"
    assert request.url.endswith("/repos/owner/repo/git/refs")
    assert request.payload == {"ref": "refs/heads/feature/a9", "sha": "a" * 40}
    assert request.headers["Authorization"] == "Bearer secret-token"


def test_protected_branch_creation_requires_human_before_network_access(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("ST_GITHUB_TOKEN", "secret-token")
    transport = QueueTransport([])
    client = GitHubMutationClient(config(), transport=transport)

    result = client.create_branch("main", "a" * 40)

    assert result.executed is False
    assert result.decision is AutonomyDecision.REQUIRE_HUMAN
    assert transport.requests == []


def test_feature_branch_file_write_auto_executes_with_bounded_projection(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("ST_GITHUB_TOKEN", "secret-token")
    transport = QueueTransport(
        [
            JsonResponse(
                status_code=200,
                payload={
                    "content": {"sha": "b" * 40, "name": "ignored"},
                    "commit": {"sha": "c" * 40, "message": "ignored"},
                },
            )
        ]
    )
    client = GitHubMutationClient(config(), transport=transport)

    result = client.write_file(
        path="src/example.py",
        content="print('ok')\n",
        commit_message="A9: update example",
        branch="feature/a9",
        sha="d" * 40,
    )

    assert result.executed is True
    assert result.value == {
        "path": "src/example.py",
        "branch": "feature/a9",
        "commit_sha": "c" * 40,
        "content_sha": "b" * 40,
    }
    request = transport.requests[0]
    assert request.method == "PUT"
    assert request.url.endswith("/repos/owner/repo/contents/src/example.py")
    assert request.payload["branch"] == "feature/a9"
    assert request.payload["sha"] == "d" * 40
    assert base64.b64decode(request.payload["content"]).decode() == "print('ok')\n"


def test_protected_branch_file_write_is_gated_before_token_resolution(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("ST_GITHUB_TOKEN", raising=False)
    transport = QueueTransport([])
    client = GitHubMutationClient(config(), transport=transport)

    result = client.write_file(
        path="README.md",
        content="change",
        commit_message="change readme",
        branch="main",
    )

    assert result.executed is False
    assert result.decision is AutonomyDecision.REQUIRE_HUMAN
    assert transport.requests == []


def test_credential_sensitive_write_is_rejected_before_policy_or_network() -> None:
    transport = QueueTransport([])
    client = GitHubMutationClient(config(), transport=transport)

    for path in (".env", ".env.production", ".ssh/id_rsa", "certs/private.pem"):
        with pytest.raises(ValueError, match="credential-sensitive"):
            client.write_file(
                path=path,
                content="secret",
                commit_message="unsafe",
                branch="feature/a9",
            )

    assert transport.requests == []


def test_delete_requires_exact_human_approval(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("ST_GITHUB_TOKEN", "secret-token")
    transport = QueueTransport(
        [
            JsonResponse(
                status_code=200,
                payload={"commit": {"sha": "e" * 40}},
            )
        ]
    )
    client = GitHubMutationClient(config(), transport=transport)

    blocked = client.delete_file(
        path="docs/old.md",
        sha="d" * 40,
        commit_message="remove obsolete doc",
        branch="feature/a9",
    )
    assert blocked.executed is False
    assert blocked.decision is AutonomyDecision.REQUIRE_HUMAN
    assert transport.requests == []

    approved = client.delete_file(
        path="docs/old.md",
        sha="d" * 40,
        commit_message="remove obsolete doc",
        branch="feature/a9",
        approval=ActionApproval(
            action_name="github.delete_file",
            target="feature/a9:docs/old.md",
        ),
    )
    assert approved.executed is True
    assert approved.value["commit_sha"] == "e" * 40
    assert transport.requests[0].method == "DELETE"


def test_pull_request_creation_requires_exact_human_approval(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("ST_GITHUB_TOKEN", "secret-token")
    transport = QueueTransport(
        [
            JsonResponse(
                status_code=201,
                payload={
                    "number": 12,
                    "title": "A9",
                    "state": "open",
                    "html_url": "https://github.example/pr/12",
                },
            )
        ]
    )
    client = GitHubMutationClient(config(), transport=transport)

    blocked = client.open_pull_request(title="A9", head="feature/a9", base="main")
    assert blocked.executed is False
    assert blocked.decision is AutonomyDecision.REQUIRE_HUMAN
    assert transport.requests == []

    approved = client.open_pull_request(
        title="A9",
        head="feature/a9",
        base="main",
        approval=ActionApproval(
            action_name="github.open_pull_request",
            target="feature/a9->main",
        ),
    )
    assert approved.executed is True
    assert approved.value["number"] == 12
    assert transport.requests[0].method == "POST"
    assert transport.requests[0].url.endswith("/repos/owner/repo/pulls")


def test_model_toolset_exposes_only_reversible_mutation_tools(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("ST_GITHUB_TOKEN", "secret-token")
    transport = QueueTransport(
        [
            JsonResponse(
                status_code=201,
                payload={"ref": "refs/heads/feature/a9", "object": {"sha": "a" * 40}},
            )
        ]
    )
    registry = ToolRegistry()
    GitHubMutationToolset(GitHubMutationClient(config(), transport=transport)).register_into(
        registry
    )

    assert registry.names() == ("github.create_branch", "github.write_file")
    result = registry.dispatch(
        ToolCallRequest(
            call_id="call-1",
            tool_name="github.create_branch",
            arguments={"branch": "feature/a9", "base_sha": "a" * 40},
        )
    )
    assert result.status is ToolCallStatus.SUCCESS
    assert result.output["executed"] is True
    assert "github.delete_file" not in registry.names()
    assert "github.open_pull_request" not in registry.names()
