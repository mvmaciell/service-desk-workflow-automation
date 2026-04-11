from __future__ import annotations

from logging import Logger

from ..models import DetectionResult, Ticket
from ..repository.sqlite_repository import SQLiteRepository


class TicketDetector:
    def __init__(self, repository: SQLiteRepository, logger: Logger) -> None:
        self.repository = repository
        self.logger = logger

    def process(self, tickets: list[Ticket], collected_at: str) -> DetectionResult:
        if not self.repository.is_baseline_initialized():
            self.repository.upsert_seen_tickets(tickets, collected_at)
            self.repository.mark_baseline_initialized(collected_at)
            self.logger.info(
                "Baseline inicial criado com %s chamado(s). Nenhuma notificacao sera enviada neste primeiro ciclo.",
                len(tickets),
            )
            return DetectionResult(is_baseline=True, total_tickets=len(tickets), new_tickets=[])

        known_numbers = self.repository.get_known_numbers(ticket.number for ticket in tickets)
        new_tickets = [ticket for ticket in tickets if ticket.number not in known_numbers]

        self.repository.upsert_seen_tickets(tickets, collected_at)
        return DetectionResult(
            is_baseline=False,
            total_tickets=len(tickets),
            new_tickets=new_tickets,
        )

