from st_music_agent.contracts import ActionRequest, RiskLevel
from st_music_agent.policy import AutonomyDecision
from st_music_agent.tools import ActionApproval, GuardedActionExecutor


def test_autonomous_action_executes_without_approval() -> None:
    executor = GuardedActionExecutor()
    result = executor.execute(
        ActionRequest(name="inspect", risk=RiskLevel.READ_ONLY),
        lambda: "inspected",
    )

    assert result.executed is True
    assert result.value == "inspected"
    assert result.decision is AutonomyDecision.AUTO_EXECUTE


def test_gated_action_requires_exact_approval() -> None:
    executor = GuardedActionExecutor()
    action = ActionRequest(
        name="write_main",
        target="main",
        risk=RiskLevel.REVERSIBLE_WRITE,
        metadata={"branch": "main"},
    )
    calls = 0

    def operation() -> str:
        nonlocal calls
        calls += 1
        return "written"

    blocked = executor.execute(action, operation)
    wrong = executor.execute(action, operation, ActionApproval("write_main", "other"))
    approved = executor.execute(action, operation, ActionApproval("write_main", "main"))

    assert blocked.executed is False
    assert wrong.executed is False
    assert approved.executed is True
    assert approved.value == "written"
    assert calls == 1


def test_denied_action_cannot_be_overridden_by_approval() -> None:
    executor = GuardedActionExecutor()
    action = ActionRequest(
        name="read_secret",
        target="API_KEY",
        risk=RiskLevel.READ_ONLY,
        metadata={"requests_secret": True},
    )

    result = executor.execute(
        action,
        lambda: "secret",
        ActionApproval(action_name="read_secret", target="API_KEY"),
    )

    assert result.executed is False
    assert result.decision is AutonomyDecision.DENY
