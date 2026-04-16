"""RunCycleUseCase — orchestrates detect → workflow/notify for one source.

Dual-path design:
  - allocation_enabled=True  → workflow path (suggest allocation, audit trail)
  - allocation_enabled=False → legacy path (route + Teams notification, existing behavior)

RunOnceService remains responsible for: collection, snapshots, lock.
This use case handles: detection, routing, workflow state, audit.
"""
from __future__ import annotations

from logging import Logger

from ...config import Settings, SourceConfig
from ...domain.enums import AuditAction, TicketWorkflowState
from ...domain.models import Ticket
from ...ports.state_repository import StateRepository
from ...ports.team_catalog import TeamCatalog
from ..services.audit_logger import AuditLogger
from ..services.load_analyzer import LoadAnalyzer
from .check_approval_timeout import CheckApprovalTimeoutUseCase
from .detect_completion import DetectCompletionUseCase
from .detect_new_tickets import DetectNewTicketsUseCase
from .detect_status_return import DetectStatusReturnUseCase
from .notify_completion import NotifyCompletionUseCase
from .notify_status_return import NotifyStatusReturnUseCase
from .suggest_allocation import SuggestAllocationUseCase


class RunCycleUseCase:
    """Orchestrates the detect → suggest/notify cycle for a single source."""

    def __init__(
        self,
        detect_uc: DetectNewTicketsUseCase,
        suggest_uc: SuggestAllocationUseCase | None,
        team_catalog: TeamCatalog | None,
        load_analyzer: LoadAnalyzer,
        repository: StateRepository,
        settings: Settings,
        logger: Logger,
        # Legacy notification path (used when allocation_enabled=False)
        router=None,
        notifier=None,
    ) -> None:
        self._detect_uc = detect_uc
        self._suggest_uc = suggest_uc
        self._catalog = team_catalog
        self._load_analyzer = load_analyzer
        self._repo = repository
        self._settings = settings
        self._logger = logger
        self._router = router
        self._notifier = notifier
        self._audit = AuditLogger(repository)
        self._detect_completion_uc: DetectCompletionUseCase | None = None
        self._notify_completion_uc: NotifyCompletionUseCase | None = None
        self._detect_return_uc: DetectStatusReturnUseCase | None = None
        self._notify_return_uc: NotifyStatusReturnUseCase | None = None
        self._check_timeout_uc: CheckApprovalTimeoutUseCase | None = None

    def set_completion_use_cases(
        self,
        detect_completion: DetectCompletionUseCase,
        notify_completion: NotifyCompletionUseCase,
    ) -> None:
        """Optionally wire completion detection and notification (Phase 7)."""
        self._detect_completion_uc = detect_completion
        self._notify_completion_uc = notify_completion

    def set_return_use_cases(
        self,
        detect_return: DetectStatusReturnUseCase,
        notify_return: NotifyStatusReturnUseCase,
    ) -> None:
        """Wire status-return detection and notification."""
        self._detect_return_uc = detect_return
        self._notify_return_uc = notify_return

    def set_timeout_use_case(self, check_timeout: CheckApprovalTimeoutUseCase) -> None:
        """Wire approval timeout checker."""
        self._check_timeout_uc = check_timeout

    def execute_source(
        self,
        source: SourceConfig,
        tickets: list[Ticket],
        collected_at: str,
    ) -> None:
        """Process a collected ticket list for a source."""
        detection = self._detect_uc.execute(source, tickets, collected_at)
        self._repo.update_source_run(source.id, collected_at, success=True)

        # Completion e return detection rodam A CADA CICLO (independente de novos tickets)
        if self._detect_completion_uc and self._catalog:
            coordinator = self._catalog.get_coordinator()
            completed_pairs = self._detect_completion_uc.execute(
                source_id=source.id,
                tickets=tickets,
                collected_at=collected_at,
            )
            if completed_pairs and self._notify_completion_uc and self._notifier:
                self._notify_completion_uc.execute(
                    completed_pairs=completed_pairs,
                    coordinator=coordinator,
                    catalog=self._catalog,
                    notifier=self._notifier,
                )

        if self._detect_return_uc and self._catalog:
            returned_pairs = self._detect_return_uc.execute(
                source_id=source.id,
                tickets=tickets,
                collected_at=collected_at,
            )
            if returned_pairs and self._notify_return_uc and self._notifier:
                self._notify_return_uc.execute(
                    returned_pairs=returned_pairs,
                    catalog=self._catalog,
                    notifier=self._notifier,
                )

        # Check for timed-out approvals and send reminders
        if self._check_timeout_uc and self._catalog and self._notifier:
            timed_out = self._check_timeout_uc.execute()
            if timed_out:
                coordinator = self._catalog.get_coordinator()
                if coordinator and coordinator.webhook_url:
                    try:
                        self._notifier.send_approval_reminder(
                            coordinator_name=coordinator.name,
                            webhook_url=coordinator.webhook_url,
                            timed_out_approvals=timed_out,
                        )
                        self._logger.info(
                            "Lembrete enviado: %s aprovacao(oes) pendente(s).", len(timed_out),
                        )
                    except Exception as exc:
                        self._logger.error("Falha ao enviar lembrete de timeout. %s", exc)

        if not detection.new_tickets:
            return

        self._audit.log(
            action=AuditAction.TICKET_DETECTED,
            ticket_number=None,
            source_id=source.id,
            details={"count": len(detection.new_tickets), "is_baseline": detection.is_baseline},
        )

        if self._settings.allocation_enabled and self._catalog and self._suggest_uc:
            self._workflow_path(source, detection.new_tickets, tickets, collected_at)
        elif self._router and self._notifier:
            self._legacy_path(source, detection.new_tickets, tickets)
        else:
            self._logger.warning(
                "Fonte '%s': %s novo(s) chamado(s) detectado(s) mas nenhum roteador configurado.",
                source.id,
                len(detection.new_tickets),
            )

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _count_internal_assignments(self) -> dict[str, int]:
        """Count tickets assigned via SDWA but not yet reflected in the queue.

        Looks at WorkflowItems in ASSIGNED or IN_PROGRESS state where
        an approved_member_id exists. Returns {member_id: count}.
        """
        from collections import Counter  # noqa: PLC0415

        counts: Counter[str] = Counter()
        for state in (
            TicketWorkflowState.ALLOCATION_APPROVED,
            TicketWorkflowState.ASSIGNED,
            TicketWorkflowState.IN_PROGRESS,
        ):
            items = self._repo.get_items_in_state(state)
            for item in items:
                if item.approved_member_id:
                    counts[item.approved_member_id] += 1
        return dict(counts)

    def _workflow_path(
        self,
        source: SourceConfig,
        new_tickets: list[Ticket],
        all_tickets: list[Ticket],
        collected_at: str,
    ) -> None:
        members = self._catalog.list_active_members()

        # Reconcile: count SDWA-internal assignments not yet reflected in queue
        internal_assignments = self._count_internal_assignments()

        enhanced = self._load_analyzer.calculate(
            all_tickets, members=members, internal_assignments=internal_assignments,
        )
        current_load: dict[str, int] = {
            e.member_id: e.open_tickets for e in enhanced if e.member_id
        }
        coordinator = self._catalog.get_coordinator()

        # --- Filter by coordinator's managed_fronts ---
        filtered = new_tickets
        if coordinator and coordinator.managed_fronts:
            managed = set(coordinator.managed_fronts)
            filtered = [t for t in new_tickets if t.front.strip().lower() in managed]
            skipped = len(new_tickets) - len(filtered)
            if skipped:
                self._logger.info(
                    "Fonte '%s': %s chamado(s) fora das frentes do coordenador (ignorados).",
                    source.id,
                    skipped,
                )

        if not filtered:
            return

        # --- Prioritize: Imediata > Urgente > Normal > Baixa > sem prioridade ---
        priority_order = {"imediata": 0, "urgente": 1, "normal": 2, "baixa": 3}
        filtered.sort(key=lambda t: priority_order.get(t.priority.strip().lower(), 4))

        # --- Apply per-cycle limit to avoid flooding ---
        limit = self._settings.max_new_tickets_per_cycle
        if len(filtered) > limit:
            self._logger.warning(
                "Fonte '%s': %s chamados novos detectados, limitando sugestoes a %s. "
                "Restante sera processado no proximo ciclo.",
                source.id,
                len(filtered),
                limit,
            )
            # Remaining tickets stay as DETECTED — will be picked up next cycle
            filtered = filtered[:limit]

        # --- Suggest allocation for each ticket ---
        ticket_suggestions: list[tuple[Ticket, list]] = []
        for ticket in filtered:
            suggestions = self._suggest_uc.execute(
                ticket=ticket,
                members=members,
                current_load=current_load,
            )
            ticket_suggestions.append((ticket, suggestions))

        # --- Send consolidated card to coordinator ---
        if not self._notifier:
            return

        if coordinator and coordinator.webhook_url:
            try:
                self._notifier.send_batch_allocation_suggestion(
                    coordinator_name=coordinator.name,
                    webhook_url=coordinator.webhook_url,
                    ticket_suggestions=ticket_suggestions,
                    load_board=enhanced,
                )
                self._logger.info(
                    "Fonte '%s': card consolidado com %s sugestao(oes) enviado para %s.",
                    source.id,
                    len(ticket_suggestions),
                    coordinator.name,
                )
            except Exception as exc:
                self._logger.error(
                    "Falha ao notificar coordenador. %s", exc,
                )
        elif coordinator:
            self._logger.warning(
                "Coordenador '%s' sem webhook configurado — %s sugestao(oes) nao enviada(s).",
                coordinator.name,
                len(ticket_suggestions),
            )
        else:
            self._logger.warning(
                "Sem coordenador no catalogo — %s sugestao(oes) nao enviada(s).",
                len(ticket_suggestions),
            )

    def _legacy_path(
        self,
        source: SourceConfig,
        new_tickets: list[Ticket],
        all_tickets: list[Ticket],
    ) -> None:
        from ...errors import NotificationError
        from ...models import utc_now_iso

        legacy_load = self._load_analyzer.calculate_legacy(all_tickets)
        deliveries = self._router.build_deliveries(source, new_tickets, legacy_load)

        self._logger.info(
            "Fonte '%s': %s novo(s) chamado(s), %s entrega(s) planejada(s).",
            source.id,
            len(new_tickets),
            len(deliveries),
        )

        for delivery in deliveries:
            try:
                result = self._notifier.send_delivery(delivery)
            except NotificationError as exc:
                self._logger.error(
                    "Falha ao notificar '%s' para o chamado %s. %s",
                    delivery.recipient_id,
                    delivery.ticket.number,
                    exc,
                )
                continue

            self._repo.record_delivery(delivery, utc_now_iso(), result)
            if result.success:
                self._logger.info(
                    "Entrega concluida. Fonte='%s' Regra='%s' Destinatario='%s' Chamado='%s'.",
                    delivery.source_id,
                    delivery.rule_id,
                    delivery.recipient_id,
                    delivery.ticket.number,
                )
            else:
                self._logger.error(
                    "Entrega falhou. HTTP=%s Chamado='%s'.",
                    result.status_code,
                    delivery.ticket.number,
                )
