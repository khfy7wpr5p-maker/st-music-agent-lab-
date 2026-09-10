from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any, Protocol
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


class TransportError(RuntimeError):
    pass


@dataclass(frozen=True, slots=True)
class JsonRequest:
    method: str
    url: str
    payload: Mapping[str, Any] | None = None
    headers: Mapping[str, str] = field(default_factory=dict)
    timeout_seconds: float = 60.0


@dataclass(frozen=True, slots=True)
class JsonResponse:
    status_code: int
    payload: Mapping[str, Any]


class JsonTransport(Protocol):
    def request(self, request: JsonRequest) -> JsonResponse: ...


class UrllibJsonTransport:
    """Small dependency-free JSON HTTP transport for provider and agent adapters."""

    def request(self, request: JsonRequest) -> JsonResponse:
        body = None
        headers = {"Accept": "application/json", **request.headers}
        if request.payload is not None:
            body = json.dumps(request.payload).encode("utf-8")
            headers.setdefault("Content-Type", "application/json")

        raw_request = Request(
            request.url,
            data=body,
            headers=headers,
            method=request.method.upper(),
        )

        try:
            with urlopen(raw_request, timeout=request.timeout_seconds) as response:
                status_code = int(response.status)
                raw_body = response.read().decode("utf-8")
        except HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")
            raise TransportError(f"HTTP {exc.code} from remote service: {detail[:500]}") from exc
        except URLError as exc:
            raise TransportError(f"remote service connection failed: {exc.reason}") from exc

        if not raw_body.strip():
            return JsonResponse(status_code=status_code, payload={})

        try:
            decoded = json.loads(raw_body)
        except json.JSONDecodeError as exc:
            raise TransportError("remote service returned invalid JSON") from exc

        if not isinstance(decoded, dict):
            raise TransportError("remote service returned a non-object JSON payload")

        return JsonResponse(status_code=status_code, payload=decoded)
