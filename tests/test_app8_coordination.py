import pytest

from st_music_agent.app8_coordination import (
    CoordinationContractError,
    CoordinationDisposition,
    CoordinationItemState,
    CoordinationOutcome,
    CrossProjectCoordinator,
    CrossProjectPlan,
    ProjectCompletionReceipt,
    ProjectWorkItem,
    replay_coordination,
)
from st_music_agent.app8_execution import (
    ImplementationDisposition,
    ImplementationExecutionRecord,
)
from st_music_agent.app8_reliability import GateDisposition, GateReport
from st_music_agent.app8_supervision import MutationClass
from st_music_agent.music_evidence import MusicProject

RESTORE_REPO = "khfy7wpr5p-maker/st-score-restore-engine"
TAB_REPO = "khfy7wpr5p-maker/musicxml-to-guitar-tab-engine"
EDITOR_REPO = "khfy7wpr5p-maker/st-score-editor-core"
RESTORE_SHA = "a" * 40
TAB_BASE = "b" * 40
TAB_HEAD = "c" * 40


def work_item(
    item_id: str,
    project: MusicProject,
    repository: str,
    base_sha: str,
    *,
    dependencies=(),
    required=(),
    produces=("evidence",),
    mutation=MutationClass.READ_ONLY,
) -> ProjectWorkItem:
    return ProjectWorkItem(
        item_id=item_id,
        project=project,
        repository=repository,
        expected_base_sha=base_sha,
        instruction=f"Perform bounded work for {item_id}",
        dependencies=tuple(dependencies),
        required_upstream_evidence=tuple(required),
        produces_evidence=tuple(produces),
        mutation_class=mutation,
    )


def plan() -> CrossProjectPlan:
    return CrossProjectPlan(
        plan_id="restore-to-tab",
        items=(
            work_item(
                "01-restore",
                MusicProject.SCORE_RESTORE,
                RESTORE_REPO,
                RESTORE_SHA,
                produces=("restored_score",),
            ),
            work_item(
                "02-tab",
                MusicProject.MUSICXML_GUITAR_TAB,
                TAB_REPO,
                TAB_BASE,
                dependencies=("01-restore",),
                required=("restored_score",),
                produces=("tab_candidate",),
                mutation=MutationClass.REVERSIBLE_FEATURE_BRANCH,
            ),
        ),
    )


def read_only_receipt(item: ProjectWorkItem) -> ProjectCompletionReceipt:
    return ProjectCompletionReceipt.from_host_verified_read_only(
        item,
        exact_sha=item.expected_base_sha,
        artifact_sha256="1" * 64,
        verification_sha256="2" * 64,
        produced_evidence=item.produces_evidence,
    )


def verified_implementation(item: ProjectWorkItem) -> ImplementationExecutionRecord:
    return ImplementationExecutionRecord(
        node_id="implementation-node",
        repository=item.repository,
        task_id="task:" + "3" * 64,
        base_sha=item.expected_base_sha,
        head_sha=TAB_HEAD,
        feature_branch="st-agent/musicxml-guitar-tab/demo123",
        model_name="GLM-5.1",
        model_provider="zhipu",
        disposition=ImplementationDisposition.VERIFIED,
        artifact_sha256="4" * 64,
        audit_verification_sha256="5" * 64,
        evidence_refs=("app8c-task:demo", "app8c-head:" + TAB_HEAD),
        instruction_fingerprint="6" * 64,
    )


def accepted_gate(item: ProjectWorkItem, implementation: ImplementationExecutionRecord) -> GateReport:
    return GateReport(
        disposition=GateDisposition.ACCEPT,
        repository=item.repository,
        commit_sha=implementation.head_sha,
        artifact_sha256=implementation.artifact_sha256,
        producer_claim_fingerprint="7" * 64,
        validator_claim_fingerprint="8" * 64,
        critic_claim_fingerprint="9" * 64,
        critic_independent=True,
        provider_diverse=True,
        reasons=(),
        report_fingerprint="a" * 64,
    )


def test_project_repository_binding_is_fixed():
    with pytest.raises(CoordinationContractError, match="repository"):
        work_item(
            "bad-repo",
            MusicProject.SCORE_RESTORE,
            TAB_REPO,
            RESTORE_SHA,
        )


def test_plan_requires_declared_upstream_evidence():
    root = work_item(
        "01-restore",
        MusicProject.SCORE_RESTORE,
        RESTORE_REPO,
        RESTORE_SHA,
        produces=("restored_score",),
    )
    downstream = work_item(
        "02-editor",
        MusicProject.SCORE_EDITOR,
        EDITOR_REPO,
        "d" * 40,
        dependencies=("01-restore",),
        required=("missing_evidence",),
    )
    with pytest.raises(CoordinationContractError, match="undeclared upstream evidence"):
        CrossProjectPlan(plan_id="bad-evidence", items=(root, downstream))


