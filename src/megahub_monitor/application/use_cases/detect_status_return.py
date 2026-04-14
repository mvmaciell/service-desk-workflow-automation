"""DetectStatusReturnUseCase — detecta chamados que retornaram ao desenvolvedor."""
from __future__ import annotations

from logging import Logger

from ...config import Settings
from ...domain.enums import AuditAction, TicketWorkflowState
from ...domain.models import Ticket, WorkflowItem
from ...infrastructure.clock import Clock, SystemClock
from ...ports.state_repository import StateRepository
from ..services.audit_logger import AuditLogger


class DetectStatusReturnUseCase:
    """Detecta chamados em ASSIGNED/IN_PROGRESS cujo status ITSM mudou para um
    dos ``return_to_developer_labels`` configurados.

    Não altera ``current_state`` do WorkflowItem — apenas atualiza
    ``last_known_itsm_status`` e retorna os pares para notificação.
    A detecção é baseada em mudança de status: só dispara quando o status
    atual difere do ``last_known_itsm_status`` armazenado.
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
        """Retorna (WorkflowItem, Ticket) para chamados que retornaram ao desenvolvedor.

        Um chamado é considerado "retornado" quando:
        - Está em ASSIGNED ou IN_PROGRESS no SDWA
        - Seu ``ticket_status`` atual corresponde a um ``return_to_developer_labels``
        - O status mudou em relação ao ``last_known_itsm_status`` salvo
        """
        return_labels = {s.strip().lower() for s in self._settings.return_to_developer_labels}
        if not return_labels:
            return []

        trackable: list[WorkflowItem] = []
        for state in (TicketWorkflowState.ASSIGNED, TicketWorkflowState.IN_PROGRESS):
            trackable.extend(
                item for item in self._repo.get_items_in_state(state)
                if item.source_id == source_id
            )

        if not trackable:
            return []

        tickets_by_number: dict[str, Ticket] = {t.number: t for t in tickets}
        returned: list[tuple[WorkflowItem, Ticket]] = []

        for item in trackable:
            ticket = tickets_by_number.get(item.ticket_number)
            if ticket is None:
                continue

            current_status = ticket.ticket_status.strip()
            if current_status.lower() not in return_labels:
                continue

            # Só notifica se o status mudou desde a última verificação
            if current_status == item.last_known_itsm_status:
                continue

            # Salva o novo status para não renotificar no próximo ciclo
            previous_status = item.last_known_itsm_status
            item.last_known_itsm_status = current_status
            self._repo.upsert_workflow_item(item)

            self._audit.log(
                action=AuditAction.TICKET_RETURNED,
                ticket_number=item.ticket_number,
                source_id=source_id,
                details={
                    "ticket_status": current_status,
                    "previous_status": previous_status,
                    "assigned_to": item.approved_member_id or "?",
                },
            )

            self._logger.info(
                "Chamado %s: retornou ao desenvolvedor (status='%s', atribuido_a='%s').",
                item.ticket_number,
                current_status,
                item.approved_member_id or "?",
            )

            returned.append((item, ticket))

        return returned
