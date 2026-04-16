"""Unit tests for RunCycleUseCase — coordinator workflow path."""
from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone

from src.megahub_monitor.application.services.allocation_engine import AllocationEngine
from src.megahub_monitor.application.services.load_analyzer import LoadAnalyzer
from src.megahub_monitor.application.use_cases.check_approval_timeout import CheckApprovalTimeoutUseCase
from src.megahub_monitor.application.use_cases.detect_new_tickets import DetectNewTicketsUseCase
from src.megahub_monitor.application.use_cases.run_cycle import RunCycleUseCase
from src.megahub_monitor.application.use_cases.suggest_allocation import SuggestAllocationUseCase
from src.megahub_monitor.domain.models import TeamMember, Ticket
from tests.fakes.fake_notifier import FakeNotifier
from tests.fakes.fake_state_repository import FakeStateRepository
from tests.fakes.fake_team_catalog import FakeTeamCatalog


def _make_settings(**overrides):
    """Build a minimal Settings-like object for testing."""
    from types import SimpleNamespace

    defaults = {
        "allocation_enabled": True,
        "novo_status_labels": ["Novo"],
        "completion_status_labels": ["Fechado"],
        "return_to_developer_labels": ["Não Homologado"],
        "approval_timeout_minutes": 60,
        "max_new_tickets_per_cycle": 5,
    }
    defaults.update(overrides)
    return SimpleNamespace(**defaults)


def _make_ticket(number: str, front: str = "AMS FI", priority: str = "Normal", status: str = "Novo") -> Ticket:
    return Ticket(
        number=number,
        source_id="src-1",
        source_name="Test",
        source_kind="fila",
        front=front,
        priority=priority,
        ticket_status=status,
        title=f"Ticket {number}",
    )


def _make_source():
    from types import SimpleNamespace
    return SimpleNamespace(id="src-1", name="Test Source", kind="fila")


def _build_cycle(
    members: list[TeamMember],
    settings_overrides: dict | None = None,
) -> tuple[RunCycleUseCase, FakeStateRepository, FakeNotifier]:
    repo = FakeStateRepository()
    logger = logging.getLogger("test")
    settings = _make_settings(**(settings_overrides or {}))
    catalog = FakeTeamCatalog(members)
    notifier = FakeNotifier()

    detect_uc = DetectNewTicketsUseCase(repo, logger, novo_status_labels=["Novo"])
    suggest_uc = SuggestAllocationUseCase(repo, AllocationEngine(), logger)

    cycle = RunCycleUseCase(
        detect_uc=detect_uc,
        suggest_uc=suggest_uc,
        team_catalog=catalog,
        load_analyzer=LoadAnalyzer(),
        repository=repo,
        settings=settings,
        logger=logger,
        notifier=notifier,
    )
    return cycle, repo, notifier


