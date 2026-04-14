from __future__ import annotations

from abc import ABC, abstractmethod

from ..domain.models import (
    AllocationSuggestion,
    EnhancedLoadEntry,
    NotificationResult,
    Ticket,
)


class Notifier(ABC):
    @abstractmethod
    def send_new_ticket_alert(
        self,
        recipient_name: str,
        recipient_role: str,
        webhook_url: str,
        ticket: Ticket,
        load_entries: list[EnhancedLoadEntry],
        title_prefix: str,
    ) -> NotificationResult: ...

    @abstractmethod
    def send_allocation_suggestion(
        self,
        coordinator_name: str,
        webhook_url: str,
        ticket: Ticket,
        suggestions: list[AllocationSuggestion],
        load_board: list[EnhancedLoadEntry],
    ) -> NotificationResult: ...

    @abstractmethod
    def send_assignment_notice(
        self,
        developer_name: str,
        webhook_url: str,
        ticket: Ticket,
    ) -> NotificationResult: ...

    @abstractmethod
    def send_completion_notice(
        self,
        coordinator_name: str,
        webhook_url: str,
        ticket: Ticket,
        completed_by: str,
    ) -> NotificationResult: ...

    @abstractmethod
    def send_return_notice(
        self,
        recipient_name: str,
        webhook_url: str,
        ticket: Ticket,
        current_status: str,
    ) -> NotificationResult: ...

    @abstractmethod
    def send_test_message(
        self,
        recipient_name: str,
        recipient_role: str,
        webhook_url: str,
    ) -> NotificationResult: ...
