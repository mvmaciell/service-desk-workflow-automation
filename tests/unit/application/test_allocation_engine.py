"""Unit tests for AllocationEngine ranking logic."""
from __future__ import annotations

import pytest

from src.megahub_monitor.application.services.allocation_engine import AllocationEngine
from src.megahub_monitor.domain.models import TeamMember, Ticket


def _member(mid: str, name: str, skills: list[str] | None = None, active: bool = True) -> TeamMember:
    return TeamMember(
        id=mid, name=name, role="developer",
        skills=[s.lower() for s in (skills or [])],
        active=active, webhook_url="", max_concurrent_tickets=5,
    )


def _ticket(front: str = "ABAP") -> Ticket:
    return Ticket(
        number="100", source_id="s1", source_name="Fila",
        source_kind="fila", title="Test", customer_ticket_number="",
        activity="", company="", front=front, created_label="",
        ticket_type="Incidente", priority="Alta", ticket_status="NOVO",
        activity_status="", available_estimate="", start_date="",
        end_date="", due_date="", time_to_expire="", consultant="",
        raw_fields={},
    )


class TestSkillMatch:
    def test_skill_match_ranks_first(self):
        engine = AllocationEngine()
        members = [_member("a", "Alpha"), _member("b", "Beta", skills=["abap"])]
        result = engine.rank(_ticket("abap"), members, {})
        assert result[0].member_id == "b"

    def test_skill_match_score_1_when_match(self):
        engine = AllocationEngine()
        members = [_member("a", "Alice", skills=["abap"])]
        result = engine.rank(_ticket("abap"), members, {})
        assert result[0].skill_match_score == 1.0

    def test_skill_match_score_0_when_no_match(self):
        engine = AllocationEngine()
        members = [_member("a", "Alice", skills=["fiori"])]
        result = engine.rank(_ticket("abap"), members, {})
        assert result[0].skill_match_score == 0.0

    def test_no_front_no_skill_advantage(self):
        engine = AllocationEngine()
        members = [_member("a", "Alice", skills=["abap"]), _member("b", "Beta")]
        result = engine.rank(_ticket(""), members, {})
        # Without front, skill match doesn't apply — alphabetical decides
        assert result[0].member_name == "Alice"


class TestCurrentLoad:
    def test_lower_load_wins_when_skills_equal(self):
        engine = AllocationEngine()
        members = [_member("a", "Alpha"), _member("b", "Beta")]
        load = {"a": 5, "b": 2}
        result = engine.rank(_ticket(""), members, load)
        assert result[0].member_id == "b"

    def test_load_in_suggestion(self):
        engine = AllocationEngine()
        members = [_member("a", "Alice")]
        result = engine.rank(_ticket(""), members, {"a": 3})
        assert result[0].current_load == 3

    def test_missing_load_defaults_to_zero(self):
        engine = AllocationEngine()
        members = [_member("a", "Alice")]
        result = engine.rank(_ticket(""), members, {})
        assert result[0].current_load == 0


class TestHistoricalLoad:
    def test_lower_historical_wins_on_load_tie(self):
        engine = AllocationEngine()
        members = [_member("a", "Alpha"), _member("b", "Beta")]
        load = {"a": 0, "b": 0}        # same current load
        hist = {"a": 20, "b": 5}
        result = engine.rank(_ticket(""), members, load, hist)
        assert result[0].member_id == "b"


class TestAlphabetical:
    def test_alphabetical_tiebreak(self):
        engine = AllocationEngine()
        members = [_member("z", "Zed"), _member("a", "Alice")]
        result = engine.rank(_ticket(""), members, {})
        assert result[0].member_name == "Alice"


class TestMaxSuggestions:
    def test_max_suggestions_respected(self):
        engine = AllocationEngine()
        members = [_member(str(i), f"Dev{i}") for i in range(10)]
        result = engine.rank(_ticket(""), members, {}, max_suggestions=3)
        assert len(result) == 3

    def test_fewer_members_than_max(self):
        engine = AllocationEngine()
        members = [_member("a", "Alice")]
        result = engine.rank(_ticket(""), members, {}, max_suggestions=3)
        assert len(result) == 1


class TestEdgeCases:
    def test_empty_members_returns_empty(self):
        result = AllocationEngine().rank(_ticket(), [], {})
        assert result == []

    def test_inactive_members_excluded(self):
        engine = AllocationEngine()
        members = [_member("a", "Alice", active=False)]
        result = engine.rank(_ticket(), members, {})
        assert result == []

    def test_rank_field_sequential(self):
        engine = AllocationEngine()
        members = [_member("a", "A"), _member("b", "B"), _member("c", "C")]
        result = engine.rank(_ticket(""), members, {}, max_suggestions=3)
        ranks = [s.rank for s in result]
        assert ranks == [1, 2, 3]

    def test_skill_beats_load(self):
        """Dev with skill and 5 tickets should beat dev without skill and 0 tickets."""
        engine = AllocationEngine()
        members = [
            _member("skilled", "Skilled Dev", skills=["abap"]),
            _member("unloaded", "Unloaded Dev", skills=[]),
        ]
        load = {"skilled": 5, "unloaded": 0}
        result = engine.rank(_ticket("abap"), members, load)
        assert result[0].member_id == "skilled"
