from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass

from ..domain.models import AllocationSuggestion, EnhancedLoadEntry


@dataclass(frozen=True, slots=True)
class AllocationApproved:
    ticket_number: str
    source_id: str
    chosen_member_id: str
    approved_by: str
    approved_at: str


class ApprovalGateway(ABC):
    @abstractmethod
    def send_approval_request(
        self,
        ticket_number: str,
        source_id: str,
        suggestions: list[AllocationSuggestion],
        load_board: list[EnhancedLoadEntry],
        coordinator_webhook_url: str,
    ) -> str:
        """Send approval request. Returns request_id for tracking."""

    @abstractmethod
    def poll_approval(self, request_id: str) -> AllocationApproved | None:
        """Check if coordinator responded. None if still pending."""
