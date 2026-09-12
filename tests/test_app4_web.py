from __future__ import annotations

import json
from types import SimpleNamespace

from st_music_agent.app4_web_app import App4OperatorConsoleApplication
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
        self.calls: list[tuple[str, str]] = []

    def review_bundle(self, task_id: str):
        self.calls.append(("review", task_id))
        return {
            "task_id": task_id,
            "base_sha": "a" * 40,
            "head_sha": "b" * 40,
            "complete": True,
            "review_digest": "c" * 64,
            "files": [],
        }

    def acknowledge_review(self, task_id: str, review_digest: str):
        self.calls.append(("ack", task_id))
        return {"task_id": task_id, "review_ready_for_pr": review_digest == "c" * 64}

    def create_revision(self, parent_task_id: str, instruction: str, *, mode: str):
        self.calls.append((mode, parent_task_id))
        return {
            "parent_task_id": parent_task_id,
            "mode": mode,
            "child": {"task_id": "task:" + "d" * 64, "instruction": instruction},
        }

    def refresh_pr_review(self, task_id: str):
        self.calls.append(("pr-review", task_id))
        return {"task_id": task_id, "pr_review": {"exact_head_match": True}}

    def recent_tasks(self):
        return []


def _body(payload: dict) -> bytes:
    return json.dumps(payload).encode("utf-8")


def _app(service: FakeTaskService) -> App4OperatorConsoleApplication:
    return App4OperatorConsoleApplication(
        OperatorConsoleService(music_tools=SimpleNamespace()),
        service,
        session_token="session-4",
    )


def test_review_get_is_read_only_but_ack_requires_session() -> None:
    service = FakeTaskService()
    app = _app(service)
    task_id = "task:" + "a" * 64

    review = app.dispatch("GET", f"/api/tasks/review/{task_id}")
    denied = app.dispatch(
        "POST",
        "/api/tasks/ack-review",
        body=_body({"task_id": task_id, "review_digest": "c" * 64}),
        headers={},
    )
    allowed = app.dispatch(
        "POST",
        "/api/tasks/ack-review",
        body=_body({"task_id": task_id, "review_digest": "c" * 64}),
        headers={"X-ST-Session": "session-4"},
    )

    assert review.status == 200
    assert denied.status == 403
    assert allowed.status == 200
    assert service.calls == [("review", task_id), ("ack", task_id)]


def test_revision_requires_session_and_preserves_explicit_mode() -> None:
    service = FakeTaskService()
    app = _app(service)
    task_id = "task:" + "a" * 64
    payload = {"parent_task_id": task_id, "instruction": "Correct README", "mode": "amend"}

    denied = app.dispatch("POST", "/api/tasks/revision", body=_body(payload), headers={})
    allowed = app.dispatch(
        "POST",
        "/api/tasks/revision",
        body=_body(payload),
        headers={"X-ST-Session": "session-4"},
    )

    assert denied.status == 403
    assert allowed.status == 200
    assert json.loads(allowed.body)["mode"] == "amend"
    assert service.calls == [("amend", task_id)]


def test_app4_still_has_no_merge_route() -> None:
    service = FakeTaskService()
    app = _app(service)
    task_id = "task:" + "a" * 64

    response = app.dispatch(
        "POST",
        "/api/tasks/merge",
        body=_body({"task_id": task_id}),
        headers={"X-ST-Session": "session-4"},
    )

    assert response.status == 405
    assert service.calls == []
