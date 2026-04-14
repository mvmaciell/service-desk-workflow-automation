"""ProcessApprovalUseCase — handles coordinator approval via CLI.

Called when the coordinator runs:
  python main.py approve --ticket X --member Y
"""
from __future__ import annotations

from logging import Logger

from ...domain.enums import AuditAction, TicketWorkflowState, can_transition
from ...domain.models import TeamMember
from ...infrastructure.clock import Clock, SystemClock
from ...ports.state_repository import StateRepository
from ...ports.team_catalog import TeamCatalog
from ..services.audit_logger import AuditLogger


class ApprovalError(Exception):
    """Raised when approval cannot be processed."""


class ProcessApprovalUseCase:
    def __init__(
        self,
        repository: StateRepository,
        team_catalog: TeamCatalog,
        logger: Logger,
        clock: Clock | None = None,
    ) -> None:
        self._repo = repository
        self._catalog = team_catalog
        self._logger = logger
        self._clock = clock or SystemClock()
        self._audit = AuditLogger(repository, clock)

    def execute(
        self,
        ticket_number: str,
        source_id: str,
        chosen_member_id: str,
        approved_by: str = "coordinator",
    ) -> TeamMember:
        """Process an approval decision.

        Returns:
            The TeamMember that was approved for assignment.

        Raises:
            ApprovalError: If no pending approval exists or member is invalid.
        """
        now = self._clock.now_iso()

        # Validate pending approval exists
        pending = self._repo.get_pending_approvals()
        match = next(
            (p for p in pending if p["ticket_number"] == ticket_number and p["source_id"] == source_id),
            None,
        )
        if match is None:
            raise ApprovalError(
                f"Nenhuma aprovacao pendente encontrada para o chamado {ticket_number} "
                f"na fonte '{source_id}'."
            )

        # Validate chosen member exists and is active
        member = self._catalog.get_member(chosen_member_id)
        if member is None:
            raise ApprovalError(
                f"Membro '{chosen_member_id}' nao encontrado no catalogo de equipe."
            )
        if not member.active:
            raise ApprovalError(
                f"Membro '{chosen_member_id}' ({member.name}) esta inativo."
            )

        # Record the approval
        self._repo.mark_approval_received(ticket_number, source_id, chosen_member_id, now)

        # Advance workflow state
        item = self._repo.get_workflow_item(ticket_number, source_id)
        if item and can_transition(item.current_state, TicketWorkflowState.ALLOCATION_APPROVED):
            item.transition_to(TicketWorkflowState.ALLOCATION_APPROVED, now)
            item.approved_member_id = chosen_member_id
            item.approval_received_at = now
            self._repo.upsert_workflow_item(item)

        self._audit.log(
            action=AuditAction.ALLOCATION_APPROVED,
            actor=approved_by,
            ticket_number=ticket_number,
            source_id=source_id,
            details={"chosen_member_id": chosen_member_id, "member_name": member.name},
        )

        self._logger.info(
            "Chamado %s: aprovacao registrada. Desenvolvedor escolhido: %s (%s).",
            ticket_number,
            member.name,
            chosen_member_id,
        )

        return member
