from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from st_music_agent.app5_task_execution import App5TaskService
from st_music_agent.app6_task_execution import (
    App6GitHubReadClient,
    App6TaskService,
    _effective_health,
)
from st_music_agent.github_read import GitHubReadConfig
from st_music_agent.task_execution import TaskExecutionConfig, TaskExecutionError
from st_music_agent.task_state import TaskEventStore, TaskStage
from st_music_agent.transport import JsonResponse


class GraphQLTransport:
    def request(self, request):
        assert request.url == "https://api.github.com/graphql"
        return JsonResponse(
            status_code=200,
            payload={
                "data": {
                    "repository": {
                        "pullRequest": {
                            "reviewThreads": {
                                "nodes": [
                                    {
                                        "id": "PRRT_test",
                                        "isResolved": True,
                                        "isOutdated": False,
                                        "path": "src/example.py",
                                        "line": 12,
                                        "comments": {
                                            "totalCount": 1,
                                            "nodes": [
                                                {
                                                    "databaseId": 91,
                                                    "commit": {"oid": "b" * 40},
                                                }
                                            ],
                                        },
                                    }
                                ],
                                "pageInfo": {"hasNextPage": False},
                            }
                        }
                    }
                }
            },
        )


def test_effective_health_distinguishes_fresh_and_stale() -> None:
    now = datetime(2026, 9, 12, 8, 0, tzinfo=UTC)
    value = {
        "state": "HEALTHY",
        "expires_at": (now + timedelta(minutes=5)).isoformat(),
    }

    fresh = _effective_health(value, now=now)
    stale = _effective_health(value, now=now + timedelta(minutes=6))

    assert fresh["effective_state"] == "FRESH_HEALTHY"
    assert fresh["refresh_required"] is False
    assert stale["effective_state"] == "STALE_HEALTHY"
    assert stale["refresh_required"] is True


def test_pr_open_requires_fresh_healthy_validation(tmp_path, monkeypatch) -> None:
    service = App6TaskService(TaskExecutionConfig(enabled=False), state_path=tmp_path / "tasks.jsonl")
    monkeypatch.setattr(
        App5TaskService,
        "open_pull_request",
        lambda self, task_id: {"number": 7, "task_id": task_id},
    )
    monkeypatch.setattr(
        service,
        "status",
        lambda task_id: {"validator_health": {"effective_state": "STALE_HEALTHY"}},
    )

    with pytest.raises(TaskExecutionError, match="fresh healthy APP6 validator evidence"):
        service.open_pull_request("task:" + "a" * 64)

    monkeypatch.setattr(
        service,
        "status",
        lambda task_id: {"validator_health": {"effective_state": "FRESH_HEALTHY"}},
    )
    assert service.open_pull_request("task:" + "a" * 64)["number"] == 7


def test_graphql_review_resolution_uses_explicit_is_resolved() -> None:
    client = App6GitHubReadClient(
        GitHubReadConfig(repository="owner/repo"),
        transport=GraphQLTransport(),
    )

    result = client._graphql_review_threads(4)

    assert result["complete"] is True
    assert result["threads"][0]["root_comment_id"] == 91
    assert result["threads"][0]["is_resolved"] is True
    assert result["threads"][0]["is_outdated"] is False


def test_validator_health_is_restored_from_hash_chained_journal(tmp_path) -> None:
    store = TaskEventStore(tmp_path / "events.jsonl")
    task_id = "task:" + "a" * 64
    store.append_stage(task_id, TaskStage.PREVIEWED, {"project": "score_restore"})
    store.append_evidence(
        task_id,
        "VALIDATOR_HEALTH_SNAPSHOT",
        {
            "state": "HEALTHY",
            "checked_at": "2026-09-12T08:00:00+00:00",
            "expires_at": "2026-09-12T08:15:00+00:00",
        },
    )

    view = TaskEventStore(tmp_path / "events.jsonl").task_view(task_id)

    assert view["validator_health"]["state"] == "HEALTHY"


def test_audit_bundle_exports_anchor_without_merge_authority(tmp_path) -> None:
    store = TaskEventStore(tmp_path / "events.jsonl")
    task_id = "task:" + "a" * 64
    store.append_stage(
        task_id,
        TaskStage.PREVIEWED,
        {
            "project": "score_restore",
            "repository": "owner/repo",
            "base_branch": "main",
            "base_sha": "a" * 40,
            "feature_branch": "st-agent/test/task",
            "instruction_fingerprint": "f" * 64,
        },
    )
    store.append_evidence(
        task_id,
        "PR_COLLABORATION_SNAPSHOT",
        {
            "thread_count": 1,
            "resolution_state_available": True,
            "conversation": [{"body_sha256": "d" * 64, "body_chars": 999}],
            "merge_authorized": False,
        },
    )
    service = App6TaskService(
        TaskExecutionConfig(enabled=False),
        store=store,
        read_factory=lambda repository: object(),
    )

    bundle = service.audit_bundle(task_id)

    assert bundle["merge_authorized"] is False
    assert bundle["production_actions_authorized"] is False
    assert bundle["journal"]["anchor_hash"] == store.task_events(task_id)[-1]["hash"]
    assert len(bundle["audit_sha256"]) == 64
    assert "conversation" not in bundle["pr_collaboration"]
