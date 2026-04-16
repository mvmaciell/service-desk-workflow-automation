from __future__ import annotations

import argparse
import csv
from pathlib import Path

from .adapters.catalog.toml_catalog import TomlTeamCatalog
from .adapters.notification.teams_notifier import TeamsNotifier
from .adapters.persistence.sqlite_repository import SQLiteStateRepository
from .application.services.allocation_engine import AllocationEngine
from .application.services.load_analyzer import LoadAnalyzer as AllocationLoadAnalyzer
from .application.use_cases.check_approval_timeout import CheckApprovalTimeoutUseCase
from .application.use_cases.detect_completion import DetectCompletionUseCase
from .application.use_cases.detect_new_tickets import DetectNewTicketsUseCase
from .application.use_cases.detect_status_return import DetectStatusReturnUseCase
from .application.use_cases.notify_assignment import NotifyAssignmentUseCase
from .application.use_cases.notify_completion import NotifyCompletionUseCase
from .application.use_cases.notify_status_return import NotifyStatusReturnUseCase
from .application.use_cases.process_approval import ApprovalError, ProcessApprovalUseCase
from .application.use_cases.run_cycle import RunCycleUseCase
from .application.use_cases.suggest_allocation import SuggestAllocationUseCase
from .browser import BrowserSession
from .collectors import build_collector
from .config import NotificationProfileConfig, Settings, SourceConfig
from .domain.models import Ticket
from .errors import ConfigurationError, MonitorError
from .logging_setup import configure_logging
from .notifiers import TeamsWorkflowNotifier
from .services import LoadAnalyzer, MonitorService, NotificationRouter, RunOnceService, TicketDetector


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Monitor multi-fonte do MegaHub.")
    subparsers = parser.add_subparsers(dest="command", required=True)

    login_parser = subparsers.add_parser("login", help="Abre o navegador com perfil persistente para login manual.")
    login_parser.add_argument("--context", dest="context_id", help="Id do contexto configurado.")
    login_parser.add_argument("--source", dest="source_id", help="Id da fonte usada para validar o login.")

    notify_parser = subparsers.add_parser("notify-test", help="Envia um card de teste para os perfis configurados.")
    notify_parser.add_argument("--profile", dest="profile_id", help="Id de um perfil especifico.")
    notify_parser.add_argument(
        "--recipient",
        dest="profile_id_legacy",
        help=argparse.SUPPRESS,
    )

    snapshot_parser = subparsers.add_parser("snapshot", help="Captura a fonte e imprime um resumo.")
    snapshot_parser.add_argument("--source", dest="source_id", help="Id da fonte configurada.")
    snapshot_parser.add_argument("--csv", dest="csv_path", default=None, help="Exportar para CSV (caminho do arquivo).")

    subparsers.add_parser("run-once", help="Executa um ciclo unico. Comando recomendado para o agendador.")
    subparsers.add_parser("monitor", help="Mantem o monitor em loop continuo.")

    forget_parser = subparsers.add_parser(
        "forget-ticket",
        help="Remove um chamado da base local para forcar reprocessamento em demo.",
    )
    forget_parser.add_argument("ticket_number", help="Numero do chamado.")
    forget_parser.add_argument("--source", dest="source_id", help="Id da fonte. Se omitido, remove em todas.")

    approve_parser = subparsers.add_parser(
        "approve",
        help="Registra aprovacao de alocacao e notifica o desenvolvedor.",
    )
    approve_parser.add_argument("--ticket", required=True, dest="ticket_number", help="Numero do chamado.")
    approve_parser.add_argument("--member", required=True, dest="member_id", help="Id do membro aprovado.")
    approve_parser.add_argument(
        "--source", dest="source_id", default=None,
        help="Id da fonte (omitir se unica aprovacao pendente).",
    )

    audit_parser = subparsers.add_parser(
        "audit-trail",
        help="Exibe trilha de auditoria do sistema.",
    )
    audit_parser.add_argument("--ticket", dest="ticket_number", default=None, help="Filtrar por numero de chamado.")
    audit_parser.add_argument("--limit", type=int, default=20, help="Maximo de eventos (padrao: 20).")

    status_parser = subparsers.add_parser(
        "status",
        help="Exibe visao consolidada do workflow para o coordenador.",
    )
    status_parser.add_argument(
        "--state", dest="state", default=None,
        help="Filtrar por estado do workflow (ex: ALLOCATION_SUGGESTED, ASSIGNED).",
    )

    bulk_approve_parser = subparsers.add_parser(
        "bulk-approve",
        help="Aprova multiplas sugestoes de alocacao de uma vez.",
    )
    bulk_approve_parser.add_argument(
        "approvals",
        nargs="+",
        help="Pares ticket:member_id (ex: 12345:dev-1 12346:dev-2).",
    )
    bulk_approve_parser.add_argument(
        "--source", dest="source_id", default=None,
        help="Id da fonte (obrigatorio se houver ambiguidade).",
    )

    subparsers.add_parser(
        "tray",
        help="Inicia o icone SDWA na bandeja do sistema (painel de status e controle).",
    )

    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()

    settings = Settings.load()
    logger = configure_logging(settings.log_file_path)

    state_repo = SQLiteStateRepository(settings.database_path)
    state_repo.initialize()
    repository = state_repo

    detector = TicketDetector(repository, logger)
    load_analyzer = LoadAnalyzer()
    router = NotificationRouter(settings, repository, logger)
    notifier = TeamsWorkflowNotifier(settings, logger)

    run_cycle = None
    if settings.allocation_enabled:
        team_catalog = TomlTeamCatalog(settings.teams_path)
        detect_uc = DetectNewTicketsUseCase(repository, logger)
        suggest_uc = SuggestAllocationUseCase(
            repository=repository,
            engine=AllocationEngine(),
            logger=logger,
        )
        teams_notifier = TeamsNotifier(settings, logger)
        run_cycle = RunCycleUseCase(
            detect_uc=detect_uc,
            suggest_uc=suggest_uc,
            team_catalog=team_catalog,
            load_analyzer=AllocationLoadAnalyzer(),
            repository=repository,
            settings=settings,
            logger=logger,
            notifier=teams_notifier,
        )
        run_cycle.set_completion_use_cases(
            detect_completion=DetectCompletionUseCase(repository, settings, logger),
            notify_completion=NotifyCompletionUseCase(repository, logger),
        )
        run_cycle.set_return_use_cases(
            detect_return=DetectStatusReturnUseCase(repository, settings, logger),
            notify_return=NotifyStatusReturnUseCase(logger),
        )
        run_cycle.set_timeout_use_case(
            CheckApprovalTimeoutUseCase(
                repository=repository,
                logger=logger,
                timeout_minutes=settings.approval_timeout_minutes,
            ),
        )

    run_once_service = RunOnceService(
        settings=settings,
        repository=repository,
        detector=detector,
        load_analyzer=load_analyzer,
        router=router,
        notifier=notifier,
        logger=logger,
        run_cycle=run_cycle,
    )
    monitor_service = MonitorService(settings, run_once_service, logger)

    try:
        if args.command == "login":
            source = _resolve_login_source(settings, args.source_id, args.context_id)
            collector = build_collector(settings, source, logger)
            browser_session = BrowserSession(settings, settings.get_context(source.context_id), logger)
            browser_session.interactive_login(source.url, collector.page_title)
            logger.info("Sessao persistida com sucesso para o contexto '%s'.", source.context_id)
            return 0

        if args.command == "notify-test":
            profile_id = args.profile_id or args.profile_id_legacy
            profiles = _resolve_profiles(settings, profile_id)
            for profile in profiles:
                result = notifier.send_test_message(profile.name, profile.role, profile.webhook_url)
                logger.info(
                    "Teste de notificacao concluido para o perfil '%s'. HTTP=%s",
                    profile.id,
                    result.status_code,
                )
            return 0

        if args.command == "snapshot":
            source = _resolve_source(settings, args.source_id)
            tickets = run_once_service.run_snapshot(source)
            logger.info("Resumo da captura da fonte '%s': %s chamado(s)", source.id, len(tickets))
            for ticket in tickets:
                logger.info(
                    "Chamado=%s | Tipo=%s | Prioridade=%s | Status=%s | Frente=%s | Empresa=%s | Titulo=%s",
                    ticket.number,
                    ticket.ticket_type or "-",
                    ticket.priority or "-",
                    ticket.ticket_status or "-",
                    ticket.front or "-",
                    ticket.company or "-",
                    ticket.title or "-",
                )

            csv_path = args.csv_path
            if csv_path is None:
                csv_path = f"data/snapshot-{source.id}.csv"
            out = Path(csv_path)
            out.parent.mkdir(parents=True, exist_ok=True)
            _export_snapshot_csv(tickets, out)
            logger.info("CSV exportado para: %s", out)
            return 0

        if args.command == "run-once":
            return run_once_service.run()

        if args.command == "monitor":
            return monitor_service.run_forever()

        if args.command == "forget-ticket":
            deleted = repository.forget_ticket(args.ticket_number, args.source_id)
            if deleted:
                logger.info(
                    "Chamado %s removido da base local%s.",
                    args.ticket_number,
                    f" na fonte '{args.source_id}'" if args.source_id else "",
                )
            else:
                logger.warning("Chamado %s nao existia na base local.", args.ticket_number)
            return 0

        if args.command == "approve":
            return _handle_approve(args, settings, repository, logger)

        if args.command == "audit-trail":
            return _handle_audit_trail(args, repository, logger)

        if args.command == "status":
            return _handle_status(args, repository, settings, logger)

        if args.command == "bulk-approve":
            return _handle_bulk_approve(args, settings, repository, logger)

        if args.command == "tray":
            from .tray_app import TrayApp, resolve_db_path  # noqa: PLC0415

            project_root = Path(__file__).resolve().parents[2]
            db_path = resolve_db_path(project_root)
            TrayApp(db_path=db_path, project_root=project_root).run()
            return 0

        parser.print_help()
        return 1
    except (ConfigurationError, MonitorError) as exc:
        logger.error(str(exc))
        return 1


