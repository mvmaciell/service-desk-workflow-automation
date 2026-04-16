from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from .enums import AuditAction, TicketWorkflowState, can_transition
from .errors import InvalidStateTransitionError


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


# ---------------------------------------------------------------------------
# Ticket  (migrated from root models.py — preserved exactly)
# ---------------------------------------------------------------------------
@dataclass(slots=True)
class Ticket:
    number: str
    source_id: str
    source_name: str
    source_kind: str
    title: str = ""
    customer_ticket_number: str = ""
    activity: str = ""
    company: str = ""
    front: str = ""
    created_label: str = ""
    ticket_type: str = ""
    priority: str = ""
    ticket_status: str = ""
    activity_status: str = ""
    available_estimate: str = ""
    start_date: str = ""
    end_date: str = ""
    due_date: str = ""
    time_to_expire: str = ""
    consultant: str = ""
    collected_at: str = field(default_factory=utc_now_iso)
    raw_fields: dict[str, str] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "number": self.number,
            "source_id": self.source_id,
            "source_name": self.source_name,
            "source_kind": self.source_kind,
            "title": self.title,
            "customer_ticket_number": self.customer_ticket_number,
            "activity": self.activity,
            "company": self.company,
            "front": self.front,
            "created_label": self.created_label,
            "ticket_type": self.ticket_type,
            "priority": self.priority,
            "ticket_status": self.ticket_status,
            "activity_status": self.activity_status,
            "available_estimate": self.available_estimate,
            "start_date": self.start_date,
            "end_date": self.end_date,
            "due_date": self.due_date,
            "time_to_expire": self.time_to_expire,
            "consultant": self.consultant,
            "collected_at": self.collected_at,
            "raw_fields": self.raw_fields,
        }

    def short_text(self) -> str:
        title = self.title or "Sem titulo"
        return f"{self.number} - {title}"


# ---------------------------------------------------------------------------
# Legacy models (migrated from root models.py — preserved exactly)
# ---------------------------------------------------------------------------
@dataclass(slots=True)
class LoadEntry:
    consultant: str
    open_tickets: int

    def to_dict(self) -> dict[str, Any]:
        return {
            "consultant": self.consultant,
            "open_tickets": self.open_tickets,
        }


@dataclass(slots=True)
class DetectionResult:
    source_id: str
    source_name: str
    is_baseline: bool
    total_tickets: int
    new_tickets: list[Ticket]


@dataclass(slots=True)
class DeliveryRequest:
    source_id: str
    source_name: str
    rule_id: str
    title_prefix: str
    recipient_id: str
    recipient_name: str
    recipient_role: str
    webhook_url: str
    ticket: Ticket
    load_entries: list[LoadEntry] = field(default_factory=list)
    created_at: str = field(default_factory=utc_now_iso)


@dataclass(slots=True)
class NotificationResult:
    success: bool
    status_code: int | None
    response_text: str
    payload: dict[str, Any]


# ---------------------------------------------------------------------------
# New domain entities (SDWA workflow)
# ---------------------------------------------------------------------------
@dataclass(slots=True)
class TeamMember:
    id: str
    name: str
    role: str
    skills: list[str] = field(default_factory=list)
    active: bool = True
    webhook_url: str = ""
    max_concurrent_tickets: int = 5

    def __post_init__(self) -> None:
        if self.max_concurrent_tickets < 0:
            raise ValueError(f"max_concurrent_tickets deve ser >= 0, recebido: {self.max_concurrent_tickets}")


@dataclass(slots=True)
class WorkflowItem:
    ticket_number: str
    source_id: str
    current_state: TicketWorkflowState
    detected_at: str
    last_state_change_at: str
    suggested_member_ids: list[str] = field(default_factory=list)
    approved_member_id: str | None = None
    approval_received_at: str | None = None
    completed_at: str | None = None
    last_known_itsm_status: str = ""

    def transition_to(self, target: TicketWorkflowState, timestamp: str) -> None:
        if not can_transition(self.current_state, target):
            raise InvalidStateTransitionError(
                f"Transicao invalida: {self.current_state.name} -> {target.name} "
                f"(ticket {self.ticket_number}, source {self.source_id})"
            )
        self.current_state = target
        self.last_state_change_at = timestamp
        if target == TicketWorkflowState.COMPLETED:
            self.completed_at = timestamp


@dataclass(slots=True)
class AllocationSuggestion:
    member_id: str
    member_name: str
    rank: int
    reason: str
    current_load: int
    skill_match_score: float


@dataclass(slots=True)
class EnhancedLoadEntry:
    """Load entry with member identity — used in allocation and load board."""

    member_id: str
    member_name: str
    open_tickets: int
    role: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "member_id": self.member_id,
            "member_name": self.member_name,
            "open_tickets": self.open_tickets,
            "role": self.role,
        }


@dataclass(slots=True)
class AuditEvent:
    timestamp: str
    action: AuditAction
    actor: str
    details: dict[str, Any] = field(default_factory=dict)
    ticket_number: str | None = None
    source_id: str | None = None
    event_id: str = field(default_factory=lambda: str(uuid.uuid4()))

    def to_dict(self) -> dict[str, Any]:
        return {
            "event_id": self.event_id,
            "timestamp": self.timestamp,
            "action": self.action.value,
            "ticket_number": self.ticket_number,
            "source_id": self.source_id,
            "actor": self.actor,
            "details": self.details,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> AuditEvent:
        return cls(
            event_id=data["event_id"],
            timestamp=data["timestamp"],
            action=AuditAction(data["action"]),
            ticket_number=data.get("ticket_number"),
            source_id=data.get("source_id"),
            actor=data["actor"],
            details=data.get("details", {}),
        )