def test_plan_rejects_cross_project_cycle():
    first = work_item(
        "01-restore",
        MusicProject.SCORE_RESTORE,
        RESTORE_REPO,
        RESTORE_SHA,
        dependencies=("02-editor",),
        required=("editor_output",),
        produces=("restore_output",),
    )
    second = work_item(
        "02-editor",
        MusicProject.SCORE_EDITOR,
        EDITOR_REPO,
        "d" * 40,
        dependencies=("01-restore",),
        required=("restore_output",),
        produces=("editor_output",),
    )
    with pytest.raises(CoordinationContractError, match="dependency cycle"):
        CrossProjectPlan(plan_id="cycle", items=(first, second))


def test_receipt_driven_cross_project_flow_completes_deterministically():
    cross_plan = plan()
    coordinator = CrossProjectCoordinator(cross_plan)

    first = coordinator.schedule_next()
    assert first is not None
    assert first.item_id == "01-restore"
    assert first.execution_authorized is False
    assert first.repository_mutation_authorized is False

    root = cross_plan.item("01-restore")
    after_root = coordinator.record_receipt(read_only_receipt(root))
    assert after_root.state_for("01-restore").state is CoordinationItemState.ACCEPTED
    assert after_root.state_for("02-tab").state is CoordinationItemState.READY

    second = coordinator.schedule_next()
    assert second is not None
    assert second.item_id == "02-tab"
    assert second.mutation_class is MutationClass.REVERSIBLE_FEATURE_BRANCH
    assert second.execution_authorized is False

    tab_item = cross_plan.item("02-tab")
    implementation = verified_implementation(tab_item)
    receipt = ProjectCompletionReceipt.from_app8c(
        tab_item,
        implementation,
        accepted_gate(tab_item, implementation),
        produced_evidence=("tab_candidate",),
    )
    final = coordinator.record_receipt(receipt)
    assert final.disposition is CoordinationDisposition.COMPLETE
    assert all(item.state is CoordinationItemState.ACCEPTED for item in final.items)
    assert final.execution_authorized is False
    assert final.repository_mutation_authorized is False
    assert final.pr_open_authorized is False
    assert final.merge_authorized is False
    assert final.production_actions_authorized is False

    replayed = replay_coordination(cross_plan, coordinator.events)
    assert replayed.replay_fingerprint == final.replay_fingerprint
    assert replayed.as_dict() == final.as_dict()


def test_app8c_receipt_requires_accepting_exact_binding():
    tab_item = plan().item("02-tab")
    implementation = verified_implementation(tab_item)
    gate = accepted_gate(tab_item, implementation)
    wrong_gate = GateReport(
        disposition=GateDisposition.ACCEPT,
        repository=gate.repository,
        commit_sha="d" * 40,
        artifact_sha256=gate.artifact_sha256,
        producer_claim_fingerprint=gate.producer_claim_fingerprint,
        validator_claim_fingerprint=gate.validator_claim_fingerprint,
        critic_claim_fingerprint=gate.critic_claim_fingerprint,
        critic_independent=True,
        provider_diverse=True,
        reasons=(),
        report_fingerprint="e" * 64,
    )
    with pytest.raises(CoordinationContractError, match="binding"):
        ProjectCompletionReceipt.from_app8c(
            tab_item,
            implementation,
            wrong_gate,
            produced_evidence=("tab_candidate",),
        )


def test_read_only_receipt_cannot_advance_repository_state():
    root = plan().item("01-restore")
    with pytest.raises(CoordinationContractError, match="exact SHA"):
        ProjectCompletionReceipt.from_host_verified_read_only(
            root,
            exact_sha="f" * 40,
            artifact_sha256="1" * 64,
            verification_sha256="2" * 64,
            produced_evidence=("restored_score",),
        )


def test_nonpass_blocks_dependent_project():
    coordinator = CrossProjectCoordinator(plan())
    scheduled = coordinator.schedule_next()
    assert scheduled is not None and scheduled.item_id == "01-restore"
    replay = coordinator.record_nonpass(
        "01-restore",
        CoordinationOutcome.REVIEW_REQUIRED,
        evidence_ref="review:restore-source-uncertain",
    )
    assert replay.disposition is CoordinationDisposition.REVIEW_REQUIRED
    assert replay.state_for("01-restore").state is CoordinationItemState.REVIEW_REQUIRED
    assert replay.state_for("02-tab").state is CoordinationItemState.BLOCKED
    assert coordinator.schedule_next() is None


def test_plan_and_receipts_never_authorize_external_actions():
    cross_plan = plan()
    plan_payload = cross_plan.as_dict()
    assert plan_payload["execution_authorized"] is False
    assert plan_payload["repository_mutation_authorized"] is False
    assert plan_payload["pr_open_authorized"] is False
    assert plan_payload["merge_authorized"] is False
    assert plan_payload["production_actions_authorized"] is False

    receipt_payload = read_only_receipt(cross_plan.item("01-restore")).as_dict()
    assert receipt_payload["execution_authorized"] is False
    assert receipt_payload["repository_mutation_authorized"] is False
    assert receipt_payload["pr_open_authorized"] is False
    assert receipt_payload["merge_authorized"] is False
    assert receipt_payload["production_actions_authorized"] is False
