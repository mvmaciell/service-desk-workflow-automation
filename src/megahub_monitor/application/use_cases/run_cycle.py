"""RunCycleUseCase — orchestrates detect → workflow/notify for one source.

Dual-path design:
  - allocation_enabled=True  → workflow path (suggest allocation, audit trail)
  - allocation_enabled=False → legacy path (route + Teams notification, existing behavior)

RunOnceService remains responsible for: collection, snapshots, lock.
This use case handles: detection, routing, workflow state, audit.
"""
from __future__ import annotations

from logging import Logger
from typing import Any

from ...config import Settings, SourceConfig
from ...domain.enums import AuditAction
from ...domain.errors import NotificationError
from ...domain.models import Ticket, utc_now_iso
from ...ports.state_repository import StateRepository
from ...ports.team_catalog import TeamCatalog
from ..services.audit_logger import AuditLogger
from ..services.load_analyzer import LoadAnalyzer
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
        router: Any = None,
        notifier: Any = None,
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

    def _workflow_path(
        self,
        source: SourceConfig,
        new_tickets: list[Ticket],
        all_tickets: list[Ticket],
        collected_at: str,
    ) -> None:
        assert self._catalog is not None
        assert self._suggest_uc is not None
        members = self._catalog.list_active_members()
        enhanced = self._load_analyzer.calculate(all_tickets, members=members)
        current_load: dict[str, int] = {
            e.member_id: e.open_tickets for e in enhanced if e.member_id
        }
        coordinator = self._catalog.get_coordinator()

        # --- Suggest allocation for new tickets ---
        for ticket in new_tickets:
            suggestions = self._suggest_uc.execute(
                ticket=ticket,
                members=members,
                current_load=current_load,
            )

            if not self._notifier:
                self._logger.warning(
                    "Notifier nao configurado — sugestoes para chamado %s descartadas.",
                    ticket.number,
                )
                continue

            if coordinator and coordinator.webhook_url:
                try:
                    self._notifier.send_allocation_suggestion(
                        coordinator_name=coordinator.name,
                        webhook_url=coordinator.webhook_url,
                        ticket=ticket,
                        suggestions=suggestions,
                        load_board=enhanced,
                    )
                    self._logger.info(
                        "Chamado %s: sugestao de alocacao enviada para %s.",
                        ticket.number,
                        coordinator.name,
                    )
                except Exception as exc:
                    self._logger.error(
                        "Falha ao notificar coordenador para o chamado %s. %s",
                        ticket.number,
                        exc,
                    )
            elif coordinator:
                self._logger.warning(
                    "Coordenador '%s' sem webhook configurado — sugestao nao enviada para chamado %s.",
                    coordinator.name,
                    ticket.number,
                )
            else:
                self._logger.warning(
                    "Sem coordenador no catalogo — sugestao nao enviada para chamado %s.",
                    ticket.number,
                )

    def _legacy_path(
        self,
        source: SourceConfig,
        new_tickets: list[Ticket],
        all_tickets: list[Ticket],
    ) -> None:
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
