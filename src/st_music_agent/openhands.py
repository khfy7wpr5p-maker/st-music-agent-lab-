from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .credentials import EnvCredential
from .transport import JsonRequest, JsonTransport, UrllibJsonTransport


class OpenHandsResponseError(RuntimeError):
    pass


@dataclass(frozen=True, slots=True)
class OpenHandsConfig:
    base_url: str
    agent_model: str
    working_dir: str
    provider_api_key_env: str | None = None
    llm_base_url: str | None = None
    session_api_key_env: str | None = None
    timeout_seconds: float = 120.0

    def endpoint(self, path: str) -> str:
        return f"{self.base_url.rstrip('/')}/api/{path.lstrip('/')}"


@dataclass(frozen=True, slots=True)
class OpenHandsConversation:
    conversation_id: str
    payload: dict[str, Any]


class OpenHandsAgentServerClient:
    """Thin adapter around the public OpenHands Agent Server REST boundary."""

    def __init__(
        self,
        config: OpenHandsConfig,
        transport: JsonTransport | None = None,
    ) -> None:
        self._config = config
        self._transport = transport or UrllibJsonTransport()

    def start_conversation(self, instruction: str) -> OpenHandsConversation:
        if not instruction.strip():
            raise ValueError("instruction must not be empty")

        llm: dict[str, Any] = {"model": self._config.agent_model}
        if self._config.provider_api_key_env:
            llm["api_key"] = EnvCredential(self._config.provider_api_key_env).resolve()
        if self._config.llm_base_url:
            llm["base_url"] = self._config.llm_base_url

        payload: dict[str, Any] = {
            "agent": {"kind": "Agent", "llm": llm, "tools": []},
            "workspace": {"working_dir": self._config.working_dir},
            "initial_message": {
                "role": "user",
                "content": [{"type": "text", "text": instruction}],
                "run": True,
            },
        }
        response = self._transport.request(
            JsonRequest(
                method="POST",
                url=self._config.endpoint("conversations"),
                payload=payload,
                headers=self._headers(),
                timeout_seconds=self._config.timeout_seconds,
            )
        )
        if response.status_code != 201:
            raise OpenHandsResponseError(
                f"OpenHands conversation start returned status {response.status_code}"
            )

        conversation_id = response.payload.get("id")
        if not isinstance(conversation_id, str) or not conversation_id:
            raise OpenHandsResponseError("OpenHands response does not contain a conversation id")

        return OpenHandsConversation(
            conversation_id=conversation_id,
            payload=dict(response.payload),
        )

    def get_conversation(self, conversation_id: str) -> dict[str, Any]:
        if not conversation_id.strip():
            raise ValueError("conversation_id must not be empty")

        response = self._transport.request(
            JsonRequest(
                method="GET",
                url=self._config.endpoint(f"conversations/{conversation_id}"),
                headers=self._headers(),
                timeout_seconds=self._config.timeout_seconds,
            )
        )
        if response.status_code != 200:
            raise OpenHandsResponseError(
                f"OpenHands conversation fetch returned status {response.status_code}"
            )
        return dict(response.payload)

    def _headers(self) -> dict[str, str]:
        if not self._config.session_api_key_env:
            return {}
        session_key = EnvCredential(self._config.session_api_key_env).resolve()
        return {"X-Session-API-Key": session_key}
