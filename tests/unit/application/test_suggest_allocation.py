"""Unit tests for SuggestAllocationUseCase."""
from __future__ import annotations

import logging

from src.megahub_monitor.application.services.allocation_engine import AllocationEngine
from src.megahub_monitor.application.use_cases.suggest_allocation import SuggestAllocationUseCase
from src.megahub_monitor.domain.enums import TicketWorkflowState
from src.megahub_monitor.domain.models import TeamMember
from tests.fakes.fake_state_repository import FakeStateRepository


def _member(mid: str, name: str, skills: list[str] | None = None) -> TeamMember:
    return TeamMember(
        id=mid, name=name, role="developer",
        skills=[s.lower() for s in (skills or [])],
        active=True, webhook_url="", max_concurrent_tickets=5,
    )


def _make_uc(repo=None):
    if repo is None:
        repo = FakeStateRepository()
    uc = SuggestAllocationUseCase(
        repository=repo,
        engine=AllocationEngine(),
        logger=logging.getLogger("test"),
        max_suggestions=3,
    )
    return uc, repo


class TestSuggestAllocation:
    def test_returns_suggestions(self, make_ticket):
        uc, _ = _make_uc()
        members = [_member("a", "Alice", ["abap"]), _member("b", "Bob")]
        ticket = make_ticket(front="abap")
        result = uc.execute(ticket, members, {})
        assert len(result) >= 1
        assert result[0].member_id == "a"

    def test_creates_workflow_item(self, make_ticket):
        uc, repo = _make_uc()
        ticket = make_ticket(number="42")
        uc.execute(ticket, [_member("a", "Alice")], {})
        item = repo.get_workflow_item("42", ticket.source_id)
        assert item is not None
        assert item.current_state == TicketWorkflowState.ALLOCATION_SUGGESTED

    def test_workflow_item_has_suggested_member_ids(self, make_ticket):
        uc, repo = _make_uc()
        members = [_member("a", "Alice"), _member("b", "Bob")]
        ticket = make_ticket(number="42")
        uc.execute(ticket, members, {})
        item = repo.get_workflow_item("42", ticket.source_id)
        assert "a" in item.suggested_member_ids or "b" in item.suggested_member_ids

    def test_saves_pending_approval(self, make_ticket):
        uc, repo = _make_uc()
        ticket = make_ticket(number="42")
        uc.execute(ticket, [_member("a", "Alice")], {})
        pending = repo.get_pending_approvals()
        assert len(pending) == 1
        assert pending[0]["ticket_number"] == "42"

    def test_records_audit_event(self, make_ticket):
        uc, repo = _make_uc()
        ticket = make_ticket(number="42")
        uc.execute(ticket, [_member("a", "Alice")], {})
        trail = repo.get_audit_trail("42")
        assert len(trail) == 1
        from src.megahub_monitor.domain.enums import AuditAction
        assert trail[0].action == AuditAction.ALLOCATION_SUGGESTED

    def test_empty_members_returns_empty(self, make_ticket):
        uc, _ = _make_uc()
        result = uc.execute(make_ticket(), [], {})
        assert result == []

    def test_idempotent_second_suggest_skips_transition(self, make_ticket):
        """Calling execute twice does not crash — transition guard handles it."""
        uc, repo = _make_uc()
        ticket = make_ticket(number="42")
        uc.execute(ticket, [_member("a", "Alice")], {})
        # Second call — item already in ALLOCATION_SUGGESTED
        uc.execute(ticket, [_member("a", "Alice")], {})
        item = repo.get_workflow_item("42", ticket.source_id)
        assert item.current_state == TicketWorkflowState.ALLOCATION_SUGGESTED
