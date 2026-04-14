"""Unit tests for DetectCompletionUseCase."""
from __future__ import annotations

import logging

from src.megahub_monitor.application.use_cases.detect_completion import DetectCompletionUseCase
from src.megahub_monitor.domain.enums import TicketWorkflowState
from src.megahub_monitor.domain.models import Ticket, WorkflowItem
from tests.fakes.fake_state_repository import FakeStateRepository


def _make_settings(completion_labels=None):
    from unittest.mock import MagicMock
    s = MagicMock()
    s.completion_status_labels = ["Fechado", "Resolvido", "Cancelado"] if completion_labels is None else completion_labels
    return s


def _make_ticket(number: str, source_id: str = "src1", status: str = "NOVO") -> Ticket:
    return Ticket(
        number=number, source_id=source_id,
        source_name="Fila", source_kind="fila",
        ticket_status=status, raw_fields={},
    )


def _make_workflow_item(
    number: str,
    source_id: str = "src1",
    state: TicketWorkflowState = TicketWorkflowState.ASSIGNED,
    approved_member_id: str | None = None,
) -> WorkflowItem:
    item = WorkflowItem(
        ticket_number=number, source_id=source_id,
        current_state=state,
        detected_at="2024-01-01T00:00:00",
        last_state_change_at="2024-01-01T00:00:00",
    )
    item.approved_member_id = approved_member_id
    return item


def _make_use_case(repo=None, completion_labels=None):
    repo = repo or FakeStateRepository()
    uc = DetectCompletionUseCase(
        repository=repo,
        settings=_make_settings(completion_labels),
        logger=logging.getLogger("test"),
    )
    return uc, repo


class TestDetectsCompletions:
    def test_returns_pair_for_completed_ticket(self):
        repo = FakeStateRepository()
        repo.upsert_workflow_item(_make_workflow_item("T-1", state=TicketWorkflowState.ASSIGNED))
        uc, _ = _make_use_case(repo)

        tickets = [_make_ticket("T-1", status="Fechado")]
        result = uc.execute("src1", tickets, "2024-01-02T00:00:00")

        assert len(result) == 1
        item, ticket = result[0]
        assert item.ticket_number == "T-1"
        assert ticket.number == "T-1"

    def test_workflow_transitions_to_completed(self):
        repo = FakeStateRepository()
        repo.upsert_workflow_item(_make_workflow_item("T-1", state=TicketWorkflowState.ASSIGNED))
        uc, _ = _make_use_case(repo)

        uc.execute("src1", [_make_ticket("T-1", status="Resolvido")], "2024-01-02T00:00:00")

        item = repo.get_workflow_item("T-1", "src1")
        assert item.current_state == TicketWorkflowState.COMPLETED

    def test_detects_in_progress_ticket(self):
        repo = FakeStateRepository()
        repo.upsert_workflow_item(_make_workflow_item("T-2", state=TicketWorkflowState.IN_PROGRESS))
        uc, _ = _make_use_case(repo)

        result = uc.execute("src1", [_make_ticket("T-2", status="Fechado")], "2024-01-02T00:00:00")

        assert len(result) == 1
        assert result[0][0].current_state == TicketWorkflowState.COMPLETED

    def test_audit_event_logged(self):
        repo = FakeStateRepository()
        repo.upsert_workflow_item(_make_workflow_item("T-1"))
        uc, _ = _make_use_case(repo)

        uc.execute("src1", [_make_ticket("T-1", status="Fechado")], "2024-01-02T00:00:00")

        from src.megahub_monitor.domain.enums import AuditAction
        assert any(e.action == AuditAction.COMPLETION_DETECTED for e in repo._audit_events)

    def test_completion_status_case_insensitive(self):
        repo = FakeStateRepository()
        repo.upsert_workflow_item(_make_workflow_item("T-1"))
        uc, _ = _make_use_case(repo, completion_labels=["fechado"])

        result = uc.execute("src1", [_make_ticket("T-1", status="FECHADO")], "2024-01-02T00:00:00")

        assert len(result) == 1

    def test_multiple_completions(self):
        repo = FakeStateRepository()
        for n in ["T-1", "T-2", "T-3"]:
            repo.upsert_workflow_item(_make_workflow_item(n))
        uc, _ = _make_use_case(repo)

        tickets = [
            _make_ticket("T-1", status="Fechado"),
            _make_ticket("T-2", status="Resolvido"),
            _make_ticket("T-3", status="NOVO"),  # not completed
        ]
        result = uc.execute("src1", tickets, "2024-01-02T00:00:00")

        assert len(result) == 2
        numbers = {item.ticket_number for item, _ in result}
        assert numbers == {"T-1", "T-2"}


