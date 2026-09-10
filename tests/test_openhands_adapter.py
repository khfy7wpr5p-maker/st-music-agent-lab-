from __future__ import annotations

from dataclasses import dataclass, field

import pytest

from st_music_agent.openhands import OpenHandsAgentServerClient, OpenHandsConfig
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
