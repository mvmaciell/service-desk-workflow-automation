from __future__ import annotations

import time
from logging import Logger

from ..browser.session import BrowserSession
from ..collectors.minha_fila import MinhaFilaCollector
from ..config import Settings
from ..errors import AuthenticationRequiredError, NotificationError
from ..models import NotificationResult, Ticket, utc_now_iso
from ..notifiers.teams_workflow import TeamsWorkflowNotifier
from ..repository.sqlite_repository import SQLiteRepository
from .detector import TicketDetector


class MonitorService:
    def __init__(
        self,
        settings: Settings,
        browser_session: BrowserSession,
        collector: MinhaFilaCollector,
        detector: TicketDetector,
        repository: SQLiteRepository,
        notifier: TeamsWorkflowNotifier,
        logger: Logger,
    ) -> None:
        self.settings = settings
        self.browser_session = browser_session
        self.collector = collector
        self.detector = detector
        self.repository = repository
        self.notifier = notifier
        self.logger = logger

    def run_login(self) -> None:
        self.browser_session.interactive_login()
        self.logger.info("Sessao persistida com sucesso no perfil dedicado.")

    def run_snapshot(self) -> list[Ticket]:
        with self.browser_session.open_page() as page:
            tickets = self.collector.collect(page)

        collected_at = utc_now_iso()
        self.repository.save_snapshot(tickets, collected_at)
        return tickets

    def run_notify_test(self) -> NotificationResult:
        result = self.notifier.send_test_message()
        self.repository.record_notification_attempt("__test__", utc_now_iso(), result)
        return result

    def run_monitor(self, once: bool = False) -> int:
        with self.browser_session.open_page() as page:
            while True:
                try:
                    self._run_cycle(page)
                except AuthenticationRequiredError:
                    self.logger.error(
                        "Sessao indisponivel ou expirada. Execute 'python main.py login' novamente."
                    )
                    return 2
                except Exception:
                    self.logger.exception("Falha inesperada durante o ciclo do monitor.")
                    if once:
                        return 1

                if once:
                    return 0

                self.logger.info(
                    "Aguardando %s segundo(s) para o proximo ciclo.",
                    self.settings.monitor_interval_seconds,
                )
                time.sleep(self.settings.monitor_interval_seconds)

    def forget_ticket(self, ticket_number: str) -> int:
        deleted = self.repository.forget_ticket(ticket_number)
        if deleted:
            self.logger.info("Chamado %s removido da base local.", ticket_number)
        else:
            self.logger.warning("Chamado %s nao existia na base local.", ticket_number)
        return deleted

    def _run_cycle(self, page) -> None:
        collected_at = utc_now_iso()
        tickets = self.collector.collect(page)
        self.repository.save_snapshot(tickets, collected_at)

        detection = self.detector.process(tickets, collected_at)
        if detection.is_baseline:
            return

        if not detection.new_tickets:
            self.logger.info("Nenhum novo chamado detectado neste ciclo.")
            return

        self.logger.info("%s novo(s) chamado(s) detectado(s).", len(detection.new_tickets))
        for ticket in detection.new_tickets:
            self._notify_ticket(ticket)

    def _notify_ticket(self, ticket: Ticket) -> None:
        try:
            result = self.notifier.send_ticket(ticket)
        except NotificationError as exc:
            self.logger.error("Falha ao notificar o chamado %s. %s", ticket.number, exc)
            return

        self.repository.record_notification_attempt(ticket.number, utc_now_iso(), result)

        if result.success:
            self.logger.info("Notificacao enviada para o chamado %s.", ticket.number)
            return

        self.logger.error(
            "Falha ao notificar o chamado %s. HTTP=%s. Resposta=%s",
            ticket.number,
            result.status_code,
            result.response_text,
        )
