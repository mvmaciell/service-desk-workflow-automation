"""Unit tests for ProcessApprovalUseCase."""
from __future__ import annotations

import logging

import pytest

from src.megahub_monitor.application.use_cases.process_approval import (
    ApprovalError,
    ProcessApprovalUseCase,
)
from src.megahub_monitor.domain.enums import TicketWorkflowState
from src.megahub_monitor.domain.models import TeamMember, Ticket, WorkflowItem
from tests.fakes.fake_state_repository import FakeStateRepository
from tests.fakes.fake_team_catalog import FakeTeamCatalog


def _make_member(mid: str, name: str, active: bool = True, role: str = "developer") -> TeamMember:
    return TeamMember(
        id=mid, name=name, role=role,
        skills=[], active=active, webhook_url="", max_concurrent_tickets=5,
    )


def _make_ticket(number: str = "T-001", source_id: str = "src1") -> Ticket:
    return Ticket(
        number=number, source_id=source_id,
        source_name="Fila", source_kind="fila",
        ticket_status="NOVO",
        raw_fields={},
    )


def _pending_approval(ticket_number: str, source_id: str, member_id: str = "dev1") -> dict:
    return {
        "ticket_number": ticket_number,
        "source_id": source_id,
        "request_id": "req-1",
        "suggestions": [],
        "resolved_at": None,
    }


def _make_workflow_item(ticket_number: str, source_id: str, state: TicketWorkflowState) -> WorkflowItem:
    return WorkflowItem(
        ticket_number=ticket_number,
        source_id=source_id,
        current_state=state,
        detected_at="2024-01-01T00:00:00",
        last_state_change_at="2024-01-01T00:00:00",
    )


def _make_use_case(
    repo: FakeStateRepository | None = None,
    catalog: FakeTeamCatalog | None = None,
) -> tuple[ProcessApprovalUseCase, FakeStateRepository, FakeTeamCatalog]:
    repo = repo or FakeStateRepository()
    catalog = catalog or FakeTeamCatalog()
    uc = ProcessApprovalUseCase(
        repository=repo,
        team_catalog=catalog,
        logger=logging.getLogger("test"),
    )
    return uc, repo, catalog


class TestHappyPath:
    def test_returns_chosen_member(self):
        repo = FakeStateRepository()
        repo._pending_approvals.append(_pending_approval("T-1", "src1", "dev1"))
        catalog = FakeTeamCatalog([_make_member("dev1", "Alice")])

        uc, _, _ = _make_use_case(repo, catalog)
        member = uc.execute("T-1", "src1", "dev1")

        assert member.id == "dev1"
        assert member.name == "Alice"

    def test_marks_approval_received(self):
        repo = FakeStateRepository()
        repo._pending_approvals.append(_pending_approval("T-1", "src1", "dev1"))
        catalog = FakeTeamCatalog([_make_member("dev1", "Alice")])

        uc, _, _ = _make_use_case(repo, catalog)
        uc.execute("T-1", "src1", "dev1")

        resolved = [a for a in repo._pending_approvals if a.get("resolved_at")]
        assert len(resolved) == 1
        assert resolved[0]["chosen_member_id"] == "dev1"

    def test_workflow_transitions_to_approved(self):
        repo = FakeStateRepository()
        repo._pending_approvals.append(_pending_approval("T-1", "src1"))
        repo.upsert_workflow_item(
            _make_workflow_item("T-1", "src1", TicketWorkflowState.ALLOCATION_SUGGESTED)
        )
        catalog = FakeTeamCatalog([_make_member("dev1", "Alice")])

        uc, _, _ = _make_use_case(repo, catalog)
        uc.execute("T-1", "src1", "dev1")

        item = repo.get_workflow_item("T-1", "src1")
        assert item.current_state == TicketWorkflowState.ALLOCATION_APPROVED
        assert item.approved_member_id == "dev1"

    def test_audit_event_logged(self):
        repo = FakeStateRepository()
        repo._pending_approvals.append(_pending_approval("T-1", "src1"))
        catalog = FakeTeamCatalog([_make_member("dev1", "Alice")])

        uc, _, _ = _make_use_case(repo, catalog)
        uc.execute("T-1", "src1", "dev1")

        assert len(repo._audit_events) == 1
        from src.megahub_monitor.domain.enums import AuditAction
        assert repo._audit_events[0].action == AuditAction.ALLOCATION_APPROVED

    def test_approved_by_default_coordinator(self):
        from src.megahub_monitor.domain.enums import AuditAction

        repo = FakeStateRepository()
        repo._pending_approvals.append(_pending_approval("T-1", "src1"))
        catalog = FakeTeamCatalog([_make_member("dev1", "Alice")])

        uc, _, _ = _make_use_case(repo, catalog)
        uc.execute("T-1", "src1", "dev1")

        event = repo._audit_events[0]
        assert event.actor == "coordinator"

    def test_custom_approved_by(self):
        repo = FakeStateRepository()
        repo._pending_approvals.append(_pending_approval("T-1", "src1"))
        catalog = FakeTeamCatalog([_make_member("dev1", "Alice")])

        uc, _, _ = _make_use_case(repo, catalog)
        uc.execute("T-1", "src1", "dev1", approved_by="mgr-joao")

        assert repo._audit_events[0].actor == "mgr-joao"