def _handle_approve(args, settings: Settings, repository, logger) -> int:
    team_catalog = TomlTeamCatalog(settings.teams_path)
    process_uc = ProcessApprovalUseCase(
        repository=repository,
        team_catalog=team_catalog,
        logger=logger,
    )

    source_id = args.source_id
    if not source_id:
        pending = repository.get_pending_approvals()
        matches = [p for p in pending if p["ticket_number"] == args.ticket_number]
        if not matches:
            logger.error(
                "Nenhuma aprovacao pendente para o chamado %s. Use 'python main.py run-once' primeiro.",
                args.ticket_number,
            )
            return 1
        if len(matches) > 1:
            sources = [p["source_id"] for p in matches]
            logger.error(
                "Multiplas aprovacoes pendentes para o chamado %s. Especifique --source entre: %s",
                args.ticket_number,
                ", ".join(sources),
            )
            return 1
        source_id = matches[0]["source_id"]

    try:
        member = process_uc.execute(
            ticket_number=args.ticket_number,
            source_id=source_id,
            chosen_member_id=args.member_id,
        )
    except ApprovalError as exc:
        logger.error(str(exc))
        return 1

    teams_notifier = TeamsNotifier(settings, logger)
    notify_uc = NotifyAssignmentUseCase(repository=repository, logger=logger)
    ticket = repository.get_ticket_from_snapshot(args.ticket_number, source_id)
    if not ticket:
        ticket = Ticket(
            number=args.ticket_number,
            source_id=source_id,
            source_name=source_id,
            source_kind="unknown",
        )
    notify_uc.execute(ticket=ticket, member=member, notifier=teams_notifier)
    return 0


