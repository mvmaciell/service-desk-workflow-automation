"""DetectCompletionUseCase — scans tracked tickets for completion status."""
from __future__ import annotations

from logging import Logger

from ...config import Settings
from ...domain.enums import AuditAction, TicketWorkflowState, can_transition
from ...domain.models import Ticket, WorkflowItem
from ...infrastructure.clock import Clock, SystemClock
from ...ports.state_repository import StateRepository
from ..services.audit_logger import AuditLogger


class DetectCompletionUseCase:
    """Detects tickets that transitioned to a completion status.

    Scans WorkflowItems in ASSIGNED or IN_PROGRESS state for the given source.
    If the corresponding ticket's current status matches a completion label,
    the item is transitioned to COMPLETED and returned.
    """

    def __init__(
        self,
        repository: StateRepository,
        settings: Settings,
        logger: Logger,
        clock: Clock | None = None,
    ) -> None:
        self._repo = repository
        self._settings = settings
        self._logger = logger
        self._clock = clock or SystemClock()
        self._audit = AuditLogger(repository, clock)

    def execute(
        self,
        source_id: str,
        tickets: list[Ticket],
        collected_at: str,
    ) -> list[tuple[WorkflowItem, Ticket]]:
        """Return (WorkflowItem, Ticket) pairs for newly completed tickets.

        A ticket is considered completed when its current ``ticket_status``
        (as observed in the latest snapshot) matches one of the configured
        ``completion_status_labels``.
        """
        completion_labels = {s.strip().lower() for s in self._settings.completion_status_labels}
        if not completion_labels:
            return []

        # Collect items in trackable states for this source
        trackable: list[WorkflowItem] = []
        for state in (TicketWorkflowState.ASSIGNED, TicketWorkflowState.IN_PROGRESS):
            trackable.extend(
                item for item in self._repo.get_items_in_state(state)
                if item.source_id == source_id
            )

        if not trackable:
            return []

        tickets_by_number: dict[str, Ticket] = {t.number: t for t in tickets}
        completed: list[tuple[WorkflowItem, Ticket]] = []

        for item in trackable:
            ticket = tickets_by_number.get(item.ticket_number)
            if ticket is None:
                # Ticket no longer visible in queue — cannot confirm completion
                continue

            if ticket.ticket_status.strip().lower() not in completion_labels:
                continue

            if not can_transition(item.current_state, TicketWorkflowState.COMPLETED):
                self._logger.warning(
                    "Chamado %s: status '%s' indica conclusao mas transicao %s→COMPLETED recusada.",
                    item.ticket_number,
                    ticket.ticket_status,
                    item.current_state.name,
                )
                continue

            item.transition_to(TicketWorkflowState.COMPLETED, collected_at)
            self._repo.upsert_workflow_item(item)

            self._audit.log(
                action=AuditAction.COMPLETION_DETECTED,
                ticket_number=item.ticket_number,
                source_id=source_id,
                details={
                    "ticket_status": ticket.ticket_status,
                    "completed_by": item.approved_member_id or "?",
                },
            )

            self._logger.info(
                "Chamado %s: conclusao detectada (status='%s', atribuido_a='%s').",
                item.ticket_number,
                ticket.ticket_status,
                item.approved_member_id or "?",
            )

            completed.append((item, ticket))

        return completed
