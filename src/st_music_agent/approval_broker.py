from __future__ import annotations

import secrets
import threading
from dataclasses import dataclass
from enum import Enum

from .contracts import ActionRequest
from .tools import ActionApproval


class ApprovalState(str, Enum):
    PENDING = "pending"
    APPROVED = "approved"
    DENIED = "denied"
    CONSUMED = "consumed"


class ApprovalBrokerError(RuntimeError):
    pass


@dataclass(frozen=True, slots=True)
class ApprovalTicket:
    ticket_id: str
    action_name: str
    target: str
    state: ApprovalState


@dataclass(slots=True)
class _StoredTicket:
    action_name: str
    target: str
    state: ApprovalState = ApprovalState.PENDING


class HostApprovalBroker:
    """One-shot host-side approval store.

    This class is deliberately not a model tool. A caller may expose pending ticket metadata to
    a human UI, but only trusted host code should invoke approve/deny/consume.
    """

    def __init__(self) -> None:
        self._tickets: dict[str, _StoredTicket] = {}
        self._lock = threading.Lock()

    def request(self, action: ActionRequest) -> ApprovalTicket:
        if not action.name.strip():
            raise ValueError("action name must not be empty")
        ticket_id = secrets.token_urlsafe(24)
        with self._lock:
            self._tickets[ticket_id] = _StoredTicket(
                action_name=action.name,
                target=action.target,
            )
            return self._snapshot(ticket_id, self._tickets[ticket_id])

    def approve(self, ticket_id: str) -> ApprovalTicket:
        with self._lock:
            ticket = self._get(ticket_id)
            if ticket.state is not ApprovalState.PENDING:
                raise ApprovalBrokerError("only pending approval tickets can be approved")
            ticket.state = ApprovalState.APPROVED
            return self._snapshot(ticket_id, ticket)

    def deny(self, ticket_id: str) -> ApprovalTicket:
        with self._lock:
            ticket = self._get(ticket_id)
            if ticket.state is not ApprovalState.PENDING:
                raise ApprovalBrokerError("only pending approval tickets can be denied")
            ticket.state = ApprovalState.DENIED
            return self._snapshot(ticket_id, ticket)

    def consume(self, ticket_id: str, action: ActionRequest) -> ActionApproval:
        with self._lock:
            ticket = self._get(ticket_id)
            if ticket.state is not ApprovalState.APPROVED:
                raise ApprovalBrokerError("approval ticket is not approved")
            if ticket.action_name != action.name or ticket.target != action.target:
                raise ApprovalBrokerError("approval ticket does not match the requested action")
            ticket.state = ApprovalState.CONSUMED
            return ActionApproval(action_name=ticket.action_name, target=ticket.target)

    def status(self, ticket_id: str) -> ApprovalTicket:
        with self._lock:
            ticket = self._get(ticket_id)
            return self._snapshot(ticket_id, ticket)

    def _get(self, ticket_id: str) -> _StoredTicket:
        if not isinstance(ticket_id, str) or not ticket_id:
            raise ApprovalBrokerError("approval ticket id is invalid")
        ticket = self._tickets.get(ticket_id)
        if ticket is None:
            raise ApprovalBrokerError("approval ticket does not exist")
        return ticket

    @staticmethod
    def _snapshot(ticket_id: str, ticket: _StoredTicket) -> ApprovalTicket:
        return ApprovalTicket(
            ticket_id=ticket_id,
            action_name=ticket.action_name,
            target=ticket.target,
            state=ticket.state,
        )
