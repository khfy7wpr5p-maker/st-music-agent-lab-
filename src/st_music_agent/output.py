from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any

from .sandbox import SandboxResult

_ANSI_ESCAPE = re.compile(r"\x1b\[[0-?]*[ -/]*[@-~]")
_BEARER_TOKEN = re.compile(r"(?i)\bBearer\s+[A-Za-z0-9._~+/=-]{8,}")
_COMMON_TOKEN = re.compile(r"\b(?:gh[pousr]_[A-Za-z0-9_]{16,}|sk-[A-Za-z0-9_-]{16,})\b")
_KEY_VALUE_SECRET = re.compile(
    r"(?i)\b(api[_-]?key|access[_-]?token|auth[_-]?token|token|password|secret)"
    r"\s*[:=]\s*([^\s,;]+)"
)
_SENSITIVE_KEY = re.compile(
    r"(?i)^(?:api[_-]?key|access[_-]?token|auth[_-]?token|token|password|secret)$"
)
_REDACTED = "[REDACTED]"


@dataclass(frozen=True, slots=True)
class OutputPolicy:
    max_chars_per_stream: int = 16_000
    truncation_marker: str = "\n...[TRUNCATED]"

    def __post_init__(self) -> None:
        if self.max_chars_per_stream < len(self.truncation_marker) + 64:
            raise ValueError("max_chars_per_stream is too small")


@dataclass(slots=True)
class OutputSanitizer:
    policy: OutputPolicy = field(default_factory=OutputPolicy)
    sensitive_values: tuple[str, ...] = ()

    def sanitize_text(self, text: str) -> str:
        sanitized = _ANSI_ESCAPE.sub("", text)
        for value in self.sensitive_values:
            if len(value) >= 4:
                sanitized = sanitized.replace(value, _REDACTED)
        sanitized = _BEARER_TOKEN.sub(f"Bearer {_REDACTED}", sanitized)
        sanitized = _COMMON_TOKEN.sub(_REDACTED, sanitized)
        sanitized = _KEY_VALUE_SECRET.sub(lambda match: f"{match.group(1)}={_REDACTED}", sanitized)
        return self._truncate(sanitized)

    def sanitize_value(self, value: Any, *, key: str | None = None) -> Any:
        if key is not None and _SENSITIVE_KEY.fullmatch(key):
            return _REDACTED
        if value is None or isinstance(value, (bool, int, float)):
            return value
        if isinstance(value, str):
            return self.sanitize_text(value)
        if isinstance(value, Mapping):
            return {
                str(item_key): self.sanitize_value(item_value, key=str(item_key))
                for item_key, item_value in value.items()
            }
        if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
            return [self.sanitize_value(item) for item in value]
        raise TypeError(f"unsupported model-facing value type: {type(value).__name__}")

    def sanitize_result(self, result: SandboxResult) -> SandboxResult:
        return SandboxResult(
            returncode=result.returncode,
            stdout=self.sanitize_text(result.stdout),
            stderr=self.sanitize_text(result.stderr),
        )

    def _truncate(self, text: str) -> str:
        limit = self.policy.max_chars_per_stream
        marker = self.policy.truncation_marker
        if len(text) <= limit:
            return text
        return f"{text[: limit - len(marker)]}{marker}"
