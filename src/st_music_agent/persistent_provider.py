from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from urllib.parse import urlsplit


DEFAULT_MODEL = "qwen3:4b"
DEFAULT_API_KEY_ENV = "ST_QWEN_API_KEY"


@dataclass(frozen=True, slots=True)
class PersistentProviderSettings:
    """Generic persistent OpenAI-compatible provider settings.

    This intentionally contains no Colab- or tunnel-specific assumptions. A provider may run on
    a rented GPU, a local workstation, or any other long-lived host as long as it exposes the
    OpenAI-compatible ``/v1/chat/completions`` contract used by the agent.
    """

    base_url: str
    model: str = DEFAULT_MODEL
    api_key_env: str = DEFAULT_API_KEY_ENV

    @classmethod
    def from_env(cls, env: Mapping[str, str]) -> "PersistentProviderSettings":
        base_url = env.get("ST_QWEN_BASE_URL", "").strip()
        model = env.get("ST_QWEN_MODEL", DEFAULT_MODEL).strip() or DEFAULT_MODEL
        api_key_env = env.get("ST_QWEN_API_KEY_ENV", DEFAULT_API_KEY_ENV).strip()
        if not base_url:
            raise ValueError("ST_QWEN_BASE_URL is required")
        parsed = urlsplit(base_url)
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            raise ValueError("ST_QWEN_BASE_URL must be an absolute HTTP/HTTPS URL")
        if not api_key_env:
            raise ValueError("ST_QWEN_API_KEY_ENV must not be empty")
        return cls(base_url=base_url.rstrip("/"), model=model, api_key_env=api_key_env)

    def health_url(self) -> str:
        parsed = urlsplit(self.base_url)
        path = parsed.path.rstrip("/")
        if path.endswith("/v1"):
            path = path[:-3]
        return parsed._replace(path=f"{path}/health" or "/health", query="", fragment="").geturl()

    def cli_args(self) -> tuple[str, ...]:
        return (
            "--provider-base-url",
            self.base_url,
            "--provider-model",
            self.model,
            "--provider-api-key-env",
            self.api_key_env,
        )
