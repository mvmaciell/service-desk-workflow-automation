from __future__ import annotations

from enum import Enum, auto


class TicketWorkflowState(Enum):
    """Lifecycle states of a ticket within SDWA tracking."""

    DETECTED = auto()
    ALLOCATION_SUGGESTED = auto()
    ALLOCATION_APPROVED = auto()
    ASSIGNED = auto()
    IN_PROGRESS = auto()
    COMPLETED = auto()
    COMPLETION_NOTIFIED = auto()
    FAILED_RETRYABLE = auto()
    CANCELLED = auto()


# Valid forward transitions from each state.
_VALID_TRANSITIONS: dict[TicketWorkflowState, frozenset[TicketWorkflowState]] = {
    TicketWorkflowState.DETECTED: frozenset({
        TicketWorkflowState.ALLOCATION_SUGGESTED,
        TicketWorkflowState.FAILED_RETRYABLE,
        TicketWorkflowState.CANCELLED,
    }),
    TicketWorkflowState.ALLOCATION_SUGGESTED: frozenset({
        TicketWorkflowState.ALLOCATION_APPROVED,
        TicketWorkflowState.FAILED_RETRYABLE,
        TicketWorkflowState.CANCELLED,
    }),
    TicketWorkflowState.ALLOCATION_APPROVED: frozenset({
        TicketWorkflowState.ASSIGNED,
        TicketWorkflowState.FAILED_RETRYABLE,
        TicketWorkflowState.CANCELLED,
    }),
    TicketWorkflowState.ASSIGNED: frozenset({
        TicketWorkflowState.IN_PROGRESS,
        TicketWorkflowState.COMPLETED,
        TicketWorkflowState.FAILED_RETRYABLE,
        TicketWorkflowState.CANCELLED,
    }),
    TicketWorkflowState.IN_PROGRESS: frozenset({
        TicketWorkflowState.COMPLETED,
        TicketWorkflowState.FAILED_RETRYABLE,
        TicketWorkflowState.CANCELLED,
    }),
    TicketWorkflowState.COMPLETED: frozenset({
        TicketWorkflowState.COMPLETION_NOTIFIED,
        TicketWorkflowState.FAILED_RETRYABLE,
    }),
    TicketWorkflowState.COMPLETION_NOTIFIED: frozenset(),
    TicketWorkflowState.FAILED_RETRYABLE: frozenset({
        TicketWorkflowState.DETECTED,
        TicketWorkflowState.ALLOCATION_SUGGESTED,
        TicketWorkflowState.ASSIGNED,
        TicketWorkflowState.CANCELLED,
    }),
    TicketWorkflowState.CANCELLED: frozenset(),
}


def can_transition(current: TicketWorkflowState, target: TicketWorkflowState) -> bool:
    return target in _VALID_TRANSITIONS.get(current, frozenset())


class AllocationStrategy(Enum):
    SKILL_MATCH = "skill_match"
    CURRENT_LOAD = "current_load"
    HISTORICAL_LOAD = "historical_load"
    ALPHABETICAL = "alphabetical"


class AuditAction(Enum):
    TICKET_DETECTED = "ticket_detected"
    BASELINE_CREATED = "baseline_created"
    ALLOCATION_SUGGESTED = "allocation_suggested"
    COORDINATOR_NOTIFIED = "coordinator_notified"
    ALLOCATION_APPROVED = "allocation_approved"
    DEVELOPER_NOTIFIED = "developer_notified"
    STATUS_CHANGED = "status_changed"
    COMPLETION_DETECTED = "completion_detected"
    COMPLETION_NOTIFIED = "completion_notified"
    NOTIFICATION_FAILED = "notification_failed"
    APPROVAL_TIMEOUT = "approval_timeout"
    TICKET_RETURNED = "ticket_returned"


class NotificationType(Enum):
    NEW_TICKET_ALERT = "new_ticket_alert"
    ALLOCATION_SUGGESTION = "allocation_suggestion"
    ASSIGNMENT_NOTICE = "assignment_notice"
    COMPLETION_NOTICE = "completion_notice"
    LOAD_BOARD = "load_board"
    TEST_MESSAGE = "test_message"
