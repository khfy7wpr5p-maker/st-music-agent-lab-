from __future__ import annotations

import json

import pytest

from st_music_agent.app8_coordination import (
    CrossProjectCoordinator,
    CrossProjectPlan,
    ProjectCompletionReceipt,
    ProjectWorkItem,
)
from st_music_agent.app8_graph_state import (
    App8GraphStore,
    GraphStateError,
    coordination_graph_id,
    supervision_graph_id,
)
from st_music_agent.app8_supervision import (
    AgentRole,
    BudgetEnvelope,
    DependencyGraph,
    MutationClass,
    ObjectiveContract,
    SubtaskNode,
    SupervisorEvent,
    SupervisorEventType,
)
from st_music_agent.contracts import TaskKind
from st_music_agent.music_evidence import MusicProject

REPO = "khfy7wpr5p-maker/st-music-agent-lab-"
RESTORE_REPO = "khfy7wpr5p-maker/st-score-restore-engine"
TAB_REPO = "khfy7wpr5p-maker/musicxml-to-guitar-tab-engine"
RESTORE_SHA = "a" * 40
TAB_SHA = "b" * 40


def node_budget() -> BudgetEnvelope:
    return BudgetEnvelope(
        max_elapsed_seconds=60,
        max_model_turns=2,
        max_tool_calls=2,
        max_model_facing_bytes=100_000,
    )


def supervision_graph() -> DependencyGraph:
    objective = ObjectiveContract(
        objective_id="app8e-demo",
        instruction="Inspect one exact repository state.",
        repositories=(REPO,),
        allowed_change_classes=(MutationClass.READ_ONLY,),
        success_evidence=("evidence_report",),
        max_agent_count=1,
        total_budget=BudgetEnvelope(
            max_elapsed_seconds=600,
            max_model_turns=10,
            max_tool_calls=10,
            max_model_facing_bytes=1_000_000,
        ),
        human_gates=("merge",),
        stop_conditions=("budget_exhausted",),
    )
    node = SubtaskNode(
        node_id="01-evidence",
        parent_objective_id=objective.objective_id,
        role=AgentRole.EVIDENCE,
        instruction="Inspect exact repository evidence.",
        dependencies=(),
        repository=REPO,
        branch_scope="main",
        input_evidence_refs=(),
        expected_output_evidence=("evidence_report",),
        budget=node_budget(),
        mutation_class=MutationClass.READ_ONLY,
        completion_criteria=("evidence present",),
        abstention_criteria=("evidence unavailable",),
        task_kind=TaskKind.RESEARCH,
        needs_tools=True,
    )
    return DependencyGraph(objective=objective, nodes=(node,))


def supervision_events() -> tuple[SupervisorEvent, ...]:
    return (
        SupervisorEvent(
            sequence=1,
            event_type=SupervisorEventType.NODE_SCHEDULED,
            node_id="01-evidence",
            model_name="Qwen3-Coder",
            model_provider="qwen",
            reserved_budget=node_budget(),
        ),
        SupervisorEvent(
            sequence=2,
            event_type=SupervisorEventType.NODE_COMPLETED,
            node_id="01-evidence",
            evidence_refs=("evidence_report",),
        ),
    )


def coordination_plan() -> CrossProjectPlan:
    return CrossProjectPlan(
        plan_id="app8e-cross-project",
        items=(
            ProjectWorkItem(
                item_id="01-restore",
                project=MusicProject.SCORE_RESTORE,
                repository=RESTORE_REPO,
                expected_base_sha=RESTORE_SHA,
                instruction="Read exact restore evidence.",
                dependencies=(),
                required_upstream_evidence=(),
                produces_evidence=("restored_score",),
                mutation_class=MutationClass.READ_ONLY,
            ),
            ProjectWorkItem(
                item_id="02-tab",
                project=MusicProject.MUSICXML_GUITAR_TAB,
                repository=TAB_REPO,
                expected_base_sha=TAB_SHA,
                instruction="Read exact TAB evidence.",
                dependencies=("01-restore",),
                required_upstream_evidence=("restored_score",),
                produces_evidence=("tab_report",),
                mutation_class=MutationClass.READ_ONLY,
            ),
        ),
    )


def read_only_receipt(item: ProjectWorkItem, digit: str) -> ProjectCompletionReceipt:
    return ProjectCompletionReceipt.from_host_verified_read_only(
        item,
        exact_sha=item.expected_base_sha,
        artifact_sha256=digit * 64,
        verification_sha256=("f" if digit != "f" else "e") * 64,
        produced_evidence=item.produces_evidence,
    )


