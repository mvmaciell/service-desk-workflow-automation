from __future__ import annotations

import argparse

from .browser import BrowserSession
from .collectors import MinhaFilaCollector
from .config import Settings
from .errors import ConfigurationError, MonitorError
from .logging_setup import configure_logging
from .notifiers import TeamsWorkflowNotifier
from .repository import SQLiteRepository
from .services import MonitorService, TicketDetector


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Monitor MVP da Minha Fila do MegaHub.")
    subparsers = parser.add_subparsers(dest="command", required=True)

    subparsers.add_parser("login", help="Abre o navegador com perfil persistente para login manual.")
    subparsers.add_parser("notify-test", help="Envia uma notificacao de teste para o Teams.")
    subparsers.add_parser("snapshot", help="Captura a primeira pagina e imprime um resumo.")

    monitor_parser = subparsers.add_parser("monitor", help="Inicia o monitor continuo.")
    monitor_parser.add_argument("--once", action="store_true", help="Executa apenas um ciclo.")

    forget_parser = subparsers.add_parser(
        "forget-ticket",
        help="Remove um chamado da base local para forcar reprocessamento em demo.",
    )
    forget_parser.add_argument("ticket_number", help="Numero do chamado.")

    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()

    settings = Settings.load()
    logger = configure_logging(settings.log_file_path)

    repository = SQLiteRepository(settings.database_path, logger)
    repository.initialize()

    service = MonitorService(
        settings=settings,
        browser_session=BrowserSession(settings, logger),
        collector=MinhaFilaCollector(settings, logger),
        detector=TicketDetector(repository, logger),
        repository=repository,
        notifier=TeamsWorkflowNotifier(settings, logger),
        logger=logger,
    )

    try:
        if args.command == "login":
            service.run_login()
            return 0

        if args.command == "notify-test":
            _require_webhook(settings)
            result = service.run_notify_test()
            logger.info("Teste de notificacao concluido. HTTP=%s", result.status_code)
            return 0 if result.success else 1

        if args.command == "snapshot":
            tickets = service.run_snapshot()
            logger.info("Resumo da captura:")
            for ticket in tickets:
                logger.info(
                    "Chamado=%s | Prioridade=%s | Tipo=%s | Titulo=%s",
                    ticket.number,
                    ticket.priority or "-",
                    ticket.ticket_type or "-",
                    ticket.title or "-",
                )
            return 0

        if args.command == "monitor":
            _require_webhook(settings)
            return service.run_monitor(once=args.once)

        if args.command == "forget-ticket":
            service.forget_ticket(args.ticket_number)
            return 0

        parser.print_help()
        return 1
    except (ConfigurationError, MonitorError) as exc:
        logger.error(str(exc))
        return 1


def _require_webhook(settings: Settings) -> None:
    if not settings.teams_webhook_url:
        raise ConfigurationError("Defina TEAMS_WEBHOOK_URL no .env antes de executar este comando.")

