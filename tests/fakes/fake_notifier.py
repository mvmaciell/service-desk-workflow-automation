from __future__ import annotations

from typing import Any

from src.megahub_monitor.domain.models import (
    AllocationSuggestion,
    EnhancedLoadEntry,
    NotificationResult,
    Ticket,
)
from src.megahub_monitor.ports.notifier import Notifier


class FakeNotifier(Notifier):
    def __init__(self, success: bool = True) -> None:
        self._success = success
        self.sent: list[dict[str, Any]] = []

    def _record(self, method: str, **kwargs: Any) -> NotificationResult:
        self.sent.append({"method": method, **kwargs})
        return NotificationResult(
            success=self._success,
            status_code=200 if self._success else 500,
            response_text="ok" if self._success else "error",
            payload={},
        )

    def send_new_ticket_alert(
        self,
        recipient_name: str,
        recipient_role: str,
        webhook_url: str,
        ticket: Ticket,
        load_entries: list[EnhancedLoadEntry],
        title_prefix: str,
    ) -> NotificationResult:
        return self._record(
            "send_new_ticket_alert",
            recipient_name=recipient_name,
            ticket_number=ticket.number,
        )

    def send_allocation_suggestion(
        self,
        coordinator_name: str,
        webhook_url: str,
        ticket: Ticket,
        suggestions: list[AllocationSuggestion],
        load_board: list[EnhancedLoadEntry],
    ) -> NotificationResult:
        return self._record(
            "send_allocation_suggestion",
            coordinator_name=coordinator_name,
            ticket_number=ticket.number,
        )

    def send_assignment_notice(
        self,
        developer_name: str,
        webhook_url: str,
        ticket: Ticket,
    ) -> NotificationResult:
        return self._record(
            "send_assignment_notice",
            developer_name=developer_name,
            ticket_number=ticket.number,
        )

    def send_completion_notice(
        self,
        coordinator_name: str,
        webhook_url: str,
        ticket: Ticket,
        completed_by: str,
    ) -> NotificationResult:
        return self._record(
            "send_completion_notice",
            coordinator_name=coordinator_name,
            ticket_number=ticket.number,
        )

    def send_test_message(
        self,
        recipient_name: str,
        recipient_role: str,
        webhook_url: str,
    ) -> NotificationResult:
        return self._record(
            "send_test_message",
            recipient_name=recipient_name,
        )
