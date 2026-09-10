from __future__ import annotations

import pytest

from st_music_agent.approval_broker import (
    ApprovalBrokerError,
    ApprovalState,
    HostApprovalBroker,
)
from st_music_agent.contracts import ActionRequest, RiskLevel


def action(target: str = "main:README.md") -> ActionRequest:
    return ActionRequest(
        name="github.write_file",
        target=target,
        risk=RiskLevel.REVERSIBLE_WRITE,
        metadata={"branch": "main"},
    )


def test_broker_issues_opaque_pending_ticket_and_consumes_once() -> None:
    broker = HostApprovalBroker()
    request = action()

    pending = broker.request(request)
    assert pending.state is ApprovalState.PENDING
    assert len(pending.ticket_id) >= 24
    assert pending.action_name == request.name
    assert pending.target == request.target

    approved = broker.approve(pending.ticket_id)
    assert approved.state is ApprovalState.APPROVED

    approval = broker.consume(pending.ticket_id, request)
    assert approval.action_name == request.name
    assert approval.target == request.target
    assert broker.status(pending.ticket_id).state is ApprovalState.CONSUMED

    with pytest.raises(ApprovalBrokerError, match="not approved"):
        broker.consume(pending.ticket_id, request)


def test_approved_ticket_cannot_authorize_a_different_action_target() -> None:
    broker = HostApprovalBroker()
    pending = broker.request(action())
    broker.approve(pending.ticket_id)

    with pytest.raises(ApprovalBrokerError, match="does not match"):
        broker.consume(pending.ticket_id, action("main:pyproject.toml"))

    assert broker.status(pending.ticket_id).state is ApprovalState.APPROVED


def test_denied_ticket_cannot_be_approved_or_consumed() -> None:
    broker = HostApprovalBroker()
    pending = broker.request(action())
    denied = broker.deny(pending.ticket_id)

    assert denied.state is ApprovalState.DENIED
    with pytest.raises(ApprovalBrokerError, match="pending"):
        broker.approve(pending.ticket_id)
    with pytest.raises(ApprovalBrokerError, match="not approved"):
        broker.consume(pending.ticket_id, action())


def test_unknown_or_invalid_ticket_ids_fail_closed() -> None:
    broker = HostApprovalBroker()

    for ticket_id in ("", "not-a-ticket"):
        with pytest.raises(ApprovalBrokerError):
            broker.status(ticket_id)
