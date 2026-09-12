import json
from types import SimpleNamespace

import pytest

from st_music_agent.agent_tools import ToolRegistry
from st_music_agent.app8_execution import (
    App8ExecutionError,
    ExactCommitReadToolset,
    GuardedImplementationBridge,
    ImplementationDisposition,
    ReadOnlySpecialistRunner,
    SpecialistOutputError,
    evaluate_verified_cycle,
    validate_execution_graph,
)
from st_music_agent.app8_reliability import GateDisposition
from st_music_agent.app8_supervision import (
    AgentRole,
    BudgetEnvelope,
    DependencyGraph,
    MutationClass,
    ObjectiveContract,
    SubtaskNode,
)
from st_music_agent.catalog import DEFAULT_MODELS
from st_music_agent.contracts import TaskKind
from st_music_agent.task_state import TaskOutcome

REPO = "khfy7wpr5p-maker/st-music-agent-lab-"
BASE = "a" * 40
HEAD = "b" * 40
AUDIT = "c" * 64
BRANCH = "st-agent/demo/abc123"


def profile(name: str):
    return next(item for item in DEFAULT_MODELS if item.name == name)


def budget() -> BudgetEnvelope:
    return BudgetEnvelope(
        max_elapsed_seconds=60.0,
        max_model_turns=4,
        max_tool_calls=4,
        max_model_facing_bytes=100_000,
    )


def objective() -> ObjectiveContract:
    return ObjectiveContract(
        objective_id="app8c-demo",
        instruction="Execute one guarded multi-agent cycle.",
        repositories=(REPO,),
        allowed_change_classes=(
            MutationClass.READ_ONLY,
            MutationClass.REVERSIBLE_FEATURE_BRANCH,
        ),
        success_evidence=("critic_report",),
        max_agent_count=4,
        total_budget=BudgetEnvelope(
            max_elapsed_seconds=600,
            max_model_turns=20,
            max_tool_calls=20,
            max_model_facing_bytes=1_000_000,
        ),
        human_gates=("pull_request", "merge"),
        stop_conditions=("budget_exhausted", "verification_failed"),
    )


def node(
    node_id: str,
    role: AgentRole,
    *,
    branch: str = BRANCH,
    mutation: MutationClass = MutationClass.READ_ONLY,
    kind: TaskKind = TaskKind.GENERAL,
    dependencies=(),
    inputs=(),
    outputs=("evidence",),
) -> SubtaskNode:
    return SubtaskNode(
        node_id=node_id,
        parent_objective_id="app8c-demo",
        role=role,
        instruction=f"Perform {role.value} work for {node_id}",
        dependencies=tuple(dependencies),
        repository=REPO,
        branch_scope=branch,
        input_evidence_refs=tuple(inputs),
        expected_output_evidence=tuple(outputs),
        budget=budget(),
        mutation_class=mutation,
        completion_criteria=("evidence present",),
        abstention_criteria=("evidence unavailable",),
        task_kind=kind,
        needs_tools=True,
    )


def implementation_node() -> SubtaskNode:
    return node(
        "02-implementation",
        AgentRole.IMPLEMENTATION,
        mutation=MutationClass.REVERSIBLE_FEATURE_BRANCH,
        kind=TaskKind.CODE,
        outputs=("candidate_patch",),
    )


class FakeReadClient:
    def __init__(self, *, branch_sha: str = HEAD, tree_sha: str = HEAD) -> None:
        self.branch_sha = branch_sha
        self.tree_sha = tree_sha
        self.read_refs: list[str | None] = []

    def branch_info(self, branch: str):
        return {"name": branch, "commit_sha": self.branch_sha}

    def repository_tree(self, ref: str = "main"):
        return {
            "ref": ref,
            "commit_sha": self.tree_sha,
            "files": [
                {"path": "README.md", "sha": "blob-1", "size": 100},
                {"path": "src/app.py", "sha": "blob-2", "size": 200},
            ],
        }

    def read_file(self, path: str, ref: str | None = None):
        self.read_refs.append(ref)
        return {"path": path, "content": f"content:{path}", "ref": ref}


class FinalJsonClient:
    def __init__(self, verdict: str = "pass", summary: str = "verified evidence") -> None:
        self.verdict = verdict
        self.summary = summary
        self.tools_seen = None

    def complete_with_tools(self, messages, tools):
        self.tools_seen = tools
        return {
            "role": "assistant",
            "content": json.dumps({"verdict": self.verdict, "summary": self.summary}),
        }


