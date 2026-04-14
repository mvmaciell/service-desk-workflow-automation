"""NotifyStatusReturnUseCase — notifica o desenvolvedor quando um chamado retorna."""
from __future__ import annotations

from logging import Logger

from ...domain.models import TeamMember, Ticket, WorkflowItem
from ...infrastructure.clock import Clock, SystemClock
from ...ports.team_catalog import TeamCatalog


class NotifyStatusReturnUseCase:
    """Envia notificação de retorno ao desenvolvedor atribuído (ou ao coordinator
    como fallback quando o membro não tem webhook configurado)."""

    def __init__(
        self,
        logger: Logger,
        clock: Clock | None = None,
    ) -> None:
        self._logger = logger
        self._clock = clock or SystemClock()

    def execute(
        self,
        returned_pairs: list[tuple[WorkflowItem, Ticket]],
        catalog: TeamCatalog,
        notifier,  # Notifier or any object with send_return_notice()
    ) -> None:
        """Notifica desenvolvedor ou coordenador para cada chamado retornado."""
        if not returned_pairs:
            return

        coordinator: TeamMember | None = catalog.get_coordinator()

        for item, ticket in returned_pairs:
            current_status = ticket.ticket_status.strip()
            recipient: TeamMember | None = None

            # Prefere o desenvolvedor atribuído
            if item.approved_member_id:
                recipient = catalog.get_member(item.approved_member_id)

            # Fallback: coordinator
            if recipient is None or not recipient.webhook_url:
                if coordinator and coordinator.webhook_url:
                    recipient = coordinator
                elif recipient and not recipient.webhook_url:
                    self._logger.warning(
                        "Chamado %s: desenvolvedor '%s' sem webhook — retorno nao notificado.",
                        item.ticket_number,
                        item.approved_member_id,
                    )
                    continue
                else:
                    self._logger.warning(
                        "Chamado %s: sem destinatario com webhook configurado — retorno nao notificado.",
                        item.ticket_number,
                    )
                    continue

            try:
                result = notifier.send_return_notice(
                    recipient_name=recipient.name,
                    webhook_url=recipient.webhook_url,
                    ticket=ticket,
                    current_status=current_status,
                )
            except Exception as exc:
                self._logger.error(
                    "Falha ao notificar retorno do chamado %s para '%s'. %s",
                    item.ticket_number,
                    recipient.name,
                    exc,
                )
                continue

            if result.success:
                self._logger.info(
                    "Chamado %s: notificacao de retorno enviada para '%s'.",
                    item.ticket_number,
                    recipient.name,
                )
            else:
                self._logger.error(
                    "Falha ao notificar retorno do chamado %s. HTTP=%s",
                    item.ticket_number,
                    result.status_code,
                )
