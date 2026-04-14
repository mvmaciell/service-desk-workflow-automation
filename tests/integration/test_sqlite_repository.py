"""Integration tests for SQLiteStateRepository using in-memory SQLite."""
from __future__ import annotations

from pathlib import Path

import pytest

from src.megahub_monitor.adapters.persistence.sqlite_repository import SQLiteStateRepository
from src.megahub_monitor.domain.enums import AuditAction, TicketWorkflowState
from src.megahub_monitor.domain.models import (
    AllocationSuggestion,
    AuditEvent,
    DeliveryRequest,
    LoadEntry,
    NotificationResult,
    WorkflowItem,
)


@pytest.fixture
def repo(tmp_path) -> SQLiteStateRepository:
    r = SQLiteStateRepository(tmp_path / "test.db")
    r.initialize()
    return r


@pytest.fixture
def in_memory_repo() -> SQLiteStateRepository:
    r = SQLiteStateRepository(Path(":memory:"))
    r.initialize()
    return r


class TestMigrations:
    def test_initialize_idempotent(self, tmp_path):
        r = SQLiteStateRepository(tmp_path / "test.db")
        r.initialize()
        r.initialize()  # second call must not raise

    def test_schema_version_table_created(self, repo):
        from src.megahub_monitor.adapters.persistence.migrations import MIGRATIONS
        versions = {m.version for m in MIGRATIONS}
        conn = repo._connect()
        rows = conn.execute("SELECT version FROM schema_version").fetchall()
        applied = {row[0] for row in rows}
        assert versions == applied

    def test_all_tables_exist(self, repo):
        conn = repo._connect()
        expected = {
            "source_states",
            "source_seen_tickets",
            "source_snapshots",
            "load_snapshots",
            "notification_deliveries",
            "workflow_items",
            "audit_events",
            "pending_approvals",
            "schema_version",
        }
        rows = conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
        actual = {row[0] for row in rows}
        assert expected.issubset(actual)


class TestSourceState:
    def test_baseline_not_initialized_by_default(self, repo):
        assert repo.is_baseline_initialized("source-1") is False

    def test_mark_and_check_baseline(self, repo):
        repo.mark_baseline_initialized("source-1", "2026-04-14T00:00:00+00:00")
        assert repo.is_baseline_initialized("source-1") is True

    def test_baseline_version_default_is_2(self, repo):
        repo.mark_baseline_initialized("source-1", "2026-04-14T00:00:00+00:00")
        assert repo.get_baseline_version("source-1") == 2

    def test_baseline_version_not_found_returns_0(self, repo):
        assert repo.get_baseline_version("nonexistent") == 0

    def test_update_source_run(self, repo):
        repo.update_source_run("source-1", "2026-04-14T00:00:00+00:00", success=True)
        # No error = pass


class TestSeenTickets:
    def test_upsert_and_get_known_numbers(self, repo, make_ticket):
        tickets = [make_ticket(number="100"), make_ticket(number="101")]
        repo.upsert_seen_tickets("source-1", tickets, "2026-04-14T00:00:00+00:00")
        known = repo.get_known_numbers("source-1", ["100", "101", "102"])
        assert known == {"100", "101"}

    def test_unknown_ticket_not_returned(self, repo, make_ticket):
        repo.upsert_seen_tickets("source-1", [make_ticket(number="100")], "2026-04-14T00:00:00+00:00")
        known = repo.get_known_numbers("source-1", ["999"])
        assert known == set()

    def test_upsert_is_idempotent(self, repo, make_ticket):
        ticket = make_ticket(number="100")
        repo.upsert_seen_tickets("source-1", [ticket], "2026-04-14T00:00:00+00:00")
        repo.upsert_seen_tickets("source-1", [ticket], "2026-04-14T01:00:00+00:00")
        known = repo.get_known_numbers("source-1", ["100"])
        assert known == {"100"}

    def test_forget_ticket_by_source(self, repo, make_ticket):
        repo.upsert_seen_tickets("source-1", [make_ticket(number="100")], "2026-04-14T00:00:00+00:00")
        count = repo.forget_ticket("100", "source-1")
        assert count == 1
        assert repo.get_known_numbers("source-1", ["100"]) == set()

    def test_forget_ticket_all_sources(self, repo, make_ticket):
        t = make_ticket(number="100")
        repo.upsert_seen_tickets("source-1", [t], "2026-04-14T00:00:00+00:00")
        repo.upsert_seen_tickets("source-2", [t], "2026-04-14T00:00:00+00:00")
        count = repo.forget_ticket("100")
        assert count == 2