def _handle_audit_trail(args, repository, logger) -> int:
    events = repository.get_audit_trail(
        ticket_number=args.ticket_number,
        limit=args.limit,
    )
    if not events:
        logger.info("Nenhum evento de auditoria encontrado.")
        return 0
    for event in events:
        action_label = event.action.value if hasattr(event.action, "value") else str(event.action)
        logger.info(
            "[%s] %s | Chamado: %s | Ator: %s | %s",
            event.timestamp[:19],
            action_label,
            event.ticket_number or "-",
            event.actor,
            event.details,
        )
    return 0


def _export_snapshot_csv(tickets: list[Ticket], path: Path) -> None:
    if not tickets:
        return
    fieldnames = [
        "number", "customer_ticket_number", "company", "ticket_type",
        "priority", "front", "created_label", "due_date",
        "ticket_status", "consultant", "time_to_expire", "title",
    ]
    with path.open("w", newline="", encoding="utf-8-sig") as fh:
        writer = csv.DictWriter(fh, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        for ticket in tickets:
            writer.writerow(ticket.to_dict())


def _resolve_source(settings: Settings, source_id: str | None) -> SourceConfig:
    if source_id:
        return settings.get_source(source_id)

    enabled_sources = settings.enabled_sources()
    if not enabled_sources:
        raise ConfigurationError("Nenhuma fonte habilitada encontrada.")
    return enabled_sources[0]


def _resolve_login_source(settings: Settings, source_id: str | None, context_id: str | None) -> SourceConfig:
    if source_id:
        return settings.get_source(source_id)

    if context_id:
        for source in settings.sources.values():
            if source.context_id == context_id:
                return source
        raise ConfigurationError(f"Nenhuma fonte referencia o contexto '{context_id}'.")

    return _resolve_source(settings, None)


def _resolve_profiles(settings: Settings, profile_id: str | None) -> list[NotificationProfileConfig]:
    if profile_id:
        profile = settings.get_profile(profile_id)
        if not profile.webhook_url:
            raise ConfigurationError(f"Perfil '{profile_id}' esta sem webhook configurado.")
        return [profile]

    profiles = [
        profile
        for profile in settings.profiles.values()
        if profile.enabled and profile.webhook_url
    ]
    if not profiles:
        raise ConfigurationError("Nenhum perfil habilitado com webhook configurado.")
    return profiles


def _handle_status(args, repository, settings: Settings, logger) -> int:
    from .domain.enums import TicketWorkflowState  # noqa: PLC0415

    states_to_show = list(TicketWorkflowState)
    if args.state:
        try:
            states_to_show = [TicketWorkflowState[args.state.upper()]]
        except KeyError:
            valid = ", ".join(s.name for s in TicketWorkflowState)
            logger.error("Estado invalido: '%s'. Validos: %s", args.state, valid)
            return 1

    # Summary by state
    logger.info("=== Status do Workflow ===")
    total = 0
    for state in states_to_show:
        items = repository.get_items_in_state(state)
        if items:
            total += len(items)
            logger.info("  %-25s  %d chamado(s)", state.name, len(items))
            for item in items[:10]:
                extra = ""
                if item.approved_member_id:
                    extra = f" → {item.approved_member_id}"
                logger.info(
                    "    %s  (desde %s)%s",
                    item.ticket_number,
                    item.last_state_change_at[:16],
                    extra,
                )
            if len(items) > 10:
                logger.info("    ... e mais %d", len(items) - 10)

    if total == 0:
        logger.info("  Nenhum chamado no workflow.")

    # Pending approvals
    pending = repository.get_pending_approvals()
    if pending:
        logger.info("")
        logger.info("=== Aprovacoes Pendentes (%d) ===", len(pending))
        for p in pending:
            logger.info(
                "  Chamado %s | Fonte: %s | Criado em: %s",
                p["ticket_number"],
                p["source_id"],
                p.get("created_at", "-")[:16],
            )

    # Source status
    if hasattr(repository, "get_source_status"):
        sources = repository.get_source_status()
        if sources:
            logger.info("")
            logger.info("=== Fontes ===")
            for s in sources:
                logger.info(
                    "  %-20s  Ultimo ciclo: %s  Ultimo sucesso: %s",
                    s["source_id"],
                    (s.get("last_run_at") or "-")[:16],
                    (s.get("last_success_at") or "-")[:16],
                )

    return 0


def _handle_bulk_approve(args, settings: Settings, repository, logger) -> int:
    team_catalog = TomlTeamCatalog(settings.teams_path)
    process_uc = ProcessApprovalUseCase(
        repository=repository,
        team_catalog=team_catalog,
        logger=logger,
    )
    teams_notifier = TeamsNotifier(settings, logger)
    notify_uc = NotifyAssignmentUseCase(repository=repository, logger=logger)

    success_count = 0
    fail_count = 0

    for pair in args.approvals:
        if ":" not in pair:
            logger.error("Formato invalido: '%s'. Use ticket_number:member_id", pair)
            fail_count += 1
            continue

        ticket_number, member_id = pair.split(":", 1)

        source_id = args.source_id
        if not source_id:
            pending = repository.get_pending_approvals()
            matches = [p for p in pending if p["ticket_number"] == ticket_number]
            if not matches:
                logger.error("Nenhuma aprovacao pendente para o chamado %s.", ticket_number)
                fail_count += 1
                continue
            if len(matches) > 1:
                sources = [p["source_id"] for p in matches]
                logger.error(
                    "Multiplas aprovacoes para %s. Especifique --source entre: %s",
                    ticket_number, ", ".join(sources),
                )
                fail_count += 1
                continue
            source_id = matches[0]["source_id"]

        try:
            member = process_uc.execute(
                ticket_number=ticket_number,
                source_id=source_id,
                chosen_member_id=member_id,
            )
        except ApprovalError as exc:
            logger.error("Chamado %s: %s", ticket_number, exc)
            fail_count += 1
            continue

        ticket = repository.get_ticket_from_snapshot(ticket_number, source_id)
        if not ticket:
            ticket = Ticket(
                number=ticket_number,
                source_id=source_id,
                source_name=source_id,
                source_kind="unknown",
            )
        notify_uc.execute(ticket=ticket, member=member, notifier=teams_notifier)
        success_count += 1
        logger.info("Chamado %s aprovado para %s (%s).", ticket_number, member.name, member.id)

    logger.info("Bulk approve concluido: %d aprovado(s), %d erro(s).", success_count, fail_count)
    return 0 if fail_count == 0 else 1
