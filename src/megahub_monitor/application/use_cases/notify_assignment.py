"""NotifyAssignmentUseCase — sends Teams notice to developer after approval."""
from __future__ import annotations

from logging import Logger

from ...domain.enums import AuditAction, TicketWorkflowState, can_transition
from ...domain.models import NotificationResult, TeamMember, Ticket
from ...infrastructure.clock import Clock, SystemClock
from ...ports.state_repository import StateRepository
from ..services.audit_logger import AuditLogger


class NotifyAssignmentUseCase:
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
        ticket: Ticket,
        member: TeamMember,
        notifier,  # TeamsNotifier or any object with send_assignment_notice()
    ) -> NotificationResult | None:
        """Send assignment notice and advance workflow to ASSIGNED.

        Returns:
            NotificationResult if webhook was configured, None otherwise.
        """
        now = self._clock.now_iso()

        # Advance workflow state
        item = self._repo.get_workflow_item(ticket.number, ticket.source_id)
        if item and can_transition(item.current_state, TicketWorkflowState.ASSIGNED):
            item.transition_to(TicketWorkflowState.ASSIGNED, now)
            self._repo.upsert_workflow_item(item)

        self._audit.log(
            action=AuditAction.DEVELOPER_NOTIFIED,
            ticket_number=ticket.number,
            source_id=ticket.source_id,
            details={"member_id": member.id, "member_name": member.name},
        )

        if not member.webhook_url:
            self._logger.warning(
                "Membro '%s' sem webhook configurado — notificacao de atribuicao nao enviada.",
                member.name,
            )
            return None

        result = notifier.send_assignment_notice(member.name, member.webhook_url, ticket)

        if result.success:
            self._logger.info(
                "Chamado %s: notificacao de atribuicao enviada para %s.",
                ticket.number,
                member.name,
            )
        else:
            self._logger.error(
                "Falha ao notificar atribuicao para %s. HTTP=%s",
                member.name,
                result.status_code,
            )

        return result