class TestNoCompletions:
    def test_ticket_not_in_completion_status(self):
        repo = FakeStateRepository()
        repo.upsert_workflow_item(_make_workflow_item("T-1"))
        uc, _ = _make_use_case(repo)

        result = uc.execute("src1", [_make_ticket("T-1", status="EM ATENDIMENTO")], "2024-01-02T00:00:00")

        assert result == []

    def test_ticket_not_in_snapshot(self):
        repo = FakeStateRepository()
        repo.upsert_workflow_item(_make_workflow_item("T-1"))
        uc, _ = _make_use_case(repo)

        result = uc.execute("src1", [], "2024-01-02T00:00:00")

        assert result == []

    def test_no_tracked_items(self):
        uc, _ = _make_use_case()

        result = uc.execute("src1", [_make_ticket("T-1", status="Fechado")], "2024-01-02T00:00:00")

        assert result == []

    def test_empty_completion_labels(self):
        repo = FakeStateRepository()
        repo.upsert_workflow_item(_make_workflow_item("T-1"))
        uc, _ = _make_use_case(repo, completion_labels=[])

        result = uc.execute("src1", [_make_ticket("T-1", status="Fechado")], "2024-01-02T00:00:00")

        assert result == []


class TestSourceFiltering:
    def test_only_detects_for_given_source(self):
        repo = FakeStateRepository()
        repo.upsert_workflow_item(_make_workflow_item("T-1", source_id="src-A"))
        repo.upsert_workflow_item(_make_workflow_item("T-2", source_id="src-B"))
        uc, _ = _make_use_case(repo)

        tickets = [_make_ticket("T-1", "src-A", "Fechado"), _make_ticket("T-2", "src-B", "Fechado")]
        # Only execute for src-A
        result = uc.execute("src-A", tickets, "2024-01-02T00:00:00")

        assert len(result) == 1
        assert result[0][0].source_id == "src-A"


class TestWorkflowStateFiltering:
    def test_does_not_process_detected_state(self):
        repo = FakeStateRepository()
        repo.upsert_workflow_item(_make_workflow_item("T-1", state=TicketWorkflowState.DETECTED))
        uc, _ = _make_use_case(repo)

        result = uc.execute("src1", [_make_ticket("T-1", status="Fechado")], "2024-01-02T00:00:00")

        assert result == []
        item = repo.get_workflow_item("T-1", "src1")
        assert item.current_state == TicketWorkflowState.DETECTED

    def test_does_not_process_already_completed(self):
        repo = FakeStateRepository()
        # Can't create COMPLETED state through _make_workflow_item directly,
        # transition from ASSIGNED to COMPLETED first
        item = _make_workflow_item("T-1", state=TicketWorkflowState.ASSIGNED)
        item.transition_to(TicketWorkflowState.COMPLETED, "2024-01-01T00:00:00")
        repo.upsert_workflow_item(item)
        uc, _ = _make_use_case(repo)

        result = uc.execute("src1", [_make_ticket("T-1", status="Fechado")], "2024-01-02T00:00:00")

        assert result == []
