import pytest

from src.megahub_monitor.domain.enums import AuditAction, TicketWorkflowState
from src.megahub_monitor.domain.errors import InvalidStateTransitionError
from src.megahub_monitor.domain.models import (
    AuditEvent,
    EnhancedLoadEntry,
    TeamMember,
    WorkflowItem,
)


class TestWorkflowItem:
    def test_valid_transition(self):
        item = WorkflowItem(
            ticket_number="100",
            source_id="s1",
            current_state=TicketWorkflowState.DETECTED,
            detected_at="2026-04-14T00:00:00+00:00",
            last_state_change_at="2026-04-14T00:00:00+00:00",
        )
        item.transition_to(TicketWorkflowState.ALLOCATION_SUGGESTED, "2026-04-14T00:01:00+00:00")
        assert item.current_state == TicketWorkflowState.ALLOCATION_SUGGESTED
        assert item.last_state_change_at == "2026-04-14T00:01:00+00:00"

    def test_invalid_transition_raises(self):
        item = WorkflowItem(
            ticket_number="100",
            source_id="s1",
            current_state=TicketWorkflowState.COMPLETED,
            detected_at="2026-04-14T00:00:00+00:00",
            last_state_change_at="2026-04-14T00:00:00+00:00",
        )
        with pytest.raises(InvalidStateTransitionError):
            item.transition_to(TicketWorkflowState.DETECTED, "2026-04-14T01:00:00+00:00")

    def test_completion_sets_completed_at(self):
        item = WorkflowItem(
            ticket_number="100",
            source_id="s1",
            current_state=TicketWorkflowState.IN_PROGRESS,
            detected_at="2026-04-14T00:00:00+00:00",
            last_state_change_at="2026-04-14T00:00:00+00:00",
        )
        ts = "2026-04-14T02:00:00+00:00"
        item.transition_to(TicketWorkflowState.COMPLETED, ts)
        assert item.completed_at == ts

    def test_non_completion_does_not_set_completed_at(self):
        item = WorkflowItem(
            ticket_number="100",
            source_id="s1",
            current_state=TicketWorkflowState.DETECTED,
            detected_at="2026-04-14T00:00:00+00:00",
            last_state_change_at="2026-04-14T00:00:00+00:00",
        )
        item.transition_to(TicketWorkflowState.ALLOCATION_SUGGESTED, "2026-04-14T00:01:00+00:00")
        assert item.completed_at is None


class TestTeamMember:
    def test_defaults(self):
        m = TeamMember(id="dev-1", name="Dev 1", role="developer")
        assert m.active is True
        assert m.skills == []
        assert m.max_concurrent_tickets == 5
        assert m.webhook_url == ""


class TestEnhancedLoadEntry:
    def test_to_dict(self):
        entry = EnhancedLoadEntry(
            member_id="dev-1",
            member_name="Dev 1",
            open_tickets=3,
            role="developer",
        )
        d = entry.to_dict()
        assert d == {
            "member_id": "dev-1",
            "member_name": "Dev 1",
            "open_tickets": 3,
            "role": "developer",
        }


class TestAuditEvent:
    def test_to_dict_and_from_dict_round_trip(self):
        event = AuditEvent(
            timestamp="2026-04-14T00:00:00+00:00",
            action=AuditAction.TICKET_DETECTED,
            actor="system",
            ticket_number="100",
            source_id="s1",
            details={"total": 5},
        )
        d = event.to_dict()
        assert d["action"] == "ticket_detected"
        assert d["actor"] == "system"
        assert d["details"] == {"total": 5}

        restored = AuditEvent.from_dict(d)
        assert restored.action == AuditAction.TICKET_DETECTED
        assert restored.event_id == event.event_id
        assert restored.timestamp == event.timestamp
        assert restored.ticket_number == "100"
        assert restored.source_id == "s1"
        assert restored.details == {"total": 5}

    def test_event_id_auto_generated(self):
        e1 = AuditEvent(timestamp="t1", action=AuditAction.BASELINE_CREATED, actor="system")
        e2 = AuditEvent(timestamp="t2", action=AuditAction.BASELINE_CREATED, actor="system")
        assert e1.event_id != e2.event_id
