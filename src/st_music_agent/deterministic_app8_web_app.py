from __future__ import annotations

import hashlib
import os
from http.server import ThreadingHTTPServer
from pathlib import Path

from .app7_web_app import _LOOPBACK_HOSTS, _MIN_REMOTE_TOKEN_CHARS
from .app8_graph_state import App8GraphStore
from .app8_web_app import App8OperatorConsoleApplication
from .deterministic_task_execution import DeterministicApp7TaskService
from .operator_console import OperatorConsoleService
from .task_execution import TaskExecutionConfig
from .web_app import make_handler


def serve_operator_console(
    *,
    host: str = "127.0.0.1",
    port: int = 8765,
    token_env: str | None = "GITHUB_TOKEN",
    api_base: str = "https://api.github.com",
    task_config: TaskExecutionConfig | None = None,
    state_path: str | Path | None = None,
    graph_state_path: str | Path | None = None,
    remote_read_only: bool = False,
    remote_auth_token_env: str | None = None,
    remote_secure_transport_attested: bool = False,
) -> None:
    """APP8E server using deterministic local task mutation when writes are enabled."""
    if not 1 <= port <= 65535:
        raise ValueError("port must be between 1 and 65535")
    config = task_config or TaskExecutionConfig(
        enabled=False,
        github_token_env=token_env or "GITHUB_TOKEN",
        github_api_base=api_base,
    )
    non_loopback = host not in _LOOPBACK_HOSTS
    if remote_read_only:
        if config.enabled:
            raise ValueError("APP8E remote mode is read-only and cannot enable task writes")
        if not remote_auth_token_env:
            raise ValueError("APP8E remote mode requires --remote-auth-token-env")
        raw_token = os.environ.get(remote_auth_token_env)
        if not isinstance(raw_token, str) or len(raw_token) < _MIN_REMOTE_TOKEN_CHARS:
            raise ValueError("remote auth token must contain at least 24 characters")
        if non_loopback and not remote_secure_transport_attested:
            raise ValueError(
                "non-loopback APP8E remote mode requires explicit secure-transport attestation"
            )
        remote_digest = hashlib.sha256(raw_token.encode("utf-8")).hexdigest()
    else:
        if non_loopback:
            raise ValueError(
                "APP8E non-loopback binding is allowed only in authenticated remote read-only mode"
            )
        remote_digest = None

    service = OperatorConsoleService(token_env=token_env, api_base=api_base)
    task_service = DeterministicApp7TaskService(config, state_path=state_path)
    graph_store = App8GraphStore(graph_state_path)
    application = App8OperatorConsoleApplication(
        service,
        task_service,
        graph_store,
        remote_read_only=remote_read_only,
        remote_auth_digest=remote_digest,
    )
    server = ThreadingHTTPServer((host, port), make_handler(application))
    print(f"ST Music Agent APP8E operator console: http://{host}:{port}")
    print(f"APP8 graph journal: {graph_store.path}")
    if remote_read_only:
        print("Mode: authenticated remote READ-ONLY; task and graph mutations unavailable.")
        if non_loopback:
            print("Transport: operator explicitly attested a private/encrypted transport boundary.")
    elif application.writes_enabled:
        print("Mode: MODEL_PLANS_HOST_EXECUTES + APP2-APP7 evidence + APP8 observability.")
        print("Local model has no direct write/PR/merge tools; APP8 graph surface is read-only.")
    else:
        print("Mode: local read/review/audit + persistent APP8 graph observability.")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
