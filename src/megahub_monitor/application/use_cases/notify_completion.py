"""NotifyCompletionUseCase — notifies coordinator when a ticket is completed."""
from __future__ import annotations

from logging import Logger

from ...domain.enums import AuditAction, TicketWorkflowState, can_transition
from ...domain.models import TeamMember, Ticket, WorkflowItem
from ...infrastructure.clock import Clock, SystemClock
from ...ports.state_repository import StateRepository
from ...ports.team_catalog import TeamCatalog
from ..services.audit_logger import AuditLogger


class NotifyCompletionUseCase:
    """Sends completion notice to the coordinator and advances workflow state."""

    def __init__(
        self,
        repository: StateRepository,
        logger: Logger,
        clock: Clock | None = None,
    ) -> None:
        self._repo = repository
        self._logger = logger
        self._clock = clock or SystemClock()
        self._audit = AuditLogger(repository, clock)

    def execute(
        self,
        completed_pairs: list[tuple[WorkflowItem, Ticket]],
        coordinator: TeamMember | None,
        catalog: TeamCatalog,
        notifier,  # Notifier or any object with send_completion_notice()
    ) -> None:
        """Notify coordinator for each completed ticket and advance to COMPLETION_NOTIFIED."""
        if not completed_pairs:
            return

        now = self._clock.now_iso()

        if not coordinator:
            self._logger.warning(
                "Sem coordenador no catalogo — %s notificacao(oes) de conclusao nao enviada(s).",
                len(completed_pairs),
            )
            return

        if not coordinator.webhook_url:
            self._logger.warning(
                "Coordenador '%s' sem webhook — %s notificacao(oes) de conclusao nao enviada(s).",
                coordinator.name,
                len(completed_pairs),
            )
            return

        for item, ticket in completed_pairs:
            # Resolve developer name from catalog
            completed_by = item.approved_member_id or "?"
            if item.approved_member_id:
                member = catalog.get_member(item.approved_member_id)
                if member:
                    completed_by = member.name

            try:
                result = notifier.send_completion_notice(
                    coordinator_name=coordinator.name,
                    webhook_url=coordinator.webhook_url,
                    ticket=ticket,
                    completed_by=completed_by,
                )
            except Exception as exc:
                self._logger.error(
                    "Falha ao notificar conclusao do chamado %s. %s",
                    item.ticket_number,
                    exc,
                )
                continue

            self._audit.log(
                action=AuditAction.COMPLETION_NOTIFIED,
                ticket_number=item.ticket_number,
                source_id=item.source_id,
                details={
                    "coordinator": coordinator.name,
                    "completed_by": completed_by,
                    "success": result.success,
                },
            )

            if result.success:
                self._logger.info(
                    "Chamado %s: notificacao de conclusao enviada para %s.",
                    item.ticket_number,
                    coordinator.name,
                )
                if can_transition(item.current_state, TicketWorkflowState.COMPLETION_NOTIFIED):
                    item.transition_to(TicketWorkflowState.COMPLETION_NOTIFIED, now)
                    self._repo.upsert_workflow_item(item)
            else:
                self._logger.error(
                    "Falha ao notificar conclusao do chamado %s. HTTP=%s",
                    item.ticket_number,
                    result.status_code,
                )
