import pytest

from st_music_agent.app8_supervision import (
    AgentRole,
    BudgetEnvelope,
    DependencyGraph,
    MutationClass,
    NodeOutcome,
    NodeState,
    ObjectiveContract,
    SubtaskNode,
    SupervisorBudgetError,
    SupervisorDisposition,
    SupervisorEvent,
    SupervisorEventType,
    SupervisorGraphError,
    SupervisorSimulator,
    SupervisorStateError,
    replay_supervision,
)
from st_music_agent.catalog import DEFAULT_MODELS
from st_music_agent.contracts import TaskKind
from st_music_agent.router import ModelRouter

REPO = "khfy7wpr5p-maker/st-music-agent-lab-"


def budget(turns: int = 2, tools: int = 4, seconds: float = 60.0) -> BudgetEnvelope:
    return BudgetEnvelope(
        max_elapsed_seconds=seconds,
        max_model_turns=turns,
        max_tool_calls=tools,
        max_model_facing_bytes=100_000,
    )


def objective(*, total_turns: int = 20, classes=None) -> ObjectiveContract:
    if classes is None:
        classes = (
            MutationClass.READ_ONLY,
            MutationClass.REVERSIBLE_FEATURE_BRANCH,
            MutationClass.HUMAN_GATED,
        )
    return ObjectiveContract(
        objective_id="app8a-demo",
        instruction="Simulate a bounded multi-agent engineering objective.",
        repositories=(REPO,),
        allowed_change_classes=classes,
        success_evidence=("critic_report",),
        max_agent_count=4,
        total_budget=BudgetEnvelope(
            max_elapsed_seconds=600.0,
            max_model_turns=total_turns,
            max_tool_calls=40,
            max_model_facing_bytes=1_000_000,
        ),
        human_gates=("merge",),
        stop_conditions=("budget_exhausted", "invariant_failed"),
    )


def node(
    node_id: str,
    role: AgentRole,
    *,
    dependencies=(),
    inputs=(),
    outputs=("evidence",),
    mutation=MutationClass.READ_ONLY,
    branch="main",
    kind=TaskKind.GENERAL,
    minimum_context_tokens=0,
    node_budget=None,
) -> SubtaskNode:
    return SubtaskNode(
        node_id=node_id,
        parent_objective_id="app8a-demo",
        role=role,
        instruction=f"Perform bounded {role.value} work for {node_id}.",
        dependencies=tuple(dependencies),
        repository=REPO,
        branch_scope=branch,
        input_evidence_refs=tuple(inputs),
        expected_output_evidence=tuple(outputs),
        budget=node_budget or budget(),
        mutation_class=mutation,
        completion_criteria=("expected evidence is present",),
        abstention_criteria=("required evidence is unavailable",),
        task_kind=kind,
        minimum_context_tokens=minimum_context_tokens,
    )


def full_graph(*, total_turns: int = 20) -> DependencyGraph:
    return DependencyGraph(
        objective=objective(total_turns=total_turns),
        nodes=(
            node(
                "01-evidence",
                AgentRole.EVIDENCE,
                outputs=("repo_snapshot",),
                kind=TaskKind.RESEARCH,
                minimum_context_tokens=220_000,
            ),
            node(
                "02-implementation",
                AgentRole.IMPLEMENTATION,
                dependencies=("01-evidence",),
                inputs=("repo_snapshot",),
                outputs=("candidate_patch",),
                mutation=MutationClass.REVERSIBLE_FEATURE_BRANCH,
                branch="feature/app8a-demo",
                kind=TaskKind.CODE,
            ),
            node(
                "03-validation",
                AgentRole.VALIDATION,
                dependencies=("02-implementation",),
                inputs=("candidate_patch",),
                outputs=("validator_report",),
                kind=TaskKind.CODE,
            ),
            node(
                "04-critic",
                AgentRole.CRITIC,
                dependencies=("03-validation",),
                inputs=("validator_report",),
                outputs=("critic_report",),
                kind=TaskKind.PLANNING,
            ),
        ),
    )


def test_objective_is_canonical_and_keeps_production_authority_false() -> None:
    first = objective()
    second = objective()

    assert first.objective_fingerprint == second.objective_fingerprint
    assert "merge" in first.forbidden_actions
    assert "deployment" in first.forbidden_actions
    payload = first.as_dict()
    assert payload["execution_authorized"] is False
    assert payload["merge_authorized"] is False
    assert payload["production_actions_authorized"] is False


