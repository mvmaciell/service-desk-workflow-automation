"""Unit tests for NotifyStatusReturnUseCase."""
from __future__ import annotations

import logging

from src.megahub_monitor.application.use_cases.notify_status_return import NotifyStatusReturnUseCase
from src.megahub_monitor.domain.enums import TicketWorkflowState
from src.megahub_monitor.domain.models import TeamMember, Ticket, WorkflowItem
from tests.fakes.fake_notifier import FakeNotifier
from tests.fakes.fake_team_catalog import FakeTeamCatalog


def _make_developer(webhook: str = "https://hook.example.com/dev") -> TeamMember:
    return TeamMember(
        id="dev-1", name="Desenvolvedor", role="developer",
        skills=[], active=True, webhook_url=webhook, max_concurrent_tickets=5,
    )


def _make_coordinator(webhook: str = "https://hook.example.com/coord") -> TeamMember:
    return TeamMember(
        id="coord-1", name="Coordenador", role="coordinator",
        skills=[], active=True, webhook_url=webhook, max_concurrent_tickets=0,
    )


def _make_ticket(number: str = "T-1", status: str = "Em Processamento") -> Ticket:
    return Ticket(
        number=number, source_id="src1",
        source_name="Fila", source_kind="fila",
        ticket_status=status, raw_fields={},
    )


def _make_workflow_item(
    number: str = "T-1",
    state: TicketWorkflowState = TicketWorkflowState.ASSIGNED,
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


def _make_uc():
    return NotifyStatusReturnUseCase(logger=logging.getLogger("test"))


class TestNotifyReturnToAssignedDeveloper:
    def test_sends_to_developer_webhook(self):
        uc = _make_uc()
        notifier = FakeNotifier(success=True)
        dev = _make_developer(webhook="https://hook/dev")
        catalog = FakeTeamCatalog(members=[dev])

        pairs = [(_make_workflow_item(), _make_ticket())]
        uc.execute(pairs, catalog, notifier)

        assert len(notifier.sent) == 1
        assert notifier.sent[0]["method"] == "send_return_notice"
        assert notifier.sent[0]["ticket_number"] == "T-1"

    def test_sends_with_correct_status(self):
        uc = _make_uc()
        notifier = FakeNotifier(success=True)
        dev = _make_developer()
        catalog = FakeTeamCatalog(members=[dev])

        pairs = [(_make_workflow_item(), _make_ticket(status="Em Processamento"))]
        uc.execute(pairs, catalog, notifier)

        assert notifier.sent[0]["current_status"] == "Em Processamento"

    def test_multiple_tickets(self):
        uc = _make_uc()
        notifier = FakeNotifier(success=True)
        dev = _make_developer()
        catalog = FakeTeamCatalog(members=[dev])

        pairs = [
            (_make_workflow_item("T-1"), _make_ticket("T-1")),
            (_make_workflow_item("T-2"), _make_ticket("T-2")),
        ]
        uc.execute(pairs, catalog, notifier)

        assert len(notifier.sent) == 2

    def test_empty_pairs_does_nothing(self):
        uc = _make_uc()
        notifier = FakeNotifier(success=True)
        catalog = FakeTeamCatalog()

        uc.execute([], catalog, notifier)

        assert notifier.sent == []


class TestFallbackToCoordinator:
    def test_falls_back_to_coordinator_when_dev_has_no_webhook(self):
        uc = _make_uc()
        notifier = FakeNotifier(success=True)
        dev = _make_developer(webhook="")  # no webhook
        coord = _make_coordinator(webhook="https://hook/coord")
        catalog = FakeTeamCatalog(members=[dev, coord])

        pairs = [(_make_workflow_item(approved_member_id="dev-1"), _make_ticket())]
        uc.execute(pairs, catalog, notifier)

        assert len(notifier.sent) == 1
        assert notifier.sent[0]["recipient_name"] == "Coordenador"

    def test_skips_when_no_webhook_available(self):
        uc = _make_uc()
        notifier = FakeNotifier(success=True)
        dev = _make_developer(webhook="")
        coord = _make_coordinator(webhook="")
        catalog = FakeTeamCatalog(members=[dev, coord])

        pairs = [(_make_workflow_item(), _make_ticket())]
        uc.execute(pairs, catalog, notifier)

        assert notifier.sent == []

    def test_skips_when_no_member_and_no_coordinator(self):
        uc = _make_uc()
        notifier = FakeNotifier(success=True)
        catalog = FakeTeamCatalog()

        pairs = [(_make_workflow_item(approved_member_id=None), _make_ticket())]
        uc.execute(pairs, catalog, notifier)

        assert notifier.sent == []


class TestErrorHandling:
    def test_continues_after_notification_failure(self):
        uc = _make_uc()
        notifier = FakeNotifier(success=False)
        dev = _make_developer()
        catalog = FakeTeamCatalog(members=[dev])

        pairs = [
            (_make_workflow_item("T-1"), _make_ticket("T-1")),
            (_make_workflow_item("T-2"), _make_ticket("T-2")),
        ]
        # Should not raise — just log errors
        uc.execute(pairs, catalog, notifier)

        assert len(notifier.sent) == 2  # Both attempted

    def test_handles_exception_from_notifier(self):
        uc = _make_uc()

        class BrokenNotifier:
            def send_return_notice(self, **_):
                raise RuntimeError("network error")

        dev = _make_developer()
        catalog = FakeTeamCatalog(members=[dev])

        pairs = [(_make_workflow_item(), _make_ticket())]
        # Should not raise
        uc.execute(pairs, catalog, BrokenNotifier())
