from __future__ import annotations

from src.megahub_monitor.domain.models import Ticket
from src.megahub_monitor.ports.itsm_reader import ITSMReader


class FakeITSMReader(ITSMReader):
    def __init__(self, tickets: list[Ticket] | None = None) -> None:
        self.tickets = tickets or []
        self.login_calls: list[str] = []

    def read_queue(self, source_id: str) -> list[Ticket]:
        return [t for t in self.tickets if t.source_id == source_id]

    def read_ticket_status(self, source_id: str, ticket_number: str) -> str | None:
        for t in self.tickets:
            if t.source_id == source_id and t.number == ticket_number:
                return t.ticket_status
        return None

    def interactive_login(self, source_id: str) -> None:
        self.login_calls.append(source_id)
