from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Iterable
from typing import Any

from ..domain.enums import TicketWorkflowState
from ..domain.models import (
    AllocationSuggestion,
    AuditEvent,
    DeliveryRequest,
    LoadEntry,
    NotificationResult,
    Ticket,
    WorkflowItem,
)


class StateRepository(ABC):
    # --- Source state (existing) ---
    @abstractmethod
    def is_baseline_initialized(self, source_id: str) -> bool: ...

    @abstractmethod
    def mark_baseline_initialized(self, source_id: str, timestamp: str, baseline_version: int = 2) -> None: ...

    @abstractmethod
    def get_baseline_version(self, source_id: str) -> int: ...

    @abstractmethod
    def update_source_run(self, source_id: str, run_at: str, success: bool) -> None: ...

    # --- Seen tickets (existing) ---
    @abstractmethod
    def get_known_numbers(self, source_id: str, ticket_numbers: Iterable[str]) -> set[str]: ...

    @abstractmethod
    def upsert_seen_tickets(self, source_id: str, tickets: Iterable[Ticket], seen_at: str) -> None: ...

    # --- Snapshots (existing) ---
    @abstractmethod
    def save_snapshot(self, source_id: str, tickets: Iterable[Ticket], collected_at: str) -> None: ...

    @abstractmethod
    def save_load_snapshot(self, source_id: str, entries: Iterable[LoadEntry], collected_at: str) -> None: ...

    # --- Delivery dedup (existing) ---
    @abstractmethod
    def has_delivery(self, source_id: str, rule_id: str, recipient_id: str, ticket_number: str) -> bool: ...

    @abstractmethod
    def record_delivery(self, delivery: DeliveryRequest, attempted_at: str, result: NotificationResult) -> None: ...

    # --- Workflow items (NEW) ---
    @abstractmethod
    def get_workflow_item(self, ticket_number: str, source_id: str) -> WorkflowItem | None: ...

    @abstractmethod
    def upsert_workflow_item(self, item: WorkflowItem) -> None: ...

    @abstractmethod
    def get_items_in_state(self, state: TicketWorkflowState) -> list[WorkflowItem]: ...

    # --- Audit trail (NEW) ---
    @abstractmethod
    def record_audit_event(self, event: AuditEvent) -> None: ...

    @abstractmethod
    def get_audit_trail(self, ticket_number: str | None = None, limit: int = 100) -> list[AuditEvent]: ...

    # --- Approval tracking (NEW) ---
    @abstractmethod
    def save_pending_approval(
        self,
        ticket_number: str,
        source_id: str,
        request_id: str,
        suggestions: list[AllocationSuggestion],
    ) -> None: ...

    @abstractmethod
    def get_pending_approvals(self) -> list[dict[str, Any]]: ...

    @abstractmethod
    def mark_approval_received(
        self,
        ticket_number: str,
        source_id: str,
        chosen_member_id: str,
        approved_at: str,
    ) -> None: ...

    # --- Utility (existing) ---
    @abstractmethod
    def forget_ticket(self, ticket_number: str, source_id: str | None = None) -> int: ...

    @abstractmethod
    def initialize(self) -> None: ...
