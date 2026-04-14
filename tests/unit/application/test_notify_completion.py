"""Unit tests for NotifyCompletionUseCase."""
from __future__ import annotations

import logging

from src.megahub_monitor.application.use_cases.notify_completion import NotifyCompletionUseCase
from src.megahub_monitor.domain.enums import TicketWorkflowState
from src.megahub_monitor.domain.models import TeamMember, Ticket, WorkflowItem
from tests.fakes.fake_notifier import FakeNotifier
from tests.fakes.fake_state_repository import FakeStateRepository
from tests.fakes.fake_team_catalog import FakeTeamCatalog


def _make_coordinator(webhook: str = "https://hook.example.com/coord") -> TeamMember:
    return TeamMember(
        id="coord-1", name="Coordenador", role="coordinator",
        skills=[], active=True, webhook_url=webhook, max_concurrent_tickets=0,
    )


def _make_member(mid: str = "dev-1", name: str = "Dev") -> TeamMember:
    return TeamMember(
        id=mid, name=name, role="developer",
        skills=[], active=True, webhook_url="", max_concurrent_tickets=5,
    )


def _make_ticket(number: str = "T-1") -> Ticket:
    return Ticket(
        number=number, source_id="src1",
        source_name="Fila", source_kind="fila",
        ticket_status="Fechado", raw_fields={},
    )


def _make_workflow_item(
    number: str = "T-1",
    state: TicketWorkflowState = TicketWorkflowState.COMPLETED,
    approved_member_id: str | None = "dev-1",
) -> WorkflowItem:
    item = WorkflowItem(
        ticket_number=number, source_id="src1",
        current_state=state,
        detected_at="2024-01-01T00:00:00",
        last_state_change_at="2024-01-02T00:00:00",
    )
    item.approved_member_id = approved_member_id
    return item


def _make_use_case(repo=None):
    repo = repo or FakeStateRepository()
    uc = NotifyCompletionUseCase(repository=repo, logger=logging.getLogger("test"))
    return uc, repo


class TestHappyPath:
    def test_calls_send_completion_notice(self):
        uc, repo = _make_use_case()
        coordinator = _make_coordinator()
        catalog = FakeTeamCatalog([_make_member()])
        notifier = FakeNotifier()

        item = _make_workflow_item()
        repo.upsert_workflow_item(item)
        uc.execute([(item, _make_ticket())], coordinator, catalog, notifier)

        assert len(notifier.sent) == 1
        assert notifier.sent[0]["method"] == "send_completion_notice"
        assert notifier.sent[0]["coordinator_name"] == "Coordenador"

    def test_transitions_to_completion_notified(self):
        uc, repo = _make_use_case()
        coordinator = _make_coordinator()
        catalog = FakeTeamCatalog([_make_member()])
        notifier = FakeNotifier(success=True)

        item = _make_workflow_item()
        repo.upsert_workflow_item(item)
        uc.execute([(item, _make_ticket())], coordinator, catalog, notifier)

        stored = repo.get_workflow_item("T-1", "src1")
        assert stored.current_state == TicketWorkflowState.COMPLETION_NOTIFIED

    def test_audit_event_logged(self):
        uc, repo = _make_use_case()
        coordinator = _make_coordinator()
        catalog = FakeTeamCatalog([_make_member()])
        notifier = FakeNotifier()

        item = _make_workflow_item()
        repo.upsert_workflow_item(item)
        uc.execute([(item, _make_ticket())], coordinator, catalog, notifier)

        from src.megahub_monitor.domain.enums import AuditAction
        assert any(e.action == AuditAction.COMPLETION_NOTIFIED for e in repo._audit_events)

    def test_resolves_developer_name_from_catalog(self):
        uc, repo = _make_use_case()
        coordinator = _make_coordinator()
        catalog = FakeTeamCatalog([_make_member("dev-1", "Alice")])
        notifier = FakeNotifier()

        item = _make_workflow_item(approved_member_id="dev-1")
        repo.upsert_workflow_item(item)
        uc.execute([(item, _make_ticket())], coordinator, catalog, notifier)

        # completed_by should appear in the audit details
        event = repo._audit_events[0]
        assert event.details["completed_by"] == "Alice"

    def test_multiple_tickets_notified(self):
        uc, repo = _make_use_case()
        coordinator = _make_coordinator()
        catalog = FakeTeamCatalog([_make_member()])
        notifier = FakeNotifier()

        pairs = [(
            _make_workflow_item(f"T-{i}"),
            _make_ticket(f"T-{i}"),
        ) for i in range(3)]
        uc.execute(pairs, coordinator, catalog, notifier)

        assert len(notifier.sent) == 3


class TestNoNotification:
    def test_no_coordinator(self):
        uc, repo = _make_use_case()
        notifier = FakeNotifier()
        catalog = FakeTeamCatalog()

        uc.execute([(_make_workflow_item(), _make_ticket())], None, catalog, notifier)

        assert notifier.sent == []

    def test_coordinator_without_webhook(self):
        uc, repo = _make_use_case()
        coordinator = _make_coordinator(webhook="")
        catalog = FakeTeamCatalog()
        notifier = FakeNotifier()

        uc.execute([(_make_workflow_item(), _make_ticket())], coordinator, catalog, notifier)

        assert notifier.sent == []

    def test_empty_pairs(self):
        uc, repo = _make_use_case()
        coordinator = _make_coordinator()
        catalog = FakeTeamCatalog()
        notifier = FakeNotifier()

        uc.execute([], coordinator, catalog, notifier)

        assert notifier.sent == []

    def test_failed_notification_no_state_transition(self):
        uc, repo = _make_use_case()
        coordinator = _make_coordinator()
        catalog = FakeTeamCatalog([_make_member()])
        notifier = FakeNotifier(success=False)

        item = _make_workflow_item()
        repo.upsert_workflow_item(item)
        uc.execute([(item, _make_ticket())], coordinator, catalog, notifier)

        stored = repo.get_workflow_item("T-1", "src1")
        assert stored.current_state == TicketWorkflowState.COMPLETED  # unchanged

    def test_unknown_member_uses_id_as_fallback(self):
        uc, repo = _make_use_case()
        coordinator = _make_coordinator()
        catalog = FakeTeamCatalog()  # empty — member not found
        notifier = FakeNotifier()

        item = _make_workflow_item(approved_member_id="dev-99")
        uc.execute([(item, _make_ticket())], coordinator, catalog, notifier)

        event = repo._audit_events[0]
        assert event.details["completed_by"] == "dev-99"
