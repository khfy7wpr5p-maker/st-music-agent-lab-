from __future__ import annotations

import hashlib
import json
from types import SimpleNamespace

import pytest

from st_music_agent import app7_web_app as app7web
from st_music_agent.app7_web_app import App7OperatorConsoleApplication
from st_music_agent.operator_console import OperatorConsoleService
from st_music_agent.task_execution import TaskExecutionConfig


class FakeTaskService:
    def __init__(self, *, enabled: bool = False) -> None:
        self.config = TaskExecutionConfig(
            enabled=enabled,
            provider_base_url="https://provider.invalid/v1" if enabled else None,
            provider_model="model" if enabled else None,
            provider_api_key_env="KEY" if enabled else None,
        )
        self.calls: list[tuple[str, str]] = []

    def verify_current_audit(self, task_id: str):
        self.calls.append(("verify", task_id))
        return {"task_id": task_id, "verified": True, "status": "VERIFIED"}

    def replay_task(self, task_id: str):
        self.calls.append(("replay", task_id))
        return {
            "task_id": task_id,
            "verified": True,
            "derived_stage": "PREVIEWED",
            "derived_outcome": "WORKING",
        }

    def audit_bundle(self, task_id: str):
        self.calls.append(("audit", task_id))
        return {"task_id": task_id, "audit_sha256": "a" * 64}

    def recent_tasks(self):
        return []


def _app(*, remote: bool = True, token: str = "r" * 32) -> App7OperatorConsoleApplication:
    digest = hashlib.sha256(token.encode("utf-8")).hexdigest() if remote else None
    return App7OperatorConsoleApplication(
        OperatorConsoleService(music_tools=SimpleNamespace()),
        FakeTaskService(),
        session_token="local-session",
        remote_read_only=remote,
        remote_auth_digest=digest,
    )


def _auth(token: str = "r" * 32) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def _body(payload: dict) -> bytes:
    return json.dumps(payload).encode("utf-8")


def test_remote_root_and_mode_discovery_are_public_but_data_requires_auth() -> None:
    app = _app()

    root = app.dispatch("GET", "/")
    mode = app.dispatch("GET", "/api/remote-mode")
    denied = app.dispatch("GET", "/api/session")
    allowed = app.dispatch("GET", "/api/session", headers=_auth())

    assert root.status == 200
    assert "APP7 Audit Replay Console" in root.body.decode("utf-8")
    assert mode.status == 200
    assert json.loads(mode.body)["remote_read_only"] is True
    assert denied.status == 401
    assert allowed.status == 200
    payload = json.loads(allowed.body)
    assert payload["writes_enabled"] is False
    assert payload["session_token"] == ""
    assert payload["merge_enabled"] is False


def test_remote_auth_rejects_wrong_or_short_tokens() -> None:
    app = _app()

    wrong = app.dispatch("GET", "/api/session", headers=_auth("x" * 32))
    short = app.dispatch("GET", "/api/session", headers=_auth("too-short"))

    assert wrong.status == 401
    assert short.status == 401


def test_remote_mode_blocks_all_post_mutations_even_with_valid_bearer() -> None:
    app = _app()

    response = app.dispatch(
        "POST",
        "/api/tasks/preview",
        body=_body({"project": "score_restore", "instruction": "change code"}),
        headers=_auth(),
    )
    merge = app.dispatch(
        "POST",
        "/api/tasks/merge",
        body=_body({"task_id": "task:" + "a" * 64}),
        headers=_auth(),
    )

    assert response.status == 405
    assert json.loads(response.body)["error"] == "remote_read_only"
    assert merge.status == 405


def test_remote_audit_verify_and_replay_remain_read_only_gets() -> None:
    app = _app()
    task_id = "task:" + "a" * 64

    verify = app.dispatch("GET", f"/api/tasks/audit-verify/{task_id}", headers=_auth())
    replay = app.dispatch("GET", f"/api/tasks/replay/{task_id}", headers=_auth())

    assert verify.status == 200
    assert replay.status == 200
    assert json.loads(verify.body)["verified"] is True
    assert json.loads(replay.body)["derived_stage"] == "PREVIEWED"


def test_local_mode_does_not_require_remote_bearer() -> None:
    app = _app(remote=False)

    session = app.dispatch("GET", "/api/session")

    assert session.status == 200
    assert json.loads(session.body)["session_token"] == "local-session"


class _DummyServer:
    def __init__(self, address, handler) -> None:
        self.address = address
        self.handler = handler
        self.served = False
        self.closed = False

    def serve_forever(self) -> None:
        self.served = True

    def server_close(self) -> None:
        self.closed = True


def test_non_loopback_requires_remote_mode_and_secure_transport_attestation(monkeypatch) -> None:
    monkeypatch.setattr(app7web, "ThreadingHTTPServer", _DummyServer)
    monkeypatch.setenv("REMOTE_TOKEN", "t" * 32)
    config = TaskExecutionConfig(enabled=False)

    with pytest.raises(ValueError, match="authenticated remote read-only"):
        app7web.serve_operator_console(host="0.0.0.0", task_config=config)
    with pytest.raises(ValueError, match="secure-transport attestation"):
        app7web.serve_operator_console(
            host="0.0.0.0",
            task_config=config,
            remote_read_only=True,
            remote_auth_token_env="REMOTE_TOKEN",
        )

    app7web.serve_operator_console(
        host="0.0.0.0",
        task_config=config,
        remote_read_only=True,
        remote_auth_token_env="REMOTE_TOKEN",
        remote_secure_transport_attested=True,
    )


def test_remote_mode_rejects_enabled_task_writes(monkeypatch) -> None:
    monkeypatch.setenv("REMOTE_TOKEN", "t" * 32)
    config = TaskExecutionConfig(
        enabled=True,
        provider_base_url="https://provider.invalid/v1",
        provider_model="model",
        provider_api_key_env="KEY",
    )

    with pytest.raises(ValueError, match="read-only"):
        app7web.serve_operator_console(
            task_config=config,
            remote_read_only=True,
            remote_auth_token_env="REMOTE_TOKEN",
        )
