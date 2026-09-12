from __future__ import annotations

import json
from types import SimpleNamespace

from st_music_agent.app5_web_app import App5OperatorConsoleApplication
from st_music_agent.operator_console import OperatorConsoleService
from st_music_agent.task_execution import TaskExecutionConfig


class FakeTaskService:
    def __init__(self) -> None:
        self.config = TaskExecutionConfig(
            enabled=True,
            provider_base_url="https://provider.invalid/v1",
            provider_model="model",
            provider_api_key_env="KEY",
        )
        self.calls: list[str] = []

    def refresh_pr_collaboration(self, task_id: str):
        self.calls.append(task_id)
        return {
            "task_id": task_id,
            "pr_collaboration": {
                "exact_head_approvals": ["reviewer"],
                "merge_authorized": False,
            },
        }

    def recent_tasks(self):
        return []


def _app(service: FakeTaskService) -> App5OperatorConsoleApplication:
    return App5OperatorConsoleApplication(
        OperatorConsoleService(music_tools=SimpleNamespace()),
        service,
        session_token="session-5",
    )


def _body(payload: dict) -> bytes:
    return json.dumps(payload).encode("utf-8")


def test_app5_root_exposes_project_validation_and_collaboration_ui() -> None:
    app = _app(FakeTaskService())

    response = app.dispatch("GET", "/")
    html = response.body.decode("utf-8")

    assert response.status == 200
    assert "APP5 Validation & Review Console" in html
    assert "PR review / thread yenile" in html
    assert "Merge / Production" in html


def test_pr_collaboration_refresh_requires_session() -> None:
    service = FakeTaskService()
    app = _app(service)
    task_id = "task:" + "a" * 64

    denied = app.dispatch(
        "POST",
        "/api/tasks/refresh-pr-collaboration",
        body=_body({"task_id": task_id}),
        headers={},
    )
    allowed = app.dispatch(
        "POST",
        "/api/tasks/refresh-pr-collaboration",
        body=_body({"task_id": task_id}),
        headers={"X-ST-Session": "session-5"},
    )

    assert denied.status == 403
    assert allowed.status == 200
    assert service.calls == [task_id]


def test_app5_still_has_no_merge_route() -> None:
    service = FakeTaskService()
    app = _app(service)

    response = app.dispatch(
        "POST",
        "/api/tasks/merge",
        body=_body({"task_id": "task:" + "a" * 64}),
        headers={"X-ST-Session": "session-5"},
    )

    assert response.status == 405
    assert service.calls == []
