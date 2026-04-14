from __future__ import annotations

import unicodedata
from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .models import Ticket


def _normalize(value: str) -> str:
    """Remove accents, strip, and lowercase for filter comparison."""
    normalized = unicodedata.normalize("NFD", value or "")
    normalized = "".join(ch for ch in normalized if unicodedata.category(ch) != "Mn")
    return normalized.strip().lower()


@dataclass(frozen=True, slots=True)
class TicketId:
    number: str
    source_id: str


@dataclass(frozen=True, slots=True)
class SubscriptionFilter:
    """Immutable filter set used to match tickets against subscription rules.

    An empty frozenset means "match all" for that dimension.
    All values must be pre-normalized (lowercase, no accents).
    """

    ticket_types: frozenset[str] = frozenset()
    priorities: frozenset[str] = frozenset()
    companies: frozenset[str] = frozenset()
    consultants: frozenset[str] = frozenset()
    fronts: frozenset[str] = frozenset()

    def matches(self, ticket: Ticket) -> bool:
        if self.ticket_types and _normalize(ticket.ticket_type) not in self.ticket_types:
            return False
        if self.priorities and _normalize(ticket.priority) not in self.priorities:
            return False
        if self.companies and _normalize(ticket.company) not in self.companies:
            return False
        if self.consultants and _normalize(ticket.consultant) not in self.consultants:
            return False
        if self.fronts and _normalize(ticket.front) not in self.fronts:
            return False
        return True
