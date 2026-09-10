from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from ..contracts import ModelProfile
from ..credentials import EnvCredential
from ..transport import JsonRequest, JsonTransport, UrllibJsonTransport


class ProviderResponseError(RuntimeError):
    pass


@dataclass(frozen=True, slots=True)
class OpenAICompatibleConfig:
    base_url: str
    model: str
    api_key_env: str
    timeout_seconds: float = 120.0

    def endpoint(self) -> str:
        return f"{self.base_url.rstrip('/')}/chat/completions"


class OpenAICompatibleClient:
    """Provider-neutral chat-completions adapter.

    This supports providers exposing an OpenAI-compatible endpoint while keeping
    their SDKs and secrets outside the ST core contracts.
    """

    def __init__(
        self,
        profile: ModelProfile,
        config: OpenAICompatibleConfig,
        transport: JsonTransport | None = None,
    ) -> None:
        self._profile = profile
        self._config = config
        self._transport = transport or UrllibJsonTransport()

    @property
    def profile(self) -> ModelProfile:
        return self._profile

    def complete(self, messages: Sequence[Mapping[str, Any]]) -> Mapping[str, Any]:
        api_key = EnvCredential(self._config.api_key_env).resolve()
        response = self._transport.request(
            JsonRequest(
                method="POST",
                url=self._config.endpoint(),
                payload={"model": self._config.model, "messages": list(messages)},
                headers={"Authorization": f"Bearer {api_key}"},
                timeout_seconds=self._config.timeout_seconds,
            )
        )

        if not 200 <= response.status_code < 300:
            raise ProviderResponseError(
                f"provider returned unexpected status {response.status_code}"
            )

        choices = response.payload.get("choices")
        if not isinstance(choices, list) or not choices:
            raise ProviderResponseError("provider response does not contain choices")

        first_choice = choices[0]
        if not isinstance(first_choice, dict):
            raise ProviderResponseError("provider response contains an invalid choice")

        message = first_choice.get("message")
        if not isinstance(message, dict):
            raise ProviderResponseError("provider response does not contain a message")

        return message
