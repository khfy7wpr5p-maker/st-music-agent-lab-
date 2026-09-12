from __future__ import annotations

import json
from types import SimpleNamespace

from st_music_agent.app6_web_app import App6OperatorConsoleApplication
from st_music_agent.operator_console import OperatorConsoleService
from st_music_agent.task_execution import TaskExecutionConfig


class FakeTaskService:
    def __init__(self) -> None:
        self.config = TaskExecutionConfig(enabled=False)
        self.calls: list[str] = []

    def audit_bundle(self, task_id: str):
        self.calls.append(task_id)
        return {
            "task_id": task_id,
            "audit_sha256": "a" * 64,
            "merge_authorized": False,
            "production_actions_authorized": False,
        }

    def recent_tasks(self):
        return []


def _app(service: FakeTaskService) -> App6OperatorConsoleApplication:
    return App6OperatorConsoleApplication(
        OperatorConsoleService(music_tools=SimpleNamespace()),
        service,
        session_token="session-6",
    )


def _body(payload: dict) -> bytes:
    return json.dumps(payload).encode("utf-8")


def test_app6_root_exposes_health_and_audit_ui() -> None:
    response = _app(FakeTaskService()).dispatch("GET", "/")
    html = response.body.decode("utf-8")

    assert response.status == 200
    assert "APP6 Health & Audit Console" in html
    assert "Audit JSON" in html
    assert "Validator health" in html


def test_audit_export_is_read_only_and_bounded_to_task_id() -> None:
    service = FakeTaskService()
    task_id = "task:" + "a" * 64
    app = _app(service)

    response = app.dispatch("GET", f"/api/tasks/audit/{task_id}")
    invalid = app.dispatch("GET", "/api/tasks/audit/bad/path")

    assert response.status == 200
    assert json.loads(response.body)["merge_authorized"] is False
    assert invalid.status == 404
    assert service.calls == [task_id]


def test_app6_still_has_no_merge_route() -> None:
    service = FakeTaskService()
    app = _app(service)

    response = app.dispatch(
        "POST",
        "/api/tasks/merge",
        body=_body({"task_id": "task:" + "a" * 64}),
        headers={"X-ST-Session": "session-6"},
    )

    assert response.status == 405
    assert service.calls == []