class ReadThenFinalClient:
    def __init__(self) -> None:
        self.calls = 0
        self.tools_seen = None

    def complete_with_tools(self, messages, tools):
        self.calls += 1
        self.tools_seen = tools
        if self.calls == 1:
            return {
                "role": "assistant",
                "content": None,
                "tool_calls": [
                    {
                        "id": "read-1",
                        "type": "function",
                        "function": {
                            "name": "task.read_file",
                            "arguments": json.dumps({"path": "README.md"}),
                        },
                    }
                ],
            }
        return {
            "role": "assistant",
            "content": json.dumps({"verdict": "pass", "summary": "exact read checked"}),
        }


class InvalidOutputClient:
    def complete_with_tools(self, messages, tools):
        return {"role": "assistant", "content": "not-json"}


class FakeImplementationService:
    def __init__(
        self,
        *,
        outcome: str = TaskOutcome.VERIFIED_SUCCESS.value,
        audit_verified: bool = True,
        repository: str = REPO,
        feature_branch: str = BRANCH,
        base_sha: str = BASE,
        head_sha: str = HEAD,
    ) -> None:
        self.outcome = outcome
        self.audit_verified = audit_verified
        self.repository = repository
        self.feature_branch = feature_branch
        self.base_sha = base_sha
        self.head_sha = head_sha
        self.calls: list[str] = []

    def preview(self, project: str, instruction: str):
        self.calls.append("preview")
        return SimpleNamespace(
            task_id="task:" + "1" * 64,
            project=project,
            repository=self.repository,
            base_branch="main",
            base_sha=self.base_sha,
            feature_branch=self.feature_branch,
        )

    def run(self, task_id: str):
        self.calls.append("run")
        return SimpleNamespace(
            task_id=task_id,
            repository=self.repository,
            feature_branch=self.feature_branch,
            base_sha=self.base_sha,
            head_sha=self.head_sha,
            model_name="GLM-5.1",
        )

    def refresh_evidence(self, task_id: str):
        self.calls.append("refresh_evidence")
        return {
            "task_id": task_id,
            "outcome": self.outcome,
            "commit": {"head_sha": self.head_sha},
        }

    def status(self, task_id: str):
        self.calls.append("status")
        return self.refresh_evidence(task_id)

    def verify_current_audit(self, task_id: str):
        self.calls.append("verify_current_audit")
        return {
            "task_id": task_id,
            "verified": self.audit_verified,
            "status": "VERIFIED" if self.audit_verified else "INVALID",
            "verification_sha256": AUDIT,
        }


def test_exact_read_tools_expose_no_ref_or_write_surface() -> None:
    registry = ToolRegistry()
    ExactCommitReadToolset(FakeReadClient(), branch=BRANCH, expected_sha=HEAD).register_into(
        registry
    )
    tools = registry.provider_tools()
    names = [tool["function"]["name"] for tool in tools]

    assert names == ["task.list_files", "task.read_file"]
    read_tool = next(tool for tool in tools if tool["function"]["name"] == "task.read_file")
    properties = read_tool["function"]["parameters"]["properties"]
    assert set(properties) == {"path"}
    assert "ref" not in properties
    assert all("write" not in name for name in names)


def test_exact_read_tool_injects_immutable_sha_host_side() -> None:
    read_client = FakeReadClient()
    client = ReadThenFinalClient()
    specialist = ReadOnlySpecialistRunner(
        node=node("01-evidence", AgentRole.EVIDENCE, kind=TaskKind.RESEARCH),
        exact_sha=HEAD,
        read_client=read_client,
        profile=profile("GLM-5.1"),
        provider_client=client,
    )

    result = specialist.run()

    assert read_client.read_refs == [HEAD]
    assert result.exact_sha == HEAD
    assert result.repository_mutation_authorized is False
    assert result.merge_authorized is False
    assert result.production_actions_authorized is False


def test_exact_read_capture_fails_if_branch_or_tree_moved() -> None:
    with pytest.raises(App8ExecutionError, match="branch does not resolve"):
        ExactCommitReadToolset(FakeReadClient(branch_sha=BASE), branch=BRANCH, expected_sha=HEAD)

    with pytest.raises(App8ExecutionError, match="tree is not bound"):
        ExactCommitReadToolset(FakeReadClient(tree_sha=BASE), branch=BRANCH, expected_sha=HEAD)


