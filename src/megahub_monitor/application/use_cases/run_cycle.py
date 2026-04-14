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
from ...domain.enums import AuditAction
from ...domain.models import EnhancedLoadEntry, LoadEntry, Ticket
from ...ports.state_repository import StateRepository
from ...ports.team_catalog import TeamCatalog
from ..services.allocation_engine import AllocationEngine
from ..services.audit_logger import AuditLogger
from ..services.load_analyzer import LoadAnalyzer
from .detect_new_tickets import DetectNewTicketsUseCase
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

    def execute_source(
        self,
        source: SourceConfig,
        tickets: list[Ticket],
        collected_at: str,
    ) -> None:
        """Process a collected ticket list for a source."""
        detection = self._detect_uc.execute(source, tickets, collected_at)
        self._repo.update_source_run(source.id, collected_at, success=True)

        if not detection.new_tickets:
            return

        self._audit.log(
            action=AuditAction.TICKET_DETECTED,
            ticket_number=None,
            source_id=source.id,
            details={"count": len(detection.new_tickets), "is_baseline": detection.is_baseline},
        )

        if self._settings.allocation_enabled and self._catalog and self._suggest_uc:
            self._workflow_path(detection.new_tickets, tickets)
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

    def _workflow_path(self, new_tickets: list[Ticket], all_tickets: list[Ticket]) -> None:
        members = self._catalog.list_active_members()
        enhanced = self._load_analyzer.calculate(all_tickets, members=members)
        current_load: dict[str, int] = {
            e.member_id: e.open_tickets for e in enhanced if e.member_id
        }
        coordinator = self._catalog.get_coordinator()

        for ticket in new_tickets:
            suggestions = self._suggest_uc.execute(
                ticket=ticket,
                members=members,
                current_load=current_load,
            )

            if not self._notifier:
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
        from ...models import utc_now_iso
        from ...errors import NotificationError

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
