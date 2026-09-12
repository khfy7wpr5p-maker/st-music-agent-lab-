import pytest

from st_music_agent.app8_reliability import (
    ClaimSource,
    CriticSelectionError,
    EvidenceVerdict,
    GateContractError,
    GateDisposition,
    IndependentCriticSelector,
    IndependentDisagreementGate,
    ReliabilityAdvisor,
    ReliabilityDisposition,
    ReliabilityObservation,
    VerificationClaim,
)
from st_music_agent.app8_supervision import AgentRole, NodeOutcome
from st_music_agent.catalog import DEFAULT_MODELS
from st_music_agent.contracts import AgentTask, TaskKind

REPO = "khfy7wpr5p-maker/st-music-agent-lab-"
COMMIT = "d" * 40
ARTIFACT = "c" * 64
PRODUCER_INSTRUCTION = "a" * 64
CRITIC_INSTRUCTION = "b" * 64


def claim(
    claim_id: str,
    role: AgentRole,
    verdict: EvidenceVerdict = EvidenceVerdict.PASS,
    *,
    model_name: str | None = None,
    model_provider: str | None = None,
    source: ClaimSource = ClaimSource.MODEL,
    commit_sha: str = COMMIT,
    artifact_sha256: str = ARTIFACT,
    instruction_fingerprint: str | None = None,
) -> VerificationClaim:
    return VerificationClaim(
        claim_id=claim_id,
        role=role,
        source=source,
        verdict=verdict,
        repository=REPO,
        commit_sha=commit_sha,
        artifact_sha256=artifact_sha256,
        evidence_refs=(f"evidence:{claim_id}",),
        model_name=model_name,
        model_provider=model_provider,
        instruction_fingerprint=instruction_fingerprint,
    )


def producer(verdict: EvidenceVerdict = EvidenceVerdict.PASS) -> VerificationClaim:
    return claim(
        "producer",
        AgentRole.IMPLEMENTATION,
        verdict,
        model_name="GLM-5.1",
        model_provider="zai",
        instruction_fingerprint=PRODUCER_INSTRUCTION,
    )


def validator(verdict: EvidenceVerdict = EvidenceVerdict.PASS) -> VerificationClaim:
    return claim(
        "validator",
        AgentRole.VALIDATION,
        verdict,
        source=ClaimSource.DETERMINISTIC,
    )


def critic(
    verdict: EvidenceVerdict = EvidenceVerdict.PASS,
    *,
    model_name: str = "Qwen3.8",
    model_provider: str = "qwen",
    commit_sha: str = COMMIT,
    artifact_sha256: str = ARTIFACT,
    instruction_fingerprint: str = CRITIC_INSTRUCTION,
) -> VerificationClaim:
    return claim(
        "critic",
        AgentRole.CRITIC,
        verdict,
        model_name=model_name,
        model_provider=model_provider,
        commit_sha=commit_sha,
        artifact_sha256=artifact_sha256,
        instruction_fingerprint=instruction_fingerprint,
    )


def observation(
    index: int,
    outcome: NodeOutcome = NodeOutcome.PASS,
    *,
    project_key: str = "score_restore",
    role: AgentRole = AgentRole.IMPLEMENTATION,
    model_name: str = "GLM-5.1",
    model_provider: str = "zai",
    retries: int = 0,
    disagreements: int = 0,
    human_overrides: int = 0,
    sha_mismatches: int = 0,
    budget_exhaustions: int = 0,
    regression_escapes: int = 0,
) -> ReliabilityObservation:
    return ReliabilityObservation(
        observation_id=f"obs-{index}",
        project_key=project_key,
        role=role,
        model_name=model_name,
        model_provider=model_provider,
        outcome=outcome,
        model_turns=2,
        tool_calls=3,
        retry_count=retries,
        disagreement_count=disagreements,
        human_override_count=human_overrides,
        sha_mismatch_count=sha_mismatches,
        budget_exhaustion_count=budget_exhaustions,
        regression_escape_count=regression_escapes,
    )


def test_independent_critic_selector_excludes_producer_and_prefers_diverse_provider() -> None:
    selection = IndependentCriticSelector(DEFAULT_MODELS).select(
        AgentTask(
            instruction="Independently critique this implementation.",
            kind=TaskKind.PLANNING,
            needs_tools=True,
        ),
        producer_model_name="GLM-5.1",
        producer_provider="zai",
    )

    assert selection.model_name == "Qwen3.8"
    assert selection.provider == "qwen"
    assert selection.model_diverse is True
    assert selection.provider_diverse is True
    assert selection.execution_authorized is False
    assert selection.repository_mutation_authorized is False
    assert selection.merge_authorized is False
    assert selection.production_actions_authorized is False


def test_independent_critic_selector_fails_closed_when_only_producer_can_do_task() -> None:
    selector = IndependentCriticSelector(DEFAULT_MODELS)
    task = AgentTask(
        instruction="Critique a visual score artifact.",
        kind=TaskKind.SCORE_VISION,
        needs_tools=True,
        needs_vision=True,
        minimum_context_tokens=250_000,
    )

    with pytest.raises(CriticSelectionError, match="no independent compatible critic"):
        selector.select(
            task,
            producer_model_name="Kimi-K2.5",
            producer_provider="moonshot",
        )


def test_gate_accepts_only_exact_bound_independent_three_way_pass() -> None:
    report = IndependentDisagreementGate().evaluate(producer(), validator(), critic())

    assert report.disposition is GateDisposition.ACCEPT
    assert report.critic_independent is True
    assert report.provider_diverse is True
    assert report.reasons == ()
    assert report.execution_authorized is False
    assert report.repository_mutation_authorized is False
    assert report.merge_authorized is False
    assert report.production_actions_authorized is False