def test_specialists_must_be_read_only_and_nonimplementation() -> None:
    with pytest.raises(App8ExecutionError, match="role is not allowed"):
        ReadOnlySpecialistRunner(
            node=implementation_node(),
            exact_sha=HEAD,
            read_client=FakeReadClient(),
            profile=profile("GLM-5.1"),
            provider_client=FinalJsonClient(),
        )

    writable_critic = node(
        "critic",
        AgentRole.CRITIC,
        mutation=MutationClass.HUMAN_GATED,
        kind=TaskKind.PLANNING,
    )
    with pytest.raises(App8ExecutionError, match="READ_ONLY"):
        ReadOnlySpecialistRunner(
            node=writable_critic,
            exact_sha=HEAD,
            read_client=FakeReadClient(),
            profile=profile("Qwen3.8"),
            provider_client=FinalJsonClient(),
        )


def test_specialist_rejects_incompatible_model_profile() -> None:
    visual = SubtaskNode(
        node_id="vision",
        parent_objective_id="app8c-demo",
        role=AgentRole.EVIDENCE,
        instruction="Inspect visual score",
        dependencies=(),
        repository=REPO,
        branch_scope=BRANCH,
        input_evidence_refs=(),
        expected_output_evidence=("vision_report",),
        budget=budget(),
        mutation_class=MutationClass.READ_ONLY,
        completion_criteria=("report",),
        abstention_criteria=("unavailable",),
        task_kind=TaskKind.SCORE_VISION,
        needs_tools=True,
        needs_vision=True,
    )
    with pytest.raises(App8ExecutionError, match="does not support"):
        ReadOnlySpecialistRunner(
            node=visual,
            exact_sha=HEAD,
            read_client=FakeReadClient(),
            profile=profile("GLM-5.1"),
            provider_client=FinalJsonClient(),
        )


def test_specialist_final_output_is_strict_json() -> None:
    specialist = ReadOnlySpecialistRunner(
        node=node("critic", AgentRole.CRITIC, kind=TaskKind.PLANNING),
        exact_sha=HEAD,
        read_client=FakeReadClient(),
        profile=profile("Qwen3.8"),
        provider_client=InvalidOutputClient(),
        subject_artifact_sha256="d" * 64,
    )
    with pytest.raises(SpecialistOutputError, match="not valid JSON"):
        specialist.run()


def test_validation_claim_is_exact_bound_to_subject_artifact() -> None:
    subject = "d" * 64
    specialist = ReadOnlySpecialistRunner(
        node=node("validation", AgentRole.VALIDATION, kind=TaskKind.CODE),
        exact_sha=HEAD,
        read_client=FakeReadClient(),
        profile=profile("Qwen3.8"),
        provider_client=FinalJsonClient(),
        subject_artifact_sha256=subject,
    )
    result = specialist.run()
    claim = result.to_verification_claim()

    assert claim.repository == REPO
    assert claim.commit_sha == HEAD
    assert claim.artifact_sha256 == subject
    assert claim.model_name == "Qwen3.8"


def test_implementation_bridge_requires_exact_preview_binding() -> None:
    bridge = GuardedImplementationBridge()

    with pytest.raises(App8ExecutionError, match="repository does not match"):
        bridge.execute(
            node=implementation_node(),
            project="demo",
            expected_base_sha=BASE,
            producer_provider="zai",
            service=FakeImplementationService(repository="other/repo"),
        )

    with pytest.raises(App8ExecutionError, match="base SHA does not match"):
        bridge.execute(
            node=implementation_node(),
            project="demo",
            expected_base_sha=BASE,
            producer_provider="zai",
            service=FakeImplementationService(base_sha="f" * 40),
        )

    with pytest.raises(App8ExecutionError, match="not bound to the preview feature branch"):
        bridge.execute(
            node=implementation_node(),
            project="demo",
            expected_base_sha=BASE,
            producer_provider="zai",
            service=FakeImplementationService(feature_branch="st-agent/demo/other"),
        )


def test_implementation_bridge_refuses_nonimplementation_and_readonly_nodes() -> None:
    bridge = GuardedImplementationBridge()
    with pytest.raises(App8ExecutionError, match="IMPLEMENTATION"):
        bridge.execute(
            node=node("validation", AgentRole.VALIDATION, kind=TaskKind.CODE),
            project="demo",
            expected_base_sha=BASE,
            producer_provider="zai",
            service=FakeImplementationService(),
        )

    readonly_impl = node(
        "implementation",
        AgentRole.IMPLEMENTATION,
        mutation=MutationClass.READ_ONLY,
        kind=TaskKind.CODE,
    )
    with pytest.raises(App8ExecutionError, match="REVERSIBLE_FEATURE_BRANCH"):
        bridge.execute(
            node=readonly_impl,
            project="demo",
            expected_base_sha=BASE,
            producer_provider="zai",
            service=FakeImplementationService(),
        )