class TestErrors:
    def test_no_pending_approval_raises(self):
        catalog = FakeTeamCatalog([_make_member("dev1", "Alice")])
        uc, _, _ = _make_use_case(catalog=catalog)

        with pytest.raises(ApprovalError, match="Nenhuma aprovacao pendente"):
            uc.execute("T-999", "src1", "dev1")

    def test_pending_for_different_ticket_raises(self):
        repo = FakeStateRepository()
        repo._pending_approvals.append(_pending_approval("T-2", "src1"))
        catalog = FakeTeamCatalog([_make_member("dev1", "Alice")])

        uc, _, _ = _make_use_case(repo, catalog)
        with pytest.raises(ApprovalError):
            uc.execute("T-1", "src1", "dev1")

    def test_pending_for_different_source_raises(self):
        repo = FakeStateRepository()
        repo._pending_approvals.append(_pending_approval("T-1", "other-src"))
        catalog = FakeTeamCatalog([_make_member("dev1", "Alice")])

        uc, _, _ = _make_use_case(repo, catalog)
        with pytest.raises(ApprovalError):
            uc.execute("T-1", "src1", "dev1")

    def test_member_not_found_raises(self):
        repo = FakeStateRepository()
        repo._pending_approvals.append(_pending_approval("T-1", "src1"))
        catalog = FakeTeamCatalog()  # empty catalog

        uc, _, _ = _make_use_case(repo, catalog)
        with pytest.raises(ApprovalError, match="nao encontrado"):
            uc.execute("T-1", "src1", "unknown-dev")

    def test_inactive_member_raises(self):
        repo = FakeStateRepository()
        repo._pending_approvals.append(_pending_approval("T-1", "src1"))
        catalog = FakeTeamCatalog([_make_member("dev1", "Alice", active=False)])

        uc, _, _ = _make_use_case(repo, catalog)
        with pytest.raises(ApprovalError, match="inativo"):
            uc.execute("T-1", "src1", "dev1")

    def test_already_resolved_approval_raises(self):
        repo = FakeStateRepository()
        approval = _pending_approval("T-1", "src1")
        approval["resolved_at"] = "2024-01-01T00:00:00"  # already resolved
        repo._pending_approvals.append(approval)
        catalog = FakeTeamCatalog([_make_member("dev1", "Alice")])

        uc, _, _ = _make_use_case(repo, catalog)
        with pytest.raises(ApprovalError):
            uc.execute("T-1", "src1", "dev1")


class TestWorkflowEdgeCases:
    def test_no_workflow_item_does_not_crash(self):
        repo = FakeStateRepository()
        repo._pending_approvals.append(_pending_approval("T-1", "src1"))
        catalog = FakeTeamCatalog([_make_member("dev1", "Alice")])

        uc, _, _ = _make_use_case(repo, catalog)
        member = uc.execute("T-1", "src1", "dev1")

        assert member.id == "dev1"
        # workflow item was not pre-created, no crash expected

    def test_workflow_item_in_wrong_state_not_transitioned(self):
        repo = FakeStateRepository()
        repo._pending_approvals.append(_pending_approval("T-1", "src1"))
        # Already in ASSIGNED — can't go back to ALLOCATION_APPROVED
        repo.upsert_workflow_item(
            _make_workflow_item("T-1", "src1", TicketWorkflowState.ASSIGNED)
        )
        catalog = FakeTeamCatalog([_make_member("dev1", "Alice")])

        uc, _, _ = _make_use_case(repo, catalog)
        uc.execute("T-1", "src1", "dev1")

        item = repo.get_workflow_item("T-1", "src1")
        # State should remain ASSIGNED (transition refused)
        assert item.current_state == TicketWorkflowState.ASSIGNED
