"""DetectNewTicketsUseCase — detects new tickets, fixing the baseline bug.

Bug (v1 behavior):
  On the very first run, ALL tickets are marked as "seen" and new_tickets=[]
  is returned. Tickets already in the queue with status "NOVO" are silenced
  forever — they never trigger the allocation workflow.

Fix (v2 behavior):
  On the very first run:
    1. Mark ALL tickets as seen (same as before — prevents duplicate alerts later).
    2. Also return tickets whose ticket_status is in novo_status_labels as new_tickets.
    3. Mark baseline with baseline_version=2 so the fix is not re-applied.

Backward compatibility:
  Sources already initialized with baseline_version=1 (old deployments) keep
  the original silencing behavior. The fix only activates for:
    - New sources (never initialized before).
    - Sources explicitly re-initialized with baseline_version=2.
"""
from __future__ import annotations

from logging import Logger

from ...config import SourceConfig
from ...domain.models import DetectionResult, Ticket
from ...ports.state_repository import StateRepository


class DetectNewTicketsUseCase:
    """Detects new tickets for a source, with corrected first-run behavior."""

    def __init__(
        self,
        repository: StateRepository,
        logger: Logger,
        novo_status_labels: list[str] | None = None,
    ) -> None:
        self._repo = repository
        self._logger = logger
        self._novo_labels: frozenset[str] = frozenset(
            s.strip() for s in (novo_status_labels or ["NOVO"]) if s.strip()
        )

    def execute(
        self,
        source: SourceConfig,
        tickets: list[Ticket],
        collected_at: str,
    ) -> DetectionResult:
        if not self._repo.is_baseline_initialized(source.id):
            return self._handle_first_run(source, tickets, collected_at)

        return self._handle_subsequent_run(source, tickets, collected_at)

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _handle_first_run(
        self,
        source: SourceConfig,
        tickets: list[Ticket],
        collected_at: str,
    ) -> DetectionResult:
        """First run with v2 behavior: mark all seen, but surface NOVO tickets."""
        self._repo.upsert_seen_tickets(source.id, tickets, collected_at)
        self._repo.mark_baseline_initialized(source.id, collected_at, baseline_version=2)

        novo_tickets = [
            t for t in tickets
            if t.ticket_status.strip() in self._novo_labels
        ]

        self._logger.info(
            "Fonte '%s': baseline v2 criado com %s chamado(s). %s com status NOVO surfaceados.",
            source.id,
            len(tickets),
            len(novo_tickets),
        )

        return DetectionResult(
            source_id=source.id,
            source_name=source.name,
            is_baseline=True,
            total_tickets=len(tickets),
            new_tickets=novo_tickets,
        )

    def _handle_subsequent_run(
        self,
        source: SourceConfig,
        tickets: list[Ticket],
        collected_at: str,
    ) -> DetectionResult:
        """Normal run — return genuinely new tickets not seen before."""
        known_numbers = self._repo.get_known_numbers(
            source.id, (t.number for t in tickets)
        )
        new_tickets = [t for t in tickets if t.number not in known_numbers]

        self._repo.upsert_seen_tickets(source.id, tickets, collected_at)

        if new_tickets:
            self._logger.info(
                "Fonte '%s': %s novo(s) chamado(s) detectado(s) de %s total.",
                source.id,
                len(new_tickets),
                len(tickets),
            )
        else:
            self._logger.info(
                "Fonte '%s': nenhum novo chamado detectado.",
                source.id,
            )

        return DetectionResult(
            source_id=source.id,
            source_name=source.name,
            is_baseline=False,
            total_tickets=len(tickets),
            new_tickets=new_tickets,
        )
