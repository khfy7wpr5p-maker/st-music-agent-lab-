from __future__ import annotations

import re
from dataclasses import dataclass, field

import pytest

from st_music_agent.agent_tools import ToolRegistry
from st_music_agent.openhands import (
    OpenHandsAgentServerClient,
    OpenHandsConfig,
    OpenHandsSTBridgeConfig,
)
from st_music_agent.transport import JsonRequest, JsonResponse


@dataclass
class RecordingTransport:
    responses: list[JsonResponse]
    requests: list[JsonRequest] = field(default_factory=list)

    def request(self, request: JsonRequest) -> JsonResponse:
        self.requests.append(request)
        return self.responses.pop(0)


def test_openhands_adapter_builds_current_conversation_contract(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("ST_PROVIDER_KEY", "provider-secret")
    monkeypatch.setenv("ST_OH_SESSION", "session-secret")
    transport = RecordingTransport(
        [JsonResponse(status_code=201, payload={"id": "conversation-123"})]
    )
    config = OpenHandsConfig(
        base_url="http://127.0.0.1:8000",
        agent_model="glm-5.1",
        working_dir="/workspace/repo",
        provider_api_key_env="ST_PROVIDER_KEY",
        llm_base_url="https://provider.example/v1",
        session_api_key_env="ST_OH_SESSION",
    )
    client = OpenHandsAgentServerClient(config, transport)

    conversation = client.start_conversation("inspect and repair the repository")

    assert conversation.conversation_id == "conversation-123"
    request = transport.requests[0]
    assert request.url == "http://127.0.0.1:8000/api/conversations"
    assert request.headers["X-Session-API-Key"] == "session-secret"
    assert request.payload == {
        "agent": {
            "kind": "Agent",
            "llm": {
                "model": "glm-5.1",
                "api_key": "provider-secret",
                "base_url": "https://provider.example/v1",
            },
            "tools": [],
        },
        "workspace": {"working_dir": "/workspace/repo"},
        "initial_message": {
            "role": "user",
            "content": [{"type": "text", "text": "inspect and repair the repository"}],
            "run": True,
        },
    }


def test_openhands_st_bridge_payload_exposes_only_registry_tools_and_safe_builtins(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("ST_BRIDGE_TOKEN", "bridge-secret")
    transport = RecordingTransport(
        [JsonResponse(status_code=201, payload={"id": "conversation-bridge"})]
    )
    client = OpenHandsAgentServerClient(
        OpenHandsConfig(
            base_url="http://127.0.0.1:8000",
            agent_model="test-model",
            working_dir="/workspace/repo",
        ),
        transport,
    )
    registry = ToolRegistry()
    registry.register("github.repo_metadata", lambda arguments: {"ok": True})
    registry.register("github.read_file", lambda arguments: {"content": "safe"})

    conversation = client.start_st_bridged_conversation(
        "inspect repository",
        OpenHandsSTBridgeConfig(
            url="https://bridge.example/mcp",
            bearer_token_env="ST_BRIDGE_TOKEN",
        ),
        registry,
    )

    assert conversation.conversation_id == "conversation-bridge"
    agent = transport.requests[0].payload["agent"]
    assert agent["tools"] == []
    assert agent["include_default_tools"] == ["FinishTool", "ThinkTool"]
    assert agent["mcp_config"] == {
        "st_tools": {
            "url": "https://bridge.example/mcp",
            "transport": "streamable-http",
            "timeout": 60.0,
            "headers": {"Authorization": "Bearer bridge-secret"},
        }
    }
    pattern = re.compile(agent["filter_tools_regex"])
    assert pattern.fullmatch("finish")
    assert pattern.fullmatch("think")
    assert pattern.fullmatch("github.repo_metadata")
    assert pattern.fullmatch("github.read_file")
    assert not pattern.fullmatch("terminal")
    assert not pattern.fullmatch("file_editor")
    assert not pattern.fullmatch("bash")


def test_openhands_st_bridge_rejects_empty_registry_before_network_access() -> None:
    transport = RecordingTransport([])
    client = OpenHandsAgentServerClient(
        OpenHandsConfig(
            base_url="http://127.0.0.1:8000",
            agent_model="test-model",
            working_dir="/workspace/repo",
        ),
        transport,
    )

    with pytest.raises(ValueError, match="at least one tool"):
        client.start_st_bridged_conversation(
            "inspect repository",
            OpenHandsSTBridgeConfig(url="https://bridge.example/mcp"),
            ToolRegistry(),
        )

    assert transport.requests == []


@pytest.mark.parametrize(
    "url",
    (
        "ftp://bridge.example/mcp",
        "http://bridge.example/mcp",
        "https://user:pass@bridge.example/mcp",
        "https://bridge.example/mcp#fragment",
    ),
)
def test_openhands_st_bridge_rejects_unsafe_endpoint_urls(url: str) -> None:
    with pytest.raises(ValueError):
        OpenHandsSTBridgeConfig(url=url)


def test_openhands_st_bridge_allows_loopback_http_for_local_sidecars() -> None:
    config = OpenHandsSTBridgeConfig(url="http://127.0.0.1:9000/mcp")

    assert config.as_mcp_server() == {
        "url": "http://127.0.0.1:9000/mcp",
        "transport": "streamable-http",
        "timeout": 60.0,
    }


def test_openhands_adapter_fetches_conversation() -> None:
    transport = RecordingTransport(
        [JsonResponse(status_code=200, payload={"id": "conversation-123", "status": "running"})]
    )
    client = OpenHandsAgentServerClient(
        OpenHandsConfig(
            base_url="http://127.0.0.1:8000",
            agent_model="test-model",
            working_dir="/workspace/repo",
        ),
        transport,
    )

    payload = client.get_conversation("conversation-123")

    assert payload["status"] == "running"
    assert transport.requests[0].url.endswith("/api/conversations/conversation-123")
