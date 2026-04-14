"""Unit tests for DetectStatusReturnUseCase."""
from __future__ import annotations

import logging

from src.megahub_monitor.application.use_cases.detect_status_return import DetectStatusReturnUseCase
from src.megahub_monitor.domain.enums import AuditAction, TicketWorkflowState
from src.megahub_monitor.domain.models import Ticket, WorkflowItem
from tests.fakes.fake_state_repository import FakeStateRepository


def _make_settings(return_labels=None):
    from unittest.mock import MagicMock
    s = MagicMock()
    s.return_to_developer_labels = ["Em Processamento"] if return_labels is None else return_labels
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
    approved_member_id: str | None = "dev-1",
    last_known_itsm_status: str = "",
) -> WorkflowItem:
    item = WorkflowItem(
        ticket_number=number, source_id=source_id,
        current_state=state,
        detected_at="2024-01-01T00:00:00",
        last_state_change_at="2024-01-01T00:00:00",
    )
    item.approved_member_id = approved_member_id
    item.last_known_itsm_status = last_known_itsm_status
    return item


def _make_use_case(repo=None, return_labels=None):
    repo = repo or FakeStateRepository()
    uc = DetectStatusReturnUseCase(
        repository=repo,
        settings=_make_settings(return_labels),
        logger=logging.getLogger("test"),
    )
    return uc, repo


class TestDetectsReturn:
    def test_returns_pair_when_status_matches(self):
        repo = FakeStateRepository()
        repo.upsert_workflow_item(_make_workflow_item("T-1", state=TicketWorkflowState.ASSIGNED))
        uc, _ = _make_use_case(repo)

        result = uc.execute("src1", [_make_ticket("T-1", status="Em Processamento")], "2024-01-02T00:00:00")

        assert len(result) == 1
        item, ticket = result[0]
        assert item.ticket_number == "T-1"
        assert ticket.number == "T-1"

    def test_detects_in_progress_state(self):
        repo = FakeStateRepository()
        repo.upsert_workflow_item(_make_workflow_item("T-1", state=TicketWorkflowState.IN_PROGRESS))
        uc, _ = _make_use_case(repo)

        result = uc.execute("src1", [_make_ticket("T-1", status="Em Processamento")], "2024-01-02T00:00:00")

        assert len(result) == 1

    def test_does_not_change_workflow_state(self):
        """Return detection must NOT transition the WorkflowItem state."""
        repo = FakeStateRepository()
        repo.upsert_workflow_item(_make_workflow_item("T-1", state=TicketWorkflowState.ASSIGNED))
        uc, _ = _make_use_case(repo)

        uc.execute("src1", [_make_ticket("T-1", status="Em Processamento")], "2024-01-02T00:00:00")

        item = repo.get_workflow_item("T-1", "src1")
        assert item.current_state == TicketWorkflowState.ASSIGNED

    def test_updates_last_known_itsm_status(self):
        repo = FakeStateRepository()
        repo.upsert_workflow_item(_make_workflow_item("T-1"))
        uc, _ = _make_use_case(repo)

        uc.execute("src1", [_make_ticket("T-1", status="Em Processamento")], "2024-01-02T00:00:00")

        item = repo.get_workflow_item("T-1", "src1")
        assert item.last_known_itsm_status == "Em Processamento"

    def test_audit_event_logged(self):
        repo = FakeStateRepository()
        repo.upsert_workflow_item(_make_workflow_item("T-1"))
        uc, _ = _make_use_case(repo)

        uc.execute("src1", [_make_ticket("T-1", status="Em Processamento")], "2024-01-02T00:00:00")

        assert any(e.action == AuditAction.TICKET_RETURNED for e in repo._audit_events)

    def test_status_match_case_insensitive(self):
        repo = FakeStateRepository()
        repo.upsert_workflow_item(_make_workflow_item("T-1"))
        uc, _ = _make_use_case(repo, return_labels=["em processamento"])

        result = uc.execute("src1", [_make_ticket("T-1", status="EM PROCESSAMENTO")], "2024-01-02T00:00:00")

        assert len(result) == 1


class TestNoReturn:
    def test_status_not_in_return_labels(self):
        repo = FakeStateRepository()
        repo.upsert_workflow_item(_make_workflow_item("T-1"))
        uc, _ = _make_use_case(repo)

        result = uc.execute("src1", [_make_ticket("T-1", status="Atribuido")], "2024-01-02T00:00:00")

        assert result == []

    def test_no_tracked_items(self):
        uc, _ = _make_use_case()

        result = uc.execute("src1", [_make_ticket("T-1", status="Em Processamento")], "2024-01-02T00:00:00")

        assert result == []

    def test_ticket_not_in_snapshot(self):
        repo = FakeStateRepository()
        repo.upsert_workflow_item(_make_workflow_item("T-1"))
        uc, _ = _make_use_case(repo)

        result = uc.execute("src1", [], "2024-01-02T00:00:00")

        assert result == []

    def test_empty_return_labels(self):
        repo = FakeStateRepository()
        repo.upsert_workflow_item(_make_workflow_item("T-1"))
        uc, _ = _make_use_case(repo, return_labels=[])

        result = uc.execute("src1", [_make_ticket("T-1", status="Em Processamento")], "2024-01-02T00:00:00")

        assert result == []

    def test_no_duplicate_notification_same_status(self):
        """Se o status já estava salvo, não renotifica."""
        repo = FakeStateRepository()
        repo.upsert_workflow_item(
            _make_workflow_item("T-1", last_known_itsm_status="Em Processamento")
        )
        uc, _ = _make_use_case(repo)

        result = uc.execute("src1", [_make_ticket("T-1", status="Em Processamento")], "2024-01-02T00:00:00")

        assert result == []


class TestSourceFiltering:
    def test_only_detects_for_given_source(self):
        repo = FakeStateRepository()
        repo.upsert_workflow_item(_make_workflow_item("T-1", source_id="src-A"))
        repo.upsert_workflow_item(_make_workflow_item("T-2", source_id="src-B"))
        uc, _ = _make_use_case(repo)

        tickets = [
            _make_ticket("T-1", "src-A", "Em Processamento"),
            _make_ticket("T-2", "src-B", "Em Processamento"),
        ]
        result = uc.execute("src-A", tickets, "2024-01-02T00:00:00")

        assert len(result) == 1
        assert result[0][0].source_id == "src-A"

    def test_detected_state_not_tracked(self):
        repo = FakeStateRepository()
        repo.upsert_workflow_item(_make_workflow_item("T-1", state=TicketWorkflowState.DETECTED))
        uc, _ = _make_use_case(repo)

        result = uc.execute("src1", [_make_ticket("T-1", status="Em Processamento")], "2024-01-02T00:00:00")

        assert result == []
