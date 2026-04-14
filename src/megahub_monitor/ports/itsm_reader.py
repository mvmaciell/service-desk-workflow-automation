from __future__ import annotations

from abc import ABC, abstractmethod

from ..domain.models import Ticket


class ITSMReader(ABC):
    @abstractmethod
    def read_queue(self, source_id: str) -> list[Ticket]:
        """Fetch all visible tickets from the given source."""

    @abstractmethod
    def read_ticket_status(self, source_id: str, ticket_number: str) -> str | None:
        """Read current status of a single ticket. None if not found."""

    @abstractmethod
    def interactive_login(self, source_id: str) -> None:
        """Open interactive browser for manual authentication."""