def test_graph_rejects_unknown_dependencies_and_cycles() -> None:
    with pytest.raises(SupervisorGraphError, match="unknown dependencies"):
        DependencyGraph(
            objective=objective(),
            nodes=(
                node(
                    "a",
                    AgentRole.EVIDENCE,
                    dependencies=("missing",),
                    inputs=("missing_output",),
                ),
            ),
        )

    with pytest.raises(SupervisorGraphError, match="dependency cycle"):
        DependencyGraph(
            objective=objective(),
            nodes=(
                node(
                    "a",
                    AgentRole.EVIDENCE,
                    dependencies=("b",),
                    inputs=("b_output",),
                    outputs=("a_output",),
                ),
                node(
                    "b",
                    AgentRole.CRITIC,
                    dependencies=("a",),
                    inputs=("a_output",),
                    outputs=("b_output",),
                    kind=TaskKind.PLANNING,
                ),
            ),
        )


def test_graph_requires_explicit_dependency_evidence_flow() -> None:
    with pytest.raises(SupervisorGraphError, match="does not declare dependency evidence"):
        DependencyGraph(
            objective=objective(),
            nodes=(
                node("a", AgentRole.EVIDENCE, outputs=("snapshot",)),
                node(
                    "b",
                    AgentRole.CRITIC,
                    dependencies=("a",),
                    inputs=("wrong_ref",),
                    kind=TaskKind.PLANNING,
                ),
            ),
        )


def test_role_policy_and_protected_branch_write_fail_closed() -> None:
    with pytest.raises(SupervisorGraphError, match="not allowed for its role"):
        DependencyGraph(
            objective=objective(),
            nodes=(
                node(
                    "evidence",
                    AgentRole.EVIDENCE,
                    mutation=MutationClass.REVERSIBLE_FEATURE_BRANCH,
                    branch="feature/evidence",
                    kind=TaskKind.RESEARCH,
                ),
            ),
        )

    with pytest.raises(SupervisorGraphError, match="protected branch"):
        DependencyGraph(
            objective=objective(),
            nodes=(
                node(
                    "implementation",
                    AgentRole.IMPLEMENTATION,
                    mutation=MutationClass.REVERSIBLE_FEATURE_BRANCH,
                    branch="main",
                    kind=TaskKind.CODE,
                ),
            ),
        )


def test_scheduler_is_dependency_ordered_model_routed_and_simulation_only() -> None:
    graph = full_graph()
    simulator = SupervisorSimulator(graph, ModelRouter(DEFAULT_MODELS))

    initial = simulator.replay()
    assert initial.state_for("01-evidence").state is NodeState.READY
    assert initial.state_for("02-implementation").state is NodeState.PENDING

    evidence_decision = simulator.schedule_next()
    assert evidence_decision is not None
    assert evidence_decision.node_id == "01-evidence"
    assert evidence_decision.model_name == "Qwen3.8"
    assert evidence_decision.simulation_only is True
    assert evidence_decision.execution_authorized is False
    assert evidence_decision.repository_mutation_authorized is False
    assert evidence_decision.merge_authorized is False

    simulator.record_result(
        "01-evidence",
        NodeOutcome.PASS,
        evidence_refs=("repo_snapshot",),
    )
    implementation_decision = simulator.schedule_next()
    assert implementation_decision is not None
    assert implementation_decision.node_id == "02-implementation"
    assert implementation_decision.model_name == "GLM-5.1"
    assert implementation_decision.mutation_class is MutationClass.REVERSIBLE_FEATURE_BRANCH
    assert implementation_decision.repository_mutation_authorized is False


def test_pass_requires_expected_evidence_and_unlocks_only_after_pass() -> None:
    graph = full_graph()
    simulator = SupervisorSimulator(graph, ModelRouter(DEFAULT_MODELS))
    simulator.schedule_next()

    with pytest.raises(SupervisorStateError, match="missing expected evidence"):
        simulator.record_result("01-evidence", NodeOutcome.PASS, evidence_refs=("wrong",))

    replay = simulator.record_result(
        "01-evidence",
        NodeOutcome.PASS,
        evidence_refs=("repo_snapshot",),
    )
    assert replay.state_for("02-implementation").state is NodeState.READY