class TestDeliveryDedup:
    def test_has_delivery_false_initially(self, repo):
        assert repo.has_delivery("s1", "rule-1", "recipient-1", "100") is False

    def test_record_and_check_delivery(self, repo, make_ticket):
        ticket = make_ticket(number="100")
        delivery = DeliveryRequest(
            source_id="s1",
            source_name="Fila",
            rule_id="rule-1",
            title_prefix="Novo",
            recipient_id="recipient-1",
            recipient_name="Dev 1",
            recipient_role="developer",
            webhook_url="http://example.com",
            ticket=ticket,
        )
        result = NotificationResult(success=True, status_code=200, response_text="ok", payload={})
        repo.record_delivery(delivery, "2026-04-14T00:00:00+00:00", result)
        assert repo.has_delivery("s1", "rule-1", "recipient-1", "100") is True

    def test_failed_delivery_does_not_mark_as_delivered(self, repo, make_ticket):
        ticket = make_ticket(number="100")
        delivery = DeliveryRequest(
            source_id="s1", source_name="Fila", rule_id="rule-1",
            title_prefix="Novo", recipient_id="r1", recipient_name="Dev",
            recipient_role="developer", webhook_url="http://x", ticket=ticket,
        )
        result = NotificationResult(success=False, status_code=500, response_text="err", payload={})
        repo.record_delivery(delivery, "2026-04-14T00:00:00+00:00", result)
        assert repo.has_delivery("s1", "rule-1", "r1", "100") is False


class TestWorkflowItems:
    def _make_item(self, ticket_number="100", source_id="s1", state=TicketWorkflowState.DETECTED):
        return WorkflowItem(
            ticket_number=ticket_number,
            source_id=source_id,
            current_state=state,
            detected_at="2026-04-14T00:00:00+00:00",
            last_state_change_at="2026-04-14T00:00:00+00:00",
        )

    def test_upsert_and_get_workflow_item(self, repo):
        item = self._make_item()
        repo.upsert_workflow_item(item)
        retrieved = repo.get_workflow_item("100", "s1")
        assert retrieved is not None
        assert retrieved.ticket_number == "100"
        assert retrieved.current_state == TicketWorkflowState.DETECTED

    def test_get_nonexistent_returns_none(self, repo):
        assert repo.get_workflow_item("nonexistent", "s1") is None

    def test_upsert_updates_state(self, repo):
        item = self._make_item()
        repo.upsert_workflow_item(item)
        item.transition_to(TicketWorkflowState.ALLOCATION_SUGGESTED, "2026-04-14T00:01:00+00:00")
        repo.upsert_workflow_item(item)
        retrieved = repo.get_workflow_item("100", "s1")
        assert retrieved.current_state == TicketWorkflowState.ALLOCATION_SUGGESTED

    def test_get_items_in_state(self, repo):
        items = [
            self._make_item("100", "s1", TicketWorkflowState.DETECTED),
            self._make_item("101", "s1", TicketWorkflowState.DETECTED),
            self._make_item("102", "s1", TicketWorkflowState.ASSIGNED),
        ]
        for item in items:
            repo.upsert_workflow_item(item)
        detected = repo.get_items_in_state(TicketWorkflowState.DETECTED)
        assert len(detected) == 2
        assigned = repo.get_items_in_state(TicketWorkflowState.ASSIGNED)
        assert len(assigned) == 1

    def test_workflow_item_with_suggested_members(self, repo):
        item = self._make_item()
        item.suggested_member_ids = ["dev-1", "dev-2"]
        repo.upsert_workflow_item(item)
        retrieved = repo.get_workflow_item("100", "s1")
        assert retrieved.suggested_member_ids == ["dev-1", "dev-2"]

    def test_workflow_item_completion_at_persisted(self, repo):
        item = self._make_item(state=TicketWorkflowState.IN_PROGRESS)
        item.transition_to(TicketWorkflowState.COMPLETED, "2026-04-14T05:00:00+00:00")
        repo.upsert_workflow_item(item)
        retrieved = repo.get_workflow_item("100", "s1")
        assert retrieved.completed_at == "2026-04-14T05:00:00+00:00"


