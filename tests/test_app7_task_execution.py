from __future__ import annotations

from st_music_agent.app7_task_execution import App7TaskService, verify_audit_export
from st_music_agent.task_execution import TaskExecutionConfig
from st_music_agent.task_state import TaskEventStore, TaskOutcome, TaskStage


def _service(tmp_path) -> tuple[App7TaskService, str]:
    store = TaskEventStore(tmp_path / "tasks.jsonl")
    task_id = "task:" + "a" * 64
    store.append_stage(
        task_id,
        TaskStage.PREVIEWED,
        {
            "project": "score_restore",
            "repository": "owner/repo",
            "base_branch": "main",
            "base_sha": "b" * 40,
            "feature_branch": "st-agent/score_restore/test",
            "instruction_fingerprint": "c" * 64,
            "policy": {},
        },
    )
    service = App7TaskService(
        TaskExecutionConfig(enabled=False),
        store=store,
        read_factory=lambda repository: object(),
    )
    return service, task_id


def test_export_verifier_accepts_untampered_app6_audit(tmp_path) -> None:
    service, task_id = _service(tmp_path)

    audit = service.audit_bundle(task_id)
    result = verify_audit_export(audit)

    assert result["verified"] is True
    assert result["status"] == "STRUCTURE_VERIFIED"
    assert result["source_journal_authenticated"] is False
    assert result["supplied_audit_sha256"] == audit["audit_sha256"]


def test_export_verifier_detects_content_tampering(tmp_path) -> None:
    service, task_id = _service(tmp_path)
    audit = service.audit_bundle(task_id)
    audit["project"] = "tampered-project"

    result = verify_audit_export(audit)

    assert result["verified"] is False
    assert "audit_sha256 does not match audit content" in result["reasons"]


def test_local_verification_binds_export_to_journal_anchor_and_replay(tmp_path) -> None:
    service, task_id = _service(tmp_path)

    verification = service.verify_current_audit(task_id)

    assert verification["verified"] is True
    assert verification["status"] == "VERIFIED"
    assert verification["verification_scope"] == "local_hash_chained_journal_and_export"
    assert verification["replay"]["derived_stage"] == TaskStage.PREVIEWED.value
    assert verification["replay"]["derived_outcome"] == TaskOutcome.WORKING.value
    assert verification["merge_authorized"] is False
    assert verification["production_actions_authorized"] is False


def test_replay_is_deterministic_for_same_journal(tmp_path) -> None:
    service, task_id = _service(tmp_path)
    service.store.append_evidence(
        task_id,
        "OUTCOME",
        {"outcome": TaskOutcome.REVIEW_REQUIRED.value},
    )

    first = service.replay_task(task_id)
    second = service.replay_task(task_id)

    assert first["verified"] is True
    assert first["derived_outcome"] == TaskOutcome.REVIEW_REQUIRED.value
    assert first["replay_sha256"] == second["replay_sha256"]
    assert first["anchor_hash"] == second["anchor_hash"]


def test_export_verifier_rejects_authority_widening(tmp_path) -> None:
    service, task_id = _service(tmp_path)
    audit = service.audit_bundle(task_id)
    audit["merge_authorized"] = True

    result = verify_audit_export(audit)

    assert result["verified"] is False
    assert "audit must not authorize merge" in result["reasons"]
