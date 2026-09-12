from __future__ import annotations

from st_music_agent import app5_task_execution as app5
from st_music_agent.app5_task_execution import App5TaskService
from st_music_agent.github_read import GitHubReadError
from st_music_agent.music_evidence import (
    EvidenceAuthority,
    EvidenceSource,
    MusicEvidenceSnapshot,
    MusicProject,
)
from st_music_agent.task_execution import TaskExecutionConfig
from st_music_agent.task_state import TaskEventStore, TaskStage, ValidatorStatus


def _service(tmp_path) -> App5TaskService:
    return App5TaskService(
        TaskExecutionConfig(enabled=False),
        state_path=tmp_path / "tasks.jsonl",
        read_factory=lambda repository: object(),
    )


def _score_restore_snapshot(ref: str, *, safe: bool = True) -> MusicEvidenceSnapshot:
    return MusicEvidenceSnapshot(
        project=MusicProject.SCORE_RESTORE,
        authority=EvidenceAuthority.REPOSITORY_CURRENT_TRUTH,
        state="TEST_CURRENT_TRUTH",
        summary="Bounded Score Restore test evidence.",
        claims={
            "automatic_production_promotion_forbidden": safe,
            "omr_correctness_implied": False,
            "musical_truth_implied": False,
        },
        sources=(
            EvidenceSource(
                repository="khfy7wpr5p-maker/st-score-restore-engine",
                ref=ref,
                path="docs/live/current.json",
                blob_sha="c" * 40,
            ),
        ),
    )


def test_project_validator_passes_only_exact_head_safe_contract(tmp_path, monkeypatch) -> None:
    head = "b" * 40
    service = _service(tmp_path)
    monkeypatch.setattr(
        app5,
        "_collect_project_snapshot",
        lambda project, read_client, commit: _score_restore_snapshot(commit),
    )

    result = service._project_validator(
        "score_restore",
        head,
        {"project": "score_restore", "repository": "owner/repo"},
    )

    assert result.status is ValidatorStatus.PASS
    assert result.commit_sha == head
    assert result.name == "score_restore_current_truth"


def test_project_validator_fails_stale_or_unsafe_evidence(tmp_path, monkeypatch) -> None:
    head = "b" * 40
    service = _service(tmp_path)
    monkeypatch.setattr(
        app5,
        "_collect_project_snapshot",
        lambda project, read_client, commit: _score_restore_snapshot("a" * 40, safe=False),
    )

    result = service._project_validator(
        "score_restore",
        head,
        {"project": "score_restore", "repository": "owner/repo"},
    )

    assert result.status is ValidatorStatus.FAIL
    assert "exact task HEAD" in result.message or "must remain" in result.message


def test_project_validator_keeps_unavailable_distinct_from_pass(tmp_path, monkeypatch) -> None:
    service = _service(tmp_path)

    def unavailable(project, read_client, commit):
        raise GitHubReadError("temporary read failure")

    monkeypatch.setattr(app5, "_collect_project_snapshot", unavailable)
    result = service._project_validator(
        "score_editor",
        "d" * 40,
        {"project": "score_editor", "repository": "owner/repo"},
    )

    assert result.status is ValidatorStatus.UNAVAILABLE
    assert "unavailable" in result.message


def test_collaboration_snapshot_separates_exact_and_stale_reviews() -> None:
    head = "b" * 40
    evidence = {
        "reviews": [
            {
                "reviewer": "alice",
                "state": "APPROVED",
                "commit_id": head,
                "submitted_at": "2026-09-12T06:00:00Z",
            },
            {
                "reviewer": "bob",
                "state": "CHANGES_REQUESTED",
                "commit_id": "a" * 40,
                "submitted_at": "2026-09-12T05:00:00Z",
            },
        ],
        "threads": [
            {"root_comment_id": 1, "commit_id": head, "comments": [], "comment_count": 1},
            {
                "root_comment_id": 2,
                "commit_id": "a" * 40,
                "comments": [],
                "comment_count": 1,
            },
        ],
        "conversation": [{"id": 3, "author": "alice", "body": "Looks good"}],
        "resolution_state_available": False,
    }

    snapshot = app5._collaboration_snapshot(41, head, evidence)

    assert snapshot["exact_head_approvals"] == ["alice"]
    assert snapshot["exact_head_changes_requested"] == []
    assert snapshot["stale_review_count"] == 1
    assert snapshot["thread_count"] == 2
    assert snapshot["exact_head_thread_count"] == 1
    assert snapshot["resolution_state_available"] is False
    assert snapshot["merge_authorized"] is False


def test_task_store_restores_pr_collaboration_snapshot(tmp_path) -> None:
    store = TaskEventStore(tmp_path / "events.jsonl")
    task_id = "task:" + "a" * 64
    store.append_stage(task_id, TaskStage.PREVIEWED, {"project": "score_restore"})
    store.append_evidence(
        task_id,
        "PR_COLLABORATION_SNAPSHOT",
        {"pull_request": 41, "task_head_sha": "b" * 40, "merge_authorized": False},
    )

    view = TaskEventStore(tmp_path / "events.jsonl").task_view(task_id)

    assert view["pr_collaboration"]["pull_request"] == 41
    assert view["pr_collaboration"]["merge_authorized"] is False
