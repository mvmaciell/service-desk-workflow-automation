from __future__ import annotations

import json
import os
import time
from contextlib import contextmanager
from logging import Logger

from ..application.use_cases.run_cycle import RunCycleUseCase
from ..browser.session import BrowserSession
from ..collectors import build_collector
from ..config import Settings, SourceConfig
from ..errors import AuthenticationRequiredError, LockUnavailableError, NotificationError
from ..models import Ticket, utc_now_iso
from ..notifiers.teams_workflow import TeamsWorkflowNotifier
from ..repository.sqlite_repository import SQLiteRepository
from .detector import TicketDetector
from .load_analyzer import LoadAnalyzer
from .router import NotificationRouter


class RunOnceService:
    def __init__(
        self,
        settings: Settings,
        repository: SQLiteRepository,
        detector: TicketDetector,
        load_analyzer: LoadAnalyzer,
        router: NotificationRouter,
        notifier: TeamsWorkflowNotifier,
        logger: Logger,
        run_cycle: RunCycleUseCase | None = None,
    ) -> None:
        self.settings = settings
        self.repository = repository
        self.detector = detector
        self.load_analyzer = load_analyzer
        self.router = router
        self.notifier = notifier
        self.logger = logger
        self.run_cycle = run_cycle

    def run(self) -> int:
        enabled_sources = self.settings.enabled_sources()
        if not enabled_sources:
            self.logger.warning("Nenhuma fonte habilitada para monitoramento.")
            return 0

        try:
            with self._execution_lock():
                return self._run_sources(enabled_sources)
        except LockUnavailableError as exc:
            self.logger.warning(str(exc))
            return 0

    def run_snapshot(self, source: SourceConfig) -> list[Ticket]:
        tickets = self._collect_tickets(source)
        collected_at = utc_now_iso()
        self.repository.save_snapshot(source.id, tickets, collected_at)
        self.repository.save_load_snapshot(source.id, self.load_analyzer.calculate(tickets), collected_at)
        self.repository.update_source_run(source.id, collected_at, success=True)
        return tickets

    def _run_sources(self, sources: list[SourceConfig]) -> int:
        exit_code = 0

        for source in sources:
            try:
                self._run_source(source)
            except AuthenticationRequiredError:
                self.logger.error(
                    "Fonte '%s' sem sessao valida. Execute o login do contexto '%s' novamente.",
                    source.id,
                    source.context_id,
                )
                exit_code = 2
            except Exception:
                self.logger.exception("Falha inesperada ao processar a fonte '%s'.", source.id)
                exit_code = 1

        return exit_code

    def _run_source(self, source: SourceConfig) -> None:
        collected_at = utc_now_iso()
        tickets = self._collect_tickets(source)
        load_entries = self.load_analyzer.calculate(tickets)

        self.repository.save_snapshot(source.id, tickets, collected_at)
        self.repository.save_load_snapshot(source.id, load_entries, collected_at)

        if self.run_cycle is not None:
            # New path: RunCycleUseCase handles detection + routing + audit
            self.run_cycle.execute_source(source, tickets, collected_at)
            return

        # Legacy path (preserved exactly when run_cycle is not wired)
        detection = self.detector.process(source, tickets, collected_at)
        self.repository.update_source_run(source.id, collected_at, success=True)

        if detection.is_baseline:
            return

        if not detection.new_tickets:
            self.logger.info("Fonte '%s': nenhum novo chamado detectado.", source.id)
            return

        deliveries = self.router.build_deliveries(source, detection.new_tickets, load_entries)
        self.logger.info(
            "Fonte '%s': %s novo(s) chamado(s), %s entrega(s) planejada(s).",
            source.id,
            len(detection.new_tickets),
            len(deliveries),
        )

        for delivery in deliveries:
            try:
                result = self.notifier.send_delivery(delivery)
            except NotificationError as exc:
                self.logger.error(
                    "Falha ao notificar '%s' para o chamado %s. %s",
                    delivery.recipient_id,
                    delivery.ticket.number,
                    exc,
                )
                continue

            self.repository.record_delivery(delivery, utc_now_iso(), result)
            if result.success:
                self.logger.info(
                    "Entrega concluida. Fonte='%s' Regra='%s' Destinatario='%s' Chamado='%s'.",
                    delivery.source_id,
                    delivery.rule_id,
                    delivery.recipient_id,
                    delivery.ticket.number,
                )
            else:
                self.logger.error(
                    "Entrega falhou. Fonte='%s' Regra='%s' Destinatario='%s' Chamado='%s' HTTP=%s.",
                    delivery.source_id,
                    delivery.rule_id,
                    delivery.recipient_id,
                    delivery.ticket.number,
                    result.status_code,
                )

    def _collect_tickets(self, source: SourceConfig) -> list[Ticket]:
        browser_context = self.settings.get_context(source.context_id)
        browser_session = BrowserSession(self.settings, browser_context, self.logger)
        collector = build_collector(self.settings, source, self.logger)

        with browser_session.open_page() as page:
            return collector.collect(page)

    @contextmanager
    def _execution_lock(self):
        lock_path = self.settings.lock_file_path
        stale_after_seconds = max(self.settings.monitor_interval_seconds * 3, 600)

        if lock_path.exists():
            age_seconds = time.time() - lock_path.stat().st_mtime
            if age_seconds > stale_after_seconds:
                self.logger.warning("Lock antigo encontrado. Removendo arquivo: %s", lock_path)
                lock_path.unlink(missing_ok=True)
            else:
                raise LockUnavailableError(f"Ja existe uma execucao em andamento: {lock_path}")

        fd = os.open(lock_path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        try:
            payload = {
                "pid": os.getpid(),
                "created_at": utc_now_iso(),
            }
            os.write(fd, json.dumps(payload).encode("utf-8"))
            os.close(fd)
            yield
        finally:
            try:
                lock_path.unlink(missing_ok=True)
            except OSError:
                pass
