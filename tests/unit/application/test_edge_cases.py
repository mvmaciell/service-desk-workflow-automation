"""Edge-case tests for P0/P1 fixes."""
from __future__ import annotations

import pytest

from src.megahub_monitor.application.services.allocation_engine import AllocationEngine
from src.megahub_monitor.application.services.load_analyzer import LoadAnalyzer
from src.megahub_monitor.config import _to_int
from src.megahub_monitor.domain.models import TeamMember, Ticket


def _make_ticket(**overrides) -> Ticket:
    defaults = {
        "number": "10001",
        "source_id": "s1",
        "source_name": "Fila",
        "source_kind": "fila",
        "consultant": "Alice",
        "front": "ABAP",
    }
    defaults.update(overrides)
    return Ticket(**defaults)


def _make_member(**overrides) -> TeamMember:
    defaults = {
        "id": "dev-1",
        "name": "Alice",
        "role": "developer",
        "skills": ["abap"],
        "active": True,
    }
    defaults.update(overrides)
    return TeamMember(**defaults)


class TestLoadAnalyzerCaseMismatch:
    """Verifica que a contagem de tickets e case-insensitive com o catalogo."""

    def test_case_insensitive_match(self):
        analyzer = LoadAnalyzer()
        tickets = [_make_ticket(consultant="ALICE"), _make_ticket(number="10002", consultant="alice")]
        members = [_make_member(name="Alice")]
        result = analyzer.calculate(tickets, members=members)
        assert len(result) == 1
        assert result[0].open_tickets == 2

    def test_mixed_case_consultants(self):
        analyzer = LoadAnalyzer()
        tickets = [
            _make_ticket(consultant="Bob Silva"),
            _make_ticket(number="10002", consultant="bob silva"),
            _make_ticket(number="10003", consultant="BOB SILVA"),
        ]
        members = [_make_member(id="dev-bob", name="Bob Silva", skills=[])]
        result = analyzer.calculate(tickets, members=members)
        assert result[0].open_tickets == 3


class TestAllocationEngineEmptyDevs:
    def test_rank_with_no_active_devs(self):
        engine = AllocationEngine()
        ticket = _make_ticket()
        inactive = [_make_member(active=False)]
        result = engine.rank(ticket, inactive, current_load={})
        assert result == []

    def test_rank_with_empty_members(self):
        engine = AllocationEngine()
        ticket = _make_ticket()
        result = engine.rank(ticket, [], current_load={})
        assert result == []


class TestToIntInvalidValues:
    def test_non_numeric_string_returns_default(self):
        assert _to_int("abc", 42) == 42

    def test_empty_string_returns_default(self):
        assert _to_int("", 10) == 10

    def test_none_returns_default(self):
        assert _to_int(None, 99) == 99

    def test_valid_int_string(self):
        assert _to_int("123", 0) == 123


class TestTeamMemberValidation:
    def test_negative_max_concurrent_raises(self):
        with pytest.raises(ValueError, match="max_concurrent_tickets"):
            _make_member(max_concurrent_tickets=-1)

    def test_zero_max_concurrent_allowed(self):
        m = _make_member(max_concurrent_tickets=0)
        assert m.max_concurrent_tickets == 0
