from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any
from urllib.parse import urlsplit

from .agent_tools import ToolRegistry
from .credentials import EnvCredential
from .transport import JsonRequest, JsonTransport, UrllibJsonTransport


class OpenHandsResponseError(RuntimeError):
    pass


@dataclass(frozen=True, slots=True)
class OpenHandsSTBridgeConfig:
    url: str
    bearer_token_env: str | None = None
    timeout_seconds: float = 60.0

    def __post_init__(self) -> None:
        parsed = urlsplit(self.url)
        if parsed.scheme not in {"http", "https"} or not parsed.hostname:
            raise ValueError("ST bridge URL must be an absolute HTTP/HTTPS URL")
        if parsed.username is not None or parsed.password is not None or parsed.fragment:
            raise ValueError("ST bridge URL must not contain user-info or fragments")
        if parsed.scheme == "http" and parsed.hostname not in {"localhost", "127.0.0.1", "::1"}:
            raise ValueError("non-loopback ST bridge URLs must use HTTPS")
        if self.bearer_token_env is not None and not self.bearer_token_env.strip():
            raise ValueError("bearer_token_env must not be empty when provided")
        if self.timeout_seconds <= 0 or self.timeout_seconds > 300:
            raise ValueError("ST bridge timeout must be > 0 and <= 300 seconds")

    def as_mcp_server(self) -> dict[str, Any]:
        server: dict[str, Any] = {
            "url": self.url,
            "transport": "streamable-http",
            "timeout": self.timeout_seconds,
        }
        if self.bearer_token_env:
            token = EnvCredential(self.bearer_token_env).resolve()
            server["headers"] = {"Authorization": f"Bearer {token}"}
        return server


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
        """Start the legacy reasoning-only conversation with no external tools."""
        return self._start(instruction, agent_overrides={})

    def start_st_bridged_conversation(
        self,
        instruction: str,
        bridge: OpenHandsSTBridgeConfig,
        registry: ToolRegistry,
    ) -> OpenHandsConversation:
        """Start OpenHands with only ST-registry MCP tools plus safe finish/think built-ins."""
        tool_names = registry.names()
        if not tool_names:
            raise ValueError("ST bridge registry must expose at least one tool")
        allowed = ("finish", "think", *tool_names)
        filter_regex = "^(?:" + "|".join(re.escape(name) for name in allowed) + ")$"
        overrides = {
            "mcp_config": {"st_tools": bridge.as_mcp_server()},
            "filter_tools_regex": filter_regex,
            "include_default_tools": ["FinishTool", "ThinkTool"],
        }
        return self._start(instruction, agent_overrides=overrides)

    def _start(
        self,
        instruction: str,
        *,
        agent_overrides: dict[str, Any],
    ) -> OpenHandsConversation:
        if not instruction.strip():
            raise ValueError("instruction must not be empty")

        llm: dict[str, Any] = {"model": self._config.agent_model}
        if self._config.provider_api_key_env:
            llm["api_key"] = EnvCredential(self._config.provider_api_key_env).resolve()
        if self._config.llm_base_url:
            llm["base_url"] = self._config.llm_base_url

        agent: dict[str, Any] = {"kind": "Agent", "llm": llm, "tools": []}
        agent.update(agent_overrides)
        payload: dict[str, Any] = {
            "agent": agent,
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
