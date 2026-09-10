from st_music_agent import (
    ActionRequest,
    AutonomyDecision,
    AutonomyPolicy,
    RiskLevel,
)

POLICY = AutonomyPolicy()


def test_read_only_action_is_autonomous() -> None:
    decision = POLICY.decide(ActionRequest(name="inspect_repository", risk=RiskLevel.READ_ONLY))
    assert decision is AutonomyDecision.AUTO_EXECUTE


def test_reversible_feature_branch_write_is_autonomous() -> None:
    decision = POLICY.decide(
        ActionRequest(
            name="write_feature_file",
            risk=RiskLevel.REVERSIBLE_WRITE,
            metadata={"branch": "a1-a3-agent-foundation"},
        )
    )
    assert decision is AutonomyDecision.AUTO_EXECUTE


def test_protected_branch_write_requires_human() -> None:
    decision = POLICY.decide(
        ActionRequest(
            name="write_main",
            risk=RiskLevel.REVERSIBLE_WRITE,
            metadata={"branch": "main"},
        )
    )
    assert decision is AutonomyDecision.REQUIRE_HUMAN


def test_destructive_action_requires_human() -> None:
    decision = POLICY.decide(ActionRequest(name="delete_repository", risk=RiskLevel.DESTRUCTIVE))
    assert decision is AutonomyDecision.REQUIRE_HUMAN


def test_secret_access_is_denied() -> None:
    decision = POLICY.decide(
        ActionRequest(
            name="read_secret",
            risk=RiskLevel.READ_ONLY,
            metadata={"requests_secret": True},
        )
    )
    assert decision is AutonomyDecision.DENY
