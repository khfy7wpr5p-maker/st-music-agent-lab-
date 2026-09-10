from __future__ import annotations

from dataclasses import dataclass, field

import pytest

from st_music_agent.contracts import ModelProfile, TaskKind
from st_music_agent.credentials import MissingCredentialError
from st_music_agent.providers import OpenAICompatibleClient, OpenAICompatibleConfig
from st_music_agent.transport import JsonRequest, JsonResponse


@dataclass
class RecordingTransport:
    response: JsonResponse
    requests: list[JsonRequest] = field(default_factory=list)

    def request(self, request: JsonRequest) -> JsonResponse:
        self.requests.append(request)
        return self.response


def profile() -> ModelProfile:
    return ModelProfile(
        name="test-model",
        provider="test",
        task_kinds=frozenset({TaskKind.CODE}),
        context_window_tokens=32_000,
    )


def test_adapter_injects_secret_only_at_transport_boundary(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ST_TEST_API_KEY", "secret-value")
    transport = RecordingTransport(
        JsonResponse(
            status_code=200,
            payload={"choices": [{"message": {"role": "assistant", "content": "ok"}}]},
        )
    )
    config = OpenAICompatibleConfig(
        base_url="https://example.invalid/v1",
        model="provider-model-id",
        api_key_env="ST_TEST_API_KEY",
    )
    client = OpenAICompatibleClient(profile(), config, transport)

    message = client.complete(({"role": "user", "content": "fix tests"},))

    assert message["content"] == "ok"
    assert config.api_key_env == "ST_TEST_API_KEY"
    request = transport.requests[0]
    assert request.url == "https://example.invalid/v1/chat/completions"
    assert request.headers["Authorization"] == "Bearer secret-value"
    assert request.payload == {
        "model": "provider-model-id",
        "messages": [{"role": "user", "content": "fix tests"}],
    }


def test_adapter_fails_closed_when_credential_is_missing(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("ST_MISSING_API_KEY", raising=False)
    client = OpenAICompatibleClient(
        profile(),
        OpenAICompatibleConfig(
            base_url="https://example.invalid/v1",
            model="provider-model-id",
            api_key_env="ST_MISSING_API_KEY",
        ),
        RecordingTransport(JsonResponse(status_code=200, payload={})),
    )

    with pytest.raises(MissingCredentialError):
        client.complete(({"role": "user", "content": "hello"},))