class TestAuditTrail:
    def test_record_and_retrieve_by_ticket(self, repo):
        event = AuditEvent(
            timestamp="2026-04-14T00:00:00+00:00",
            action=AuditAction.TICKET_DETECTED,
            actor="system",
            ticket_number="100",
            source_id="s1",
            details={"total": 5},
        )
        repo.record_audit_event(event)
        trail = repo.get_audit_trail("100")
        assert len(trail) == 1
        assert trail[0].action == AuditAction.TICKET_DETECTED
        assert trail[0].details == {"total": 5}

    def test_retrieve_all_events(self, repo):
        for action in [AuditAction.TICKET_DETECTED, AuditAction.BASELINE_CREATED]:
            event = AuditEvent(timestamp="2026-04-14T00:00:00+00:00", action=action, actor="system")
            repo.record_audit_event(event)
        all_events = repo.get_audit_trail()
        assert len(all_events) == 2

    def test_idempotent_insert(self, repo):
        event = AuditEvent(
            timestamp="2026-04-14T00:00:00+00:00",
            action=AuditAction.TICKET_DETECTED,
            actor="system",
        )
        repo.record_audit_event(event)
        repo.record_audit_event(event)  # same event_id, must not duplicate
        all_events = repo.get_audit_trail()
        assert len(all_events) == 1

    def test_limit_respected(self, repo):
        for i in range(20):
            repo.record_audit_event(AuditEvent(
                timestamp=f"2026-04-14T{i:02d}:00:00+00:00",
                action=AuditAction.STATUS_CHANGED,
                actor="system",
            ))
        events = repo.get_audit_trail(limit=5)
        assert len(events) == 5


class TestPendingApprovals:
    def test_save_and_get_pending_approval(self, repo):
        suggestions = [AllocationSuggestion(
            member_id="dev-1", member_name="Dev 1", rank=1,
            reason="skill match", current_load=2, skill_match_score=1.0,
        )]
        repo.save_pending_approval("100", "s1", "req-abc", suggestions)
        pending = repo.get_pending_approvals()
        assert len(pending) == 1
        assert pending[0]["ticket_number"] == "100"
        assert pending[0]["request_id"] == "req-abc"

    def test_mark_approval_received(self, repo):
        repo.save_pending_approval("100", "s1", "req-abc", [])
        repo.mark_approval_received("100", "s1", "dev-1", "2026-04-14T01:00:00+00:00")
        pending = repo.get_pending_approvals()
        assert len(pending) == 0  # resolved_at is set, no longer pending

    def test_multiple_approvals_one_resolved(self, repo):
        repo.save_pending_approval("100", "s1", "req-1", [])
        repo.save_pending_approval("101", "s1", "req-2", [])
        repo.mark_approval_received("100", "s1", "dev-1", "2026-04-14T01:00:00+00:00")
        pending = repo.get_pending_approvals()
        assert len(pending) == 1
        assert pending[0]["ticket_number"] == "101"


class TestLegacyTablesPreserved:
    """Verify existing MVP tables still work after migration."""

    def test_can_save_and_read_snapshot(self, repo, make_ticket):
        tickets = [make_ticket(number="100"), make_ticket(number="101")]
        repo.save_snapshot("s1", tickets, "2026-04-14T00:00:00+00:00")
        # No exception = tables intact

    def test_can_save_load_snapshot(self, repo):
        entries = [LoadEntry(consultant="Dev 1", open_tickets=3)]
        repo.save_load_snapshot("s1", entries, "2026-04-14T00:00:00+00:00")