def test_nonpass_dependency_blocks_descendants_and_surfaces_review() -> None:
    graph = full_graph()
    simulator = SupervisorSimulator(graph, ModelRouter(DEFAULT_MODELS))
    simulator.schedule_next()
    replay = simulator.record_result("01-evidence", NodeOutcome.REVIEW_REQUIRED)

    assert replay.disposition is SupervisorDisposition.REVIEW_REQUIRED
    assert replay.state_for("02-implementation").state is NodeState.BLOCKED
    assert simulator.schedule_next() is None


def test_human_gated_node_is_never_scheduled_autonomously() -> None:
    graph = DependencyGraph(
        objective=objective(),
        nodes=(
            node(
                "manual",
                AgentRole.CRITIC,
                mutation=MutationClass.HUMAN_GATED,
                kind=TaskKind.PLANNING,
            ),
        ),
    )
    simulator = SupervisorSimulator(graph, ModelRouter(DEFAULT_MODELS))

    replay = simulator.replay()
    assert replay.state_for("manual").state is NodeState.READY
    assert replay.disposition is SupervisorDisposition.HUMAN_GATE_REQUIRED
    assert simulator.schedule_next() is None


def test_global_budget_reservation_fails_closed() -> None:
    graph = DependencyGraph(
        objective=objective(total_turns=3),
        nodes=(
            node(
                "a",
                AgentRole.EVIDENCE,
                outputs=("a_output",),
                kind=TaskKind.RESEARCH,
                node_budget=budget(turns=2),
            ),
            node(
                "b",
                AgentRole.CRITIC,
                dependencies=("a",),
                inputs=("a_output",),
                outputs=("b_output",),
                kind=TaskKind.PLANNING,
                node_budget=budget(turns=2),
            ),
        ),
    )
    simulator = SupervisorSimulator(graph, ModelRouter(DEFAULT_MODELS))
    simulator.schedule_next()
    simulator.record_result("a", NodeOutcome.PASS, evidence_refs=("a_output",))

    with pytest.raises(SupervisorBudgetError, match="global budget"):
        simulator.schedule_next()


def test_replay_is_deterministic_and_rejects_out_of_order_scheduling() -> None:
    graph = full_graph()
    simulator = SupervisorSimulator(graph, ModelRouter(DEFAULT_MODELS))
    simulator.schedule_next()
    simulator.record_result("01-evidence", NodeOutcome.PASS, evidence_refs=("repo_snapshot",))

    first = replay_supervision(graph, simulator.events)
    second = replay_supervision(graph, simulator.events)
    assert first.replay_fingerprint == second.replay_fingerprint
    assert first.as_dict() == second.as_dict()
    assert first.production_actions_authorized is False

    illegal = SupervisorEvent(
        sequence=1,
        event_type=SupervisorEventType.NODE_SCHEDULED,
        node_id="02-implementation",
        model_name="GLM-5.1",
        model_provider="zai",
        reserved_budget=budget(),
    )
    with pytest.raises(SupervisorStateError, match="dependency-ready"):
        replay_supervision(graph, (illegal,))


def test_complete_four_role_simulation_finishes_without_widening_authority() -> None:
    graph = full_graph()
    simulator = SupervisorSimulator(graph, ModelRouter(DEFAULT_MODELS))
    outputs = {
        "01-evidence": "repo_snapshot",
        "02-implementation": "candidate_patch",
        "03-validation": "validator_report",
        "04-critic": "critic_report",
    }

    for node_id, evidence_ref in outputs.items():
        decision = simulator.schedule_next()
        assert decision is not None
        assert decision.node_id == node_id
        simulator.record_result(node_id, NodeOutcome.PASS, evidence_refs=(evidence_ref,))

    replay = simulator.replay()
    assert replay.disposition is SupervisorDisposition.COMPLETE
    assert all(runtime.state is NodeState.PASS for runtime in replay.nodes)
    assert replay.execution_authorized is False
    assert replay.repository_mutation_authorized is False
    assert replay.merge_authorized is False
    assert replay.production_actions_authorized is False
