from __future__ import annotations

from collections.abc import Iterable
from typing import Any

from src.megahub_monitor.domain.enums import TicketWorkflowState
from src.megahub_monitor.domain.models import (
    AllocationSuggestion,
    AuditEvent,
    DeliveryRequest,
    LoadEntry,
    NotificationResult,
    Ticket,
    WorkflowItem,
)
from src.megahub_monitor.ports.state_repository import StateRepository


class FakeStateRepository(StateRepository):
    def __init__(self) -> None:
        self._baselines: dict[str, str] = {}
        self._baseline_versions: dict[str, int] = {}
        self._source_runs: dict[str, dict[str, str | None]] = {}
        self._seen: dict[str, set[str]] = {}
        self._deliveries: dict[tuple[str, str, str, str], bool] = {}
        self._workflow_items: dict[tuple[str, str], WorkflowItem] = {}
        self._audit_events: list[AuditEvent] = []
        self._pending_approvals: list[dict[str, Any]] = []
        self._snapshots: list[dict[str, Any]] = []
        self._load_snapshots: list[dict[str, Any]] = []

    # --- Source state ---
    def is_baseline_initialized(self, source_id: str) -> bool:
        return source_id in self._baselines

    def mark_baseline_initialized(self, source_id: str, timestamp: str, baseline_version: int = 2) -> None:
        self._baselines[source_id] = timestamp
        self._baseline_versions[source_id] = baseline_version

    def get_baseline_version(self, source_id: str) -> int:
        return self._baseline_versions.get(source_id, 0)

    def update_source_run(self, source_id: str, run_at: str, success: bool) -> None:
        self._source_runs[source_id] = {
            "last_run_at": run_at,
            "last_success_at": run_at if success else self._source_runs.get(source_id, {}).get("last_success_at"),
        }

    # --- Seen tickets ---
    def get_known_numbers(self, source_id: str, ticket_numbers: Iterable[str]) -> set[str]:
        known = self._seen.get(source_id, set())
        return {n for n in ticket_numbers if n in known}

    def upsert_seen_tickets(self, source_id: str, tickets: Iterable[Ticket], seen_at: str) -> None:
        if source_id not in self._seen:
            self._seen[source_id] = set()
        for t in tickets:
            self._seen[source_id].add(t.number)

    # --- Snapshots ---
    def save_snapshot(self, source_id: str, tickets: Iterable[Ticket], collected_at: str) -> None:
        self._snapshots.append({"source_id": source_id, "collected_at": collected_at})

    def save_load_snapshot(self, source_id: str, entries: Iterable[LoadEntry], collected_at: str) -> None:
        self._load_snapshots.append({"source_id": source_id, "collected_at": collected_at})

    # --- Delivery dedup ---
    def has_delivery(self, source_id: str, rule_id: str, recipient_id: str, ticket_number: str) -> bool:
        return self._deliveries.get((source_id, rule_id, recipient_id, ticket_number), False)

    def record_delivery(self, delivery: DeliveryRequest, attempted_at: str, result: NotificationResult) -> None:
        if result.success:
            self._deliveries[(delivery.source_id, delivery.rule_id, delivery.recipient_id, delivery.ticket.number)] = True

    # --- Workflow items ---
    def get_workflow_item(self, ticket_number: str, source_id: str) -> WorkflowItem | None:
        return self._workflow_items.get((ticket_number, source_id))

    def upsert_workflow_item(self, item: WorkflowItem) -> None:
        self._workflow_items[(item.ticket_number, item.source_id)] = item

    def get_items_in_state(self, state: TicketWorkflowState) -> list[WorkflowItem]:
        return [item for item in self._workflow_items.values() if item.current_state == state]

    # --- Audit trail ---
    def record_audit_event(self, event: AuditEvent) -> None:
        self._audit_events.append(event)

    def get_audit_trail(self, ticket_number: str | None = None, limit: int = 100) -> list[AuditEvent]:
        events = self._audit_events
        if ticket_number:
            events = [e for e in events if e.ticket_number == ticket_number]
        return sorted(events, key=lambda e: e.timestamp, reverse=True)[:limit]

    # --- Approval tracking ---
    def save_pending_approval(
        self,
        ticket_number: str,
        source_id: str,
        request_id: str,
        suggestions: list[AllocationSuggestion],
    ) -> None:
        self._pending_approvals.append({
            "ticket_number": ticket_number,
            "source_id": source_id,
            "request_id": request_id,
            "suggestions": suggestions,
        })

    def get_pending_approvals(self) -> list[dict[str, Any]]:
        return [a for a in self._pending_approvals if a.get("resolved_at") is None]

    def mark_approval_received(
        self,
        ticket_number: str,
        source_id: str,
        chosen_member_id: str,
        approved_at: str,
    ) -> None:
        for a in self._pending_approvals:
            if a["ticket_number"] == ticket_number and a["source_id"] == source_id:
                a["resolved_at"] = approved_at
                a["chosen_member_id"] = chosen_member_id
                break

    # --- Utility ---
    def forget_ticket(self, ticket_number: str, source_id: str | None = None) -> int:
        count = 0
        if source_id:
            if ticket_number in self._seen.get(source_id, set()):
                self._seen[source_id].discard(ticket_number)
                count = 1
        else:
            for sid in self._seen:
                if ticket_number in self._seen[sid]:
                    self._seen[sid].discard(ticket_number)
                    count += 1
        return count

    def initialize(self) -> None:
        pass
