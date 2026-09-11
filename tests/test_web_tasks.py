from __future__ import annotations

import json
from types import SimpleNamespace

from st_music_agent.operator_console import OperatorConsoleService
from st_music_agent.task_execution import TaskExecutionConfig
from st_music_agent.web_app import OperatorConsoleApplication


class FakeTaskValue:
    def __init__(self, payload):
        self.payload = payload

    def as_dict(self):
        return dict(self.payload)


class FakeTaskService:
    def __init__(self, enabled: bool) -> None:
        self.config = TaskExecutionConfig(
            enabled=enabled,
            provider_base_url="https://provider.invalid/v1" if enabled else None,
            provider_model="model" if enabled else None,
            provider_api_key_env="KEY" if enabled else None,
        )
        self.calls: list[tuple[str, str]] = []

    def preview(self, project: str, instruction: str):
        self.calls.append(("preview", project))
        return FakeTaskValue(
            {
                "task_id": "task:" + "a" * 64,
                "project": project,
                "instruction": instruction,
                "repository": "owner/repo",
                "base_branch": "main",
                "base_sha": "b" * 40,
                "feature_branch": "st-agent/test/aaaaaaaaaaaa",
                "policy": {
                    "create_branch": "auto_execute",
                    "write_file": "auto_execute",
                    "open_pull_request": "require_human",
                },
                "execution_enabled": self.config.enabled,
                "production_actions_authorized": False,
            }
        )

    def run(self, task_id: str):
        self.calls.append(("run", task_id))
        return FakeTaskValue(
            {
                "task_id": task_id,
                "head_sha": "c" * 40,
                "model_name": "GLM-5.1",
                "tool_calls": 2,
                "turns": 3,
                "final_message": {"role": "assistant", "content": "done"},
                "workflow_runs": [],
                "merge_authorized": False,
                "production_actions_authorized": False,
            }
        )

    def open_pull_request(self, task_id: str):
        self.calls.append(("open-pr", task_id))
        return {"number": 9, "state": "open", "html_url": "https://example.invalid/pr/9"}

    def status(self, task_id: str):
        return {"preview": {"task_id": task_id}, "run": None, "pull_request": None}


def _body(payload: dict) -> bytes:
    return json.dumps(payload).encode("utf-8")


def test_task_post_requires_exact_session_token() -> None:
    task_service = FakeTaskService(enabled=True)
    app = OperatorConsoleApplication(
        OperatorConsoleService(music_tools=SimpleNamespace()),
        task_service,
        session_token="session-123",
    )
    target = "/api/tasks/preview"
    payload = _body({"project": "score_restore", "instruction": "Update README"})

    missing = app.dispatch("POST", target, body=payload, headers={})
    wrong = app.dispatch("POST", target, body=payload, headers={"X-ST-Session": "wrong"})
    correct = app.dispatch(
        "POST",
        target,
        body=payload,
        headers={"X-ST-Session": "session-123"},
    )

    assert missing.status == 403
    assert wrong.status == 403
    assert correct.status == 200
    assert task_service.calls == [("preview", "score_restore")]


def test_preview_works_in_read_mode_but_run_stays_disabled() -> None:
    task_service = FakeTaskService(enabled=False)
    app = OperatorConsoleApplication(
        OperatorConsoleService(music_tools=SimpleNamespace()),
        task_service,
        session_token="session-123",
    )
    headers = {"X-ST-Session": "session-123"}
    preview = app.dispatch(
        "POST",
        "/api/tasks/preview",
        body=_body({"project": "score_editor", "instruction": "Inspect one issue"}),
        headers=headers,
    )
    run = app.dispatch(
        "POST",
        "/api/tasks/run",
        body=_body({"task_id": "task:" + "a" * 64}),
        headers=headers,
    )

    assert preview.status == 200
    assert run.status == 403
    assert task_service.calls == [("preview", "score_editor")]


def test_write_mode_exposes_run_and_human_pr_click_but_no_merge_route() -> None:
    task_service = FakeTaskService(enabled=True)
    app = OperatorConsoleApplication(
        OperatorConsoleService(music_tools=SimpleNamespace()),
        task_service,
        session_token="session-123",
    )
    headers = {"X-ST-Session": "session-123"}
    task_id = "task:" + "a" * 64

    run = app.dispatch(
        "POST",
        "/api/tasks/run",
        body=_body({"task_id": task_id}),
        headers=headers,
    )
    pr = app.dispatch(
        "POST",
        "/api/tasks/open-pr",
        body=_body({"task_id": task_id}),
        headers=headers,
    )
    merge = app.dispatch(
        "POST",
        "/api/tasks/merge",
        body=_body({"task_id": task_id}),
        headers=headers,
    )

    assert run.status == 200
    assert json.loads(run.body)["merge_authorized"] is False
    assert pr.status == 200
    assert json.loads(pr.body)["pull_request"]["number"] == 9
    assert merge.status == 405
    assert task_service.calls == [("run", task_id), ("open-pr", task_id)]


def test_session_and_capabilities_reflect_runtime_write_mode() -> None:
    task_service = FakeTaskService(enabled=True)
    service = OperatorConsoleService(music_tools=SimpleNamespace())
    app = OperatorConsoleApplication(service, task_service, session_token="session-123")

    session = json.loads(app.dispatch("GET", "/api/session").body)
    capabilities = json.loads(app.dispatch("GET", "/api/capabilities").body)

    assert session["writes_enabled"] is True
    assert session["merge_enabled"] is False
    assert session["production_actions_authorized"] is False
    assert capabilities["write"]["feature_branch_task_execution"] is True
    assert capabilities["write"]["protected_branch_mutation"] is False


def test_json_body_is_bounded_and_must_be_an_object() -> None:
    task_service = FakeTaskService(enabled=True)
    app = OperatorConsoleApplication(
        OperatorConsoleService(music_tools=SimpleNamespace()),
        task_service,
        session_token="session-123",
    )
    headers = {"X-ST-Session": "session-123"}

    array_body = app.dispatch(
        "POST",
        "/api/tasks/preview",
        body=b"[]",
        headers=headers,
    )
    huge = app.dispatch(
        "POST",
        "/api/tasks/preview",
        body=b"{" + b"x" * 40000 + b"}",
        headers=headers,
    )

    assert array_body.status == 400
    assert huge.status == 400
