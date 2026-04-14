"""Unit tests for NotifyAssignmentUseCase."""
from __future__ import annotations

import logging

from src.megahub_monitor.application.use_cases.notify_assignment import NotifyAssignmentUseCase
from src.megahub_monitor.domain.enums import TicketWorkflowState
from src.megahub_monitor.domain.models import TeamMember, Ticket, WorkflowItem
from tests.fakes.fake_notifier import FakeNotifier
from tests.fakes.fake_state_repository import FakeStateRepository


def _make_ticket(number: str = "T-001", source_id: str = "src1") -> Ticket:
    return Ticket(
        number=number, source_id=source_id,
        source_name="Fila", source_kind="fila",
        raw_fields={},
    )


def _make_member(
    mid: str = "dev1",
    name: str = "Alice",
    webhook: str = "https://hook.example.com/dev1",
    active: bool = True,
) -> TeamMember:
    return TeamMember(
        id=mid, name=name, role="developer",
        skills=[], active=active, webhook_url=webhook, max_concurrent_tickets=5,
    )


def _make_workflow_item(
    ticket_number: str, source_id: str, state: TicketWorkflowState
) -> WorkflowItem:
    return WorkflowItem(
        ticket_number=ticket_number,
        source_id=source_id,
        current_state=state,
        detected_at="2024-01-01T00:00:00",
        last_state_change_at="2024-01-01T00:00:00",
    )


def _make_use_case(repo: FakeStateRepository | None = None) -> tuple[NotifyAssignmentUseCase, FakeStateRepository]:
    repo = repo or FakeStateRepository()
    uc = NotifyAssignmentUseCase(
        repository=repo,
        logger=logging.getLogger("test"),
    )
    return uc, repo


class TestWithWebhook:
    def test_returns_notification_result(self):
        uc, repo = _make_use_case()
        ticket = _make_ticket()
        member = _make_member()
        notifier = FakeNotifier(success=True)

        result = uc.execute(ticket, member, notifier)

        assert result is not None
        assert result.success is True

    def test_calls_send_assignment_notice(self):
        uc, repo = _make_use_case()
        ticket = _make_ticket()
        member = _make_member()
        notifier = FakeNotifier()

        uc.execute(ticket, member, notifier)

        assert len(notifier.sent) == 1
        assert notifier.sent[0]["method"] == "send_assignment_notice"
        assert notifier.sent[0]["developer_name"] == "Alice"
        assert notifier.sent[0]["ticket_number"] == "T-001"

    def test_transitions_workflow_to_assigned(self):
        repo = FakeStateRepository()
        repo.upsert_workflow_item(
            _make_workflow_item("T-001", "src1", TicketWorkflowState.ALLOCATION_APPROVED)
        )
        uc, _ = _make_use_case(repo)
        notifier = FakeNotifier()

        uc.execute(_make_ticket(), _make_member(), notifier)

        item = repo.get_workflow_item("T-001", "src1")
        assert item.current_state == TicketWorkflowState.ASSIGNED

    def test_audit_event_logged(self):
        uc, repo = _make_use_case()
        notifier = FakeNotifier()

        uc.execute(_make_ticket(), _make_member(), notifier)

        assert len(repo._audit_events) == 1
        from src.megahub_monitor.domain.enums import AuditAction
        assert repo._audit_events[0].action == AuditAction.DEVELOPER_NOTIFIED

    def test_audit_details_include_member_info(self):
        uc, repo = _make_use_case()
        notifier = FakeNotifier()

        uc.execute(_make_ticket("T-42"), _make_member("dev99", "Bob"), notifier)

        event = repo._audit_events[0]
        assert event.details["member_id"] == "dev99"
        assert event.details["member_name"] == "Bob"


class TestWithoutWebhook:
    def test_returns_none_when_no_webhook(self):
        uc, _ = _make_use_case()
        member = _make_member(webhook="")
        notifier = FakeNotifier()

        result = uc.execute(_make_ticket(), member, notifier)

        assert result is None

    def test_does_not_call_notifier_when_no_webhook(self):
        uc, _ = _make_use_case()
        member = _make_member(webhook="")
        notifier = FakeNotifier()

        uc.execute(_make_ticket(), member, notifier)

        assert notifier.sent == []

    def test_still_transitions_workflow_without_webhook(self):
        repo = FakeStateRepository()
        repo.upsert_workflow_item(
            _make_workflow_item("T-001", "src1", TicketWorkflowState.ALLOCATION_APPROVED)
        )
        uc, _ = _make_use_case(repo)
        member = _make_member(webhook="")
        notifier = FakeNotifier()

        uc.execute(_make_ticket(), member, notifier)

        item = repo.get_workflow_item("T-001", "src1")
        assert item.current_state == TicketWorkflowState.ASSIGNED

    def test_still_logs_audit_without_webhook(self):
        uc, repo = _make_use_case()
        member = _make_member(webhook="")
        notifier = FakeNotifier()

        uc.execute(_make_ticket(), member, notifier)

        assert len(repo._audit_events) == 1


class TestWorkflowEdgeCases:
    def test_no_workflow_item_does_not_crash(self):
        uc, repo = _make_use_case()
        notifier = FakeNotifier()

        result = uc.execute(_make_ticket(), _make_member(), notifier)

        assert result is not None  # notification still sent

    def test_failed_notification_returns_failure_result(self):
        uc, _ = _make_use_case()
        notifier = FakeNotifier(success=False)

        result = uc.execute(_make_ticket(), _make_member(), notifier)

        assert result is not None
        assert result.success is False