class TestWorkflowPath:
    def test_sends_batch_card_for_new_tickets(self):
        members = [
            TeamMember(id="dev-1", name="Alice", role="developer", skills=["ams fi"]),
            TeamMember(id="coord", name="Coord", role="coordinator", webhook_url="http://hook"),
        ]
        cycle, repo, notifier = _build_cycle(members)
        source = _make_source()
        tickets = [_make_ticket("100"), _make_ticket("101")]

        cycle.execute_source(source, tickets, "2026-04-15T00:00:00Z")

        batch_calls = [s for s in notifier.sent if s["method"] == "send_batch_allocation_suggestion"]
        assert len(batch_calls) == 1
        assert batch_calls[0]["ticket_count"] == 2

    def test_respects_max_new_tickets_per_cycle(self):
        members = [
            TeamMember(id="dev-1", name="Alice", role="developer", skills=["ams fi"]),
            TeamMember(id="coord", name="Coord", role="coordinator", webhook_url="http://hook"),
        ]
        cycle, repo, notifier = _build_cycle(members, {"max_new_tickets_per_cycle": 2})
        source = _make_source()
        tickets = [_make_ticket(str(i)) for i in range(10)]

        cycle.execute_source(source, tickets, "2026-04-15T00:00:00Z")

        batch_calls = [s for s in notifier.sent if s["method"] == "send_batch_allocation_suggestion"]
        assert len(batch_calls) == 1
        assert batch_calls[0]["ticket_count"] == 2

    def test_filters_by_managed_fronts(self):
        members = [
            TeamMember(id="dev-1", name="Alice", role="developer", skills=["ams fi"]),
            TeamMember(
                id="coord", name="Coord", role="coordinator",
                webhook_url="http://hook", managed_fronts=["ams fi"],
            ),
        ]
        cycle, repo, notifier = _build_cycle(members)
        source = _make_source()
        tickets = [
            _make_ticket("100", front="AMS FI"),
            _make_ticket("101", front="AMS HR"),
            _make_ticket("102", front="AMS FI"),
        ]

        cycle.execute_source(source, tickets, "2026-04-15T00:00:00Z")

        batch_calls = [s for s in notifier.sent if s["method"] == "send_batch_allocation_suggestion"]
        assert len(batch_calls) == 1
        assert batch_calls[0]["ticket_count"] == 2

    def test_prioritizes_urgent_tickets_first(self):
        members = [
            TeamMember(id="dev-1", name="Alice", role="developer", skills=["ams fi"]),
            TeamMember(id="coord", name="Coord", role="coordinator", webhook_url="http://hook"),
        ]
        cycle, repo, notifier = _build_cycle(members)
        source = _make_source()
        tickets = [
            _make_ticket("100", priority="Baixa"),
            _make_ticket("101", priority="Imediata"),
            _make_ticket("102", priority="Urgente"),
        ]

        cycle.execute_source(source, tickets, "2026-04-15T00:00:00Z")

        # Verify suggestions were created in priority order
        items = list(repo._workflow_items.values())
        numbers = [item.ticket_number for item in items]
        assert numbers[0] == "101"  # Imediata first
        assert numbers[1] == "102"  # Urgente second
        assert numbers[2] == "100"  # Baixa last

    def test_no_card_when_coordinator_has_no_webhook(self):
        members = [
            TeamMember(id="dev-1", name="Alice", role="developer", skills=["ams fi"]),
            TeamMember(id="coord", name="Coord", role="coordinator", webhook_url=""),
        ]
        cycle, repo, notifier = _build_cycle(members)
        source = _make_source()
        tickets = [_make_ticket("100")]

        cycle.execute_source(source, tickets, "2026-04-15T00:00:00Z")

        batch_calls = [s for s in notifier.sent if s["method"] == "send_batch_allocation_suggestion"]
        assert len(batch_calls) == 0

    def test_no_card_when_all_fronts_filtered_out(self):
        members = [
            TeamMember(id="dev-1", name="Alice", role="developer", skills=["ams fi"]),
            TeamMember(
                id="coord", name="Coord", role="coordinator",
                webhook_url="http://hook", managed_fronts=["ams hr"],
            ),
        ]
        cycle, repo, notifier = _build_cycle(members)
        source = _make_source()
        tickets = [_make_ticket("100", front="AMS FI")]

        cycle.execute_source(source, tickets, "2026-04-15T00:00:00Z")

        batch_calls = [s for s in notifier.sent if s["method"] == "send_batch_allocation_suggestion"]
        assert len(batch_calls) == 0

    def test_sends_approval_reminder_for_timed_out(self):
        members = [
            TeamMember(id="dev-1", name="Alice", role="developer", skills=["ams fi"]),
            TeamMember(id="coord", name="Coord", role="coordinator", webhook_url="http://hook"),
        ]
        cycle, repo, notifier = _build_cycle(members)

        # Seed a timed-out pending approval
        two_hours_ago = (datetime.now(timezone.utc) - timedelta(hours=2)).isoformat()
        repo._pending_approvals.append({
            "ticket_number": "500",
            "source_id": "src-1",
            "created_at": two_hours_ago,
            "suggestions": [],
        })

        timeout_uc = CheckApprovalTimeoutUseCase(repo, logging.getLogger(), timeout_minutes=60)
        cycle.set_timeout_use_case(timeout_uc)

        source = _make_source()
        # No new tickets — just trigger timeout check
        repo.mark_baseline_initialized("src-1", "2026-04-15T00:00:00Z")
        cycle.execute_source(source, [], "2026-04-15T00:00:00Z")

        reminder_calls = [s for s in notifier.sent if s["method"] == "send_approval_reminder"]
        assert len(reminder_calls) == 1
        assert reminder_calls[0]["count"] == 1