def test_verified_implementation_requires_app7_audit_and_never_opens_pr() -> None:
    service = FakeImplementationService()
    record = GuardedImplementationBridge().execute(
        node=implementation_node(),
        project="demo",
        expected_base_sha=BASE,
        producer_provider="zai",
        service=service,
    )

    assert record.disposition is ImplementationDisposition.VERIFIED
    assert record.head_sha == HEAD
    assert record.audit_verification_sha256 == AUDIT
    assert record.pr_open_authorized is False
    assert record.merge_authorized is False
    assert "verify_current_audit" in service.calls
    assert "open_pull_request" not in service.calls

    claim = record.to_verification_claim()
    assert claim.commit_sha == HEAD
    assert claim.artifact_sha256 == record.artifact_sha256
    assert claim.model_name == "GLM-5.1"
    assert claim.model_provider == "zai"


def test_verified_implementation_fails_closed_on_invalid_audit() -> None:
    with pytest.raises(App8ExecutionError, match="audit verification failed"):
        GuardedImplementationBridge().execute(
            node=implementation_node(),
            project="demo",
            expected_base_sha=BASE,
            producer_provider="zai",
            service=FakeImplementationService(audit_verified=False),
        )


def test_pending_or_review_implementation_cannot_become_producer_claim() -> None:
    pending_service = FakeImplementationService(outcome=TaskOutcome.WORKING.value)
    pending = GuardedImplementationBridge().execute(
        node=implementation_node(),
        project="demo",
        expected_base_sha=BASE,
        producer_provider="zai",
        service=pending_service,
    )
    assert pending.disposition is ImplementationDisposition.PENDING
    assert "verify_current_audit" not in pending_service.calls
    with pytest.raises(App8ExecutionError, match="requires VERIFIED"):
        pending.to_verification_claim()

    review = GuardedImplementationBridge().execute(
        node=implementation_node(),
        project="demo",
        expected_base_sha=BASE,
        producer_provider="zai",
        service=FakeImplementationService(outcome=TaskOutcome.REVIEW_REQUIRED.value),
    )
    assert review.disposition is ImplementationDisposition.REVIEW_REQUIRED


def test_exact_bound_verified_cycle_accepts_without_widening_authority() -> None:
    implementation = GuardedImplementationBridge().execute(
        node=implementation_node(),
        project="demo",
        expected_base_sha=BASE,
        producer_provider="zai",
        service=FakeImplementationService(),
    )
    validation = ReadOnlySpecialistRunner(
        node=node("03-validation", AgentRole.VALIDATION, kind=TaskKind.CODE),
        exact_sha=HEAD,
        read_client=FakeReadClient(),
        profile=profile("Kimi-K2.5"),
        provider_client=FinalJsonClient(),
        subject_artifact_sha256=implementation.artifact_sha256,
    ).run()
    critic = ReadOnlySpecialistRunner(
        node=node("04-critic", AgentRole.CRITIC, kind=TaskKind.PLANNING),
        exact_sha=HEAD,
        read_client=FakeReadClient(),
        profile=profile("Qwen3.8"),
        provider_client=FinalJsonClient(),
        subject_artifact_sha256=implementation.artifact_sha256,
    ).run()

    gate = evaluate_verified_cycle(implementation, validation, critic)

    assert gate.disposition is GateDisposition.ACCEPT
    assert gate.execution_authorized is False
    assert gate.repository_mutation_authorized is False
    assert gate.merge_authorized is False
    assert gate.production_actions_authorized is False


def test_graph_guard_allows_only_one_writable_implementation_role() -> None:
    valid = DependencyGraph(
        objective=objective(),
        nodes=(
            implementation_node(),
            node(
                "03-validation",
                AgentRole.VALIDATION,
                dependencies=("02-implementation",),
                inputs=("candidate_patch",),
                outputs=("validator_report",),
                kind=TaskKind.CODE,
            ),
        ),
    )
    validate_execution_graph(valid)

    second_impl = SubtaskNode(
        node_id="05-implementation",
        parent_objective_id="app8c-demo",
        role=AgentRole.IMPLEMENTATION,
        instruction="Second write path",
        dependencies=("02-implementation",),
        repository=REPO,
        branch_scope="st-agent/demo/second",
        input_evidence_refs=("candidate_patch",),
        expected_output_evidence=("second_patch",),
        budget=budget(),
        mutation_class=MutationClass.REVERSIBLE_FEATURE_BRANCH,
        completion_criteria=("patch",),
        abstention_criteria=("blocked",),
        task_kind=TaskKind.CODE,
    )
    invalid = DependencyGraph(objective=objective(), nodes=(implementation_node(), second_impl))
    with pytest.raises(App8ExecutionError, match="at most one implementation"):
        validate_execution_graph(invalid)
