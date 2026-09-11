from __future__ import annotations

from st_music_agent.app3_task_execution import App3TaskService
from st_music_agent.task_state import ProjectExecutionProfile


HEAD = "b" * 40
PROFILE = ProjectExecutionProfile(project="score_restore")


def _run(
    run_id: int,
    *,
    status: str = "completed",
    conclusion: str | None = "success",
    name: str = "core-ci",
) -> dict[str, object]:
    return {
        "id": run_id,
        "name": name,
        "status": status,
        "conclusion": conclusion,
        "head_sha": HEAD,
    }


def test_incomplete_ci_stays_pending() -> None:
    snapshot = App3TaskService._ci_snapshot(
        HEAD,
        [_run(2, status="in_progress", conclusion=None)],
        PROFILE,
        None,
    )

    assert snapshot["state"] == "pending"


def test_failed_ci_cannot_be_success() -> None:
    snapshot = App3TaskService._ci_snapshot(
        HEAD,
        [_run(2, conclusion="failure")],
        PROFILE,
        None,
    )

    assert snapshot["state"] == "failed"


def test_newest_rerun_for_same_workflow_replaces_old_failed_run() -> None:
    snapshot = App3TaskService._ci_snapshot(
        HEAD,
        [
            _run(3, conclusion="success"),
            _run(2, conclusion="failure"),
        ],
        PROFILE,
        None,
    )

    assert snapshot["state"] == "success"
    assert [item["id"] for item in snapshot["runs"]] == [3]


def test_required_workflow_missing_stays_pending() -> None:
    profile = ProjectExecutionProfile(
        project="score_restore",
        required_workflows=("core-ci", "music-validator"),
    )
    snapshot = App3TaskService._ci_snapshot(
        HEAD,
        [_run(5, name="core-ci")],
        profile,
        None,
    )

    assert snapshot["state"] == "pending"
    assert "music-validator" in snapshot["message"]
