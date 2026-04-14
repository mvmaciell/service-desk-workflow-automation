"""Tests for DetectNewTicketsUseCase — the most critical tests in the project.

These tests validate the fix for the baseline bug where tickets with status
"NOVO" already in the queue on first run were silenced forever.
"""
from __future__ import annotations

import logging

import pytest

from src.megahub_monitor.application.use_cases.detect_new_tickets import DetectNewTicketsUseCase
from src.megahub_monitor.config import SourceConfig
from tests.fakes.fake_state_repository import FakeStateRepository


def _make_source(source_id: str = "src-1") -> SourceConfig:
    return SourceConfig(
        id=source_id,
        name="Test Source",
        kind="minha_fila",
        context_id="ctx-1",
        url="https://example.com",
    )


def _make_use_case(
    repo: FakeStateRepository | None = None,
    novo_labels: list[str] | None = None,
) -> tuple[DetectNewTicketsUseCase, FakeStateRepository]:
    if repo is None:
        repo = FakeStateRepository()
    uc = DetectNewTicketsUseCase(
        repository=repo,
        logger=logging.getLogger("test"),
        novo_status_labels=novo_labels or ["NOVO"],
    )
    return uc, repo


AT = "2026-04-14T00:00:00+00:00"


class TestFirstRunV2:
    """First run with new v2 baseline — NOVO tickets are surfaced, not silenced."""

    def test_returns_is_baseline_true(self, make_ticket):
        uc, _ = _make_use_case()
        result = uc.execute(_make_source(), [make_ticket(number="1")], AT)
        assert result.is_baseline is True

    def test_novo_tickets_in_new_tickets(self, make_ticket):
        uc, _ = _make_use_case()
        tickets = [
            make_ticket(number="1", ticket_status="NOVO"),
            make_ticket(number="2", ticket_status="NOVO"),
            make_ticket(number="3", ticket_status="Em andamento"),
        ]
        result = uc.execute(_make_source(), tickets, AT)
        assert len(result.new_tickets) == 2
        assert {t.number for t in result.new_tickets} == {"1", "2"}

    def test_non_novo_tickets_not_surfaced(self, make_ticket):
        uc, _ = _make_use_case()
        tickets = [
            make_ticket(number="1", ticket_status="Em andamento"),
            make_ticket(number="2", ticket_status="Atribuido"),
        ]
        result = uc.execute(_make_source(), tickets, AT)
        assert result.new_tickets == []

    def test_all_tickets_marked_seen_regardless(self, make_ticket):
        """Even non-NOVO tickets are marked seen so they don't alert on next run."""
        uc, repo = _make_use_case()
        tickets = [
            make_ticket(number="1", ticket_status="NOVO"),
            make_ticket(number="2", ticket_status="Em andamento"),
        ]
        uc.execute(_make_source(), tickets, AT)
        known = repo.get_known_numbers("src-1", ["1", "2"])
        assert known == {"1", "2"}

    def test_baseline_marked_v2(self, make_ticket):
        uc, repo = _make_use_case()
        uc.execute(_make_source(), [make_ticket()], AT)
        assert repo.get_baseline_version("src-1") == 2

    def test_total_tickets_correct(self, make_ticket):
        uc, _ = _make_use_case()
        tickets = [make_ticket(number=str(i)) for i in range(5)]
        result = uc.execute(_make_source(), tickets, AT)
        assert result.total_tickets == 5

    def test_custom_novo_labels(self, make_ticket):
        uc, _ = _make_use_case(novo_labels=["NOVO", "Novo", "novo"])
        tickets = [
            make_ticket(number="1", ticket_status="Novo"),
            make_ticket(number="2", ticket_status="NOVO"),
            make_ticket(number="3", ticket_status="novo"),
            make_ticket(number="4", ticket_status="Aberto"),
        ]
        result = uc.execute(_make_source(), tickets, AT)
        assert len(result.new_tickets) == 3

    def test_empty_queue_no_new_tickets(self):
        uc, _ = _make_use_case()
        result = uc.execute(_make_source(), [], AT)
        assert result.new_tickets == []
        assert result.total_tickets == 0


