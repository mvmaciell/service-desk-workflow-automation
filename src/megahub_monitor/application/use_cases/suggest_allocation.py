"""SuggestAllocationUseCase — ranks developers and records the pending approval."""
from __future__ import annotations

from logging import Logger

from ...domain.enums import AuditAction, TicketWorkflowState
from ...domain.models import AllocationSuggestion, TeamMember, Ticket, WorkflowItem
from ...infrastructure.clock import Clock, SystemClock
from ...ports.state_repository import StateRepository
from ..services.allocation_engine import AllocationEngine
from ..services.audit_logger import AuditLogger


class SuggestAllocationUseCase:
    def __init__(
        self,
        repository: StateRepository,
        engine: AllocationEngine,
        logger: Logger,
        clock: Clock | None = None,
        max_suggestions: int = 3,
    ) -> None:
        self._repo = repository
        self._engine = engine
        self._logger = logger
        self._clock = clock or SystemClock()
        self._max_suggestions = max_suggestions
        self._audit = AuditLogger(repository, clock)

    def execute(
        self,
        ticket: Ticket,
        members: list[TeamMember],
        current_load: dict[str, int],
        historical_load: dict[str, int] | None = None,
    ) -> list[AllocationSuggestion]:
        """Rank developers and persist a pending approval for the coordinator.

        Returns:
            Ranked list of AllocationSuggestion (may be empty if no active devs).
        """
        now = self._clock.now_iso()

        suggestions = self._engine.rank(
            ticket=ticket,
            members=members,
            current_load=current_load,
            historical_load=historical_load,
            max_suggestions=self._max_suggestions,
        )

        # Create or advance the WorkflowItem for this ticket
        item = self._repo.get_workflow_item(ticket.number, ticket.source_id)
        if item is None:
            item = WorkflowItem(
                ticket_number=ticket.number,
                source_id=ticket.source_id,
                current_state=TicketWorkflowState.DETECTED,
                detected_at=now,
                last_state_change_at=now,
            )

        if item.current_state == TicketWorkflowState.DETECTED:
            item.transition_to(TicketWorkflowState.ALLOCATION_SUGGESTED, now)

        item.suggested_member_ids = [s.member_id for s in suggestions]
        self._repo.upsert_workflow_item(item)

        # Persist pending approval so the coordinator can act via CLI
        import uuid
        request_id = str(uuid.uuid4())
        self._repo.save_pending_approval(
            ticket.number, ticket.source_id, request_id, suggestions
        )

        self._audit.log(
            action=AuditAction.ALLOCATION_SUGGESTED,
            ticket_number=ticket.number,
            source_id=ticket.source_id,
            details={
                "suggestions": [
                    {"member_id": s.member_id, "rank": s.rank, "reason": s.reason}
                    for s in suggestions
                ]
            },
        )

        self._logger.info(
            "Chamado %s: %s sugestao(oes) de alocacao gerada(s). Aguardando aprovacao.",
            ticket.number,
            len(suggestions),
        )

        return suggestions