def test_gate_rejects_unanimous_fail_without_authorizing_action() -> None:
    report = IndependentDisagreementGate().evaluate(
        producer(EvidenceVerdict.FAIL),
        validator(EvidenceVerdict.FAIL),
        critic(EvidenceVerdict.FAIL),
    )

    assert report.disposition is GateDisposition.REJECT
    assert report.execution_authorized is False


def test_gate_turns_model_or_instruction_self_review_into_review_required() -> None:
    same_model = critic(
        model_name="GLM-5.1",
        model_provider="zai",
    )
    report = IndependentDisagreementGate().evaluate(producer(), validator(), same_model)
    assert report.disposition is GateDisposition.REVIEW_REQUIRED
    assert "critic model identity matches producer model" in report.reasons

    same_instruction = critic(instruction_fingerprint=PRODUCER_INSTRUCTION)
    report = IndependentDisagreementGate().evaluate(
        producer(),
        validator(),
        same_instruction,
    )
    assert report.disposition is GateDisposition.REVIEW_REQUIRED
    assert "critic instruction fingerprint matches producer instruction" in report.reasons


def test_gate_binding_mismatch_is_review_required() -> None:
    mismatched = critic(commit_sha="e" * 40)
    report = IndependentDisagreementGate().evaluate(producer(), validator(), mismatched)

    assert report.disposition is GateDisposition.REVIEW_REQUIRED
    assert "claims are not bound to the same repository/commit/artifact" in report.reasons


def test_gate_disagreement_never_optimistically_accepts() -> None:
    report = IndependentDisagreementGate().evaluate(
        producer(),
        validator(EvidenceVerdict.FAIL),
        critic(),
    )

    assert report.disposition is GateDisposition.REVIEW_REQUIRED
    assert "producer, validator, and critic disagree" in report.reasons


def test_gate_abstains_on_unavailable_or_abstained_required_evidence() -> None:
    unavailable = IndependentDisagreementGate().evaluate(
        producer(),
        validator(EvidenceVerdict.UNAVAILABLE),
        critic(),
    )
    assert unavailable.disposition is GateDisposition.ABSTAIN

    abstained = IndependentDisagreementGate().evaluate(
        producer(),
        validator(),
        critic(EvidenceVerdict.ABSTAIN),
    )
    assert abstained.disposition is GateDisposition.ABSTAIN


def test_gate_enforces_role_contract() -> None:
    wrong_role = claim(
        "wrong",
        AgentRole.VALIDATION,
        model_name="Qwen3.8",
        model_provider="qwen",
    )
    with pytest.raises(GateContractError, match="producer claim"):
        IndependentDisagreementGate().evaluate(wrong_role, validator(), critic())


def test_reliability_requires_evidence_before_stable_classification() -> None:
    summary = ReliabilityAdvisor(minimum_attempts=5).summarize(
        [observation(1), observation(2)]
    )[0]

    assert summary.disposition is ReliabilityDisposition.INSUFFICIENT_DATA
    assert summary.auto_apply is False
    assert summary.privilege_change_authorized is False
    assert summary.execution_authorized is False
    assert summary.production_actions_authorized is False


def test_reliability_marks_clean_history_stable() -> None:
    summary = ReliabilityAdvisor(minimum_attempts=5).summarize(
        [observation(index) for index in range(5)]
    )[0]

    assert summary.disposition is ReliabilityDisposition.STABLE
    assert summary.attempts == 5
    assert summary.success_rate == 1.0
    assert summary.failure_rate == 0.0
    assert summary.mean_model_turns == 2.0
    assert summary.mean_tool_calls == 3.0


def test_reliability_watch_and_review_thresholds_are_transparent() -> None:
    watch_observations = [observation(index) for index in range(4)] + [
        observation(5, NodeOutcome.FAIL)
    ]
    watch = ReliabilityAdvisor(minimum_attempts=5).summarize(watch_observations)[0]
    assert watch.disposition is ReliabilityDisposition.WATCH
    assert watch.failure_rate == 0.2

    review_observations = [observation(index) for index in range(4)] + [
        observation(5, sha_mismatches=1)
    ]
    review = ReliabilityAdvisor(minimum_attempts=5).summarize(review_observations)[0]
    assert review.disposition is ReliabilityDisposition.REVIEW
    assert review.sha_mismatches == 1


def test_regression_escape_forces_review_even_when_all_tasks_pass() -> None:
    observations = [observation(index) for index in range(4)] + [
        observation(5, regression_escapes=1)
    ]
    summary = ReliabilityAdvisor(minimum_attempts=5).summarize(observations)[0]

    assert summary.success_rate == 1.0
    assert summary.regression_escapes == 1
    assert summary.disposition is ReliabilityDisposition.REVIEW


def test_reliability_summaries_are_deterministic_and_grouped_by_role_model_project() -> None:
    observations = [
        observation(1, project_key="score_restore"),
        observation(2, project_key="score_restore"),
        observation(
            3,
            project_key="guitar_tab",
            role=AgentRole.CRITIC,
            model_name="Qwen3.8",
            model_provider="qwen",
        ),
    ]
    advisor = ReliabilityAdvisor(minimum_attempts=1)
    first = advisor.summarize(observations)
    second = advisor.summarize(reversed(observations))

    assert [item.as_dict() for item in first] == [item.as_dict() for item in second]
    assert len(first) == 2
    assert all(item.auto_apply is False for item in first)