def completed_coordination():
    plan = coordination_plan()
    coordinator = CrossProjectCoordinator(plan)
    first = coordinator.schedule_next()
    assert first is not None
    coordinator.record_receipt(read_only_receipt(plan.item(first.item_id), "1"))
    second = coordinator.schedule_next()
    assert second is not None
    coordinator.record_receipt(read_only_receipt(plan.item(second.item_id), "2"))
    return plan, coordinator.events


def test_supervision_graph_survives_restart_with_same_replay(tmp_path) -> None:
    path = tmp_path / "graphs.jsonl"
    graph = supervision_graph()
    events = supervision_events()
    store = App8GraphStore(path)

    graph_id = store.capture_supervision(graph, events)
    before = store.graph_view(graph_id)
    before_verify = store.verify_graph(graph_id)

    restarted = App8GraphStore(path)
    after = restarted.graph_view(graph_id)
    after_verify = restarted.verify_graph(graph_id)

    assert graph_id == supervision_graph_id(graph)
    assert before["replay"]["disposition"] == "complete"
    assert after["replay"] == before["replay"]
    assert after["anchor_hash"] == before["anchor_hash"]
    assert after_verify["verification_sha256"] == before_verify["verification_sha256"]
    assert after_verify["status"] == "VERIFIED"
    assert after_verify["execution_authorized"] is False
    assert after_verify["merge_authorized"] is False


def test_coordination_graph_survives_restart_with_same_replay(tmp_path) -> None:
    path = tmp_path / "graphs.jsonl"
    plan, events = completed_coordination()
    store = App8GraphStore(path)

    graph_id = store.capture_coordination(plan, events)
    before = store.graph_view(graph_id)
    restarted = App8GraphStore(path)
    after = restarted.graph_view(graph_id)

    assert graph_id == coordination_graph_id(plan)
    assert before["replay"]["disposition"] == "complete"
    assert after["replay"] == before["replay"]
    assert restarted.graph_summary(graph_id).resume_available is False


def test_capture_is_idempotent_and_rejects_divergent_history(tmp_path) -> None:
    path = tmp_path / "graphs.jsonl"
    graph = supervision_graph()
    events = supervision_events()
    store = App8GraphStore(path)

    graph_id = store.capture_supervision(graph, events)
    record_count = len(store._records)
    assert store.capture_supervision(graph, events) == graph_id
    assert len(store._records) == record_count

    divergent = (
        events[0],
        SupervisorEvent(
            sequence=2,
            event_type=SupervisorEventType.NODE_FAILED,
            node_id="01-evidence",
            evidence_refs=("validator:failed",),
        ),
    )
    with pytest.raises(GraphStateError, match="diverges"):
        store.capture_supervision(graph, divergent)


def test_hash_chain_tampering_is_rejected_on_restart(tmp_path) -> None:
    path = tmp_path / "graphs.jsonl"
    store = App8GraphStore(path)
    store.capture_supervision(supervision_graph(), supervision_events())

    lines = path.read_text(encoding="utf-8").splitlines()
    record = json.loads(lines[-1])
    record["payload"]["node_id"] = "tampered"
    lines[-1] = json.dumps(record, sort_keys=True, separators=(",", ":"))
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")

    with pytest.raises(GraphStateError, match="hash does not match"):
        App8GraphStore(path)


def test_event_sequence_must_be_contiguous(tmp_path) -> None:
    store = App8GraphStore(tmp_path / "graphs.jsonl")
    graph = supervision_graph()
    graph_id = store.register_supervision(graph)
    wrong = SupervisorEvent(
        sequence=2,
        event_type=SupervisorEventType.NODE_SCHEDULED,
        node_id="01-evidence",
        model_name="Qwen3-Coder",
        model_provider="qwen",
        reserved_budget=node_budget(),
    )

    with pytest.raises(GraphStateError, match="contiguous"):
        store.append_supervision_event(graph_id, wrong)


def test_recent_graphs_and_views_never_authorize_mutations(tmp_path) -> None:
    store = App8GraphStore(tmp_path / "graphs.jsonl")
    graph = supervision_graph()
    graph_id = store.capture_supervision(graph, supervision_events())

    summary = store.recent_graphs()[0]
    view = store.graph_view(graph_id)

    for payload in (summary, view):
        assert payload["execution_authorized"] is False
        assert payload["repository_mutation_authorized"] is False
        assert payload["pr_open_authorized"] is False
        assert payload["merge_authorized"] is False
        assert payload["production_actions_authorized"] is False