class TestSubsequentRuns:
    """After baseline: only genuinely new ticket numbers generate alerts."""

    def test_no_new_tickets_when_all_known(self, make_ticket):
        uc, repo = _make_use_case()
        tickets = [make_ticket(number="1", ticket_status="NOVO")]
        # First run — initializes baseline
        uc.execute(_make_source(), tickets, AT)
        # Second run — same ticket, should not re-alert
        result = uc.execute(_make_source(), tickets, "2026-04-14T01:00:00+00:00")
        assert result.is_baseline is False
        assert result.new_tickets == []

    def test_new_ticket_number_detected(self, make_ticket):
        uc, repo = _make_use_case()
        uc.execute(_make_source(), [make_ticket(number="1")], AT)
        # Second run adds ticket "2"
        result = uc.execute(
            _make_source(),
            [make_ticket(number="1"), make_ticket(number="2")],
            "2026-04-14T01:00:00+00:00",
        )
        assert len(result.new_tickets) == 1
        assert result.new_tickets[0].number == "2"

    def test_status_irrelevant_on_subsequent_runs(self, make_ticket):
        """On subsequent runs, new_tickets is based on number, not status."""
        uc, _ = _make_use_case()
        uc.execute(_make_source(), [make_ticket(number="1")], AT)
        result = uc.execute(
            _make_source(),
            [make_ticket(number="2", ticket_status="Em andamento")],
            "2026-04-14T01:00:00+00:00",
        )
        # "2" is new (by number) regardless of status
        assert len(result.new_tickets) == 1

    def test_is_baseline_false(self, make_ticket):
        uc, _ = _make_use_case()
        uc.execute(_make_source(), [make_ticket()], AT)
        result = uc.execute(_make_source(), [make_ticket()], "2026-04-14T01:00:00+00:00")
        assert result.is_baseline is False


class TestLegacyV1Behavior:
    """Sources initialized with baseline_version=1 keep the old silencing behavior."""

    def test_v1_source_subsequent_run_works_normally(self, make_ticket):
        """Simulate an already-initialized v1 source — subsequent runs work fine."""
        _, repo = _make_use_case()
        # Manually mark as v1 baseline (old deployment)
        repo.mark_baseline_initialized("src-1", AT, baseline_version=1)
        repo.upsert_seen_tickets("src-1", [make_ticket(number="1")], AT)

        uc = DetectNewTicketsUseCase(
            repository=repo,
            logger=logging.getLogger("test"),
            novo_status_labels=["NOVO"],
        )
        # A new ticket appears
        result = uc.execute(
            _make_source(),
            [make_ticket(number="1"), make_ticket(number="2")],
            "2026-04-14T01:00:00+00:00",
        )
        assert len(result.new_tickets) == 1
        assert result.new_tickets[0].number == "2"

    def test_v1_source_does_not_re_baseline(self, make_ticket):
        """A v1 source must not be re-initialized on next call."""
        _, repo = _make_use_case()
        repo.mark_baseline_initialized("src-1", AT, baseline_version=1)

        uc = DetectNewTicketsUseCase(
            repository=repo,
            logger=logging.getLogger("test"),
        )
        result = uc.execute(_make_source(), [make_ticket(number="99")], "2026-04-14T01:00:00+00:00")
        assert result.is_baseline is False


class TestShimBackwardCompat:
    """The old services/detector.py shim must still export TicketDetector."""

    def test_ticket_detector_alias_importable(self):
        from src.megahub_monitor.services.detector import TicketDetector
        assert TicketDetector is DetectNewTicketsUseCase

    def test_detect_new_tickets_use_case_importable(self):
        from src.megahub_monitor.services.detector import DetectNewTicketsUseCase as UC
        assert UC is DetectNewTicketsUseCase
