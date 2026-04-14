from __future__ import annotations

from abc import ABC, abstractmethod


class ITSMWriter(ABC):
    @abstractmethod
    def assign_ticket(self, source_id: str, ticket_number: str, member_name: str) -> bool:
        """Assign ticket to member in the ITSM. Returns True on success."""
