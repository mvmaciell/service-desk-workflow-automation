"""Unit tests for LoadAnalyzer (enhanced version with zero-load support)."""
from __future__ import annotations

import pytest

from src.megahub_monitor.application.services.load_analyzer import LoadAnalyzer
from src.megahub_monitor.domain.models import TeamMember


def _make_member(
    member_id: str,
    name: str,
    role: str = "developer",
    active: bool = True,
) -> TeamMember:
    return TeamMember(
        id=member_id,
        name=name,
        role=role,
        skills=[],
        active=active,
        webhook_url="",
        max_concurrent_tickets=5,
    )


class TestCalculateLegacy:
    """calculate_legacy must behave identically to the original services/load_analyzer.py."""

    def test_counts_by_consultant(self, make_ticket):
        analyzer = LoadAnalyzer()
        tickets = [
            make_ticket(consultant="Alice"),
            make_ticket(consultant="Alice"),
            make_ticket(consultant="Bob"),
        ]
        result = analyzer.calculate_legacy(tickets)
        by_name = {e.consultant: e.open_tickets for e in result}
        assert by_name["Alice"] == 2
        assert by_name["Bob"] == 1

    def test_skips_empty_consultant(self, make_ticket):
        analyzer = LoadAnalyzer()
        tickets = [make_ticket(consultant=""), make_ticket(consultant="Alice")]
        result = analyzer.calculate_legacy(tickets)
        assert len(result) == 1
        assert result[0].consultant == "Alice"

    def test_skips_dash_consultant(self, make_ticket):
        analyzer = LoadAnalyzer()
        tickets = [make_ticket(consultant="-"), make_ticket(consultant="Alice")]
        result = analyzer.calculate_legacy(tickets)
        assert len(result) == 1

    def test_sorted_by_count_descending_then_name(self, make_ticket):
        analyzer = LoadAnalyzer()
        tickets = [
            make_ticket(consultant="Zed"),
            make_ticket(consultant="Alice"),
            make_ticket(consultant="Alice"),
        ]
        result = analyzer.calculate_legacy(tickets)
        assert result[0].consultant == "Alice"  # 2 tickets
        assert result[1].consultant == "Zed"    # 1 ticket

    def test_empty_tickets_returns_empty(self):
        assert LoadAnalyzer().calculate_legacy([]) == []


class TestCalculateWithoutCatalog:
    """calculate() without members falls back to legacy behavior wrapped in EnhancedLoadEntry."""

    def test_returns_enhanced_load_entry(self, make_ticket):
        analyzer = LoadAnalyzer()
        result = analyzer.calculate([make_ticket(consultant="Alice")])
        assert len(result) == 1
        assert result[0].member_name == "Alice"
        assert result[0].open_tickets == 1

    def test_role_defaults_to_developer(self, make_ticket):
        analyzer = LoadAnalyzer()
        result = analyzer.calculate([make_ticket(consultant="Alice")])
        assert result[0].role == "developer"

    def test_member_id_empty_string(self, make_ticket):
        analyzer = LoadAnalyzer()
        result = analyzer.calculate([make_ticket(consultant="Alice")])
        assert result[0].member_id == ""


class TestCalculateWithCatalog:
    """calculate() with members catalog includes zero-load developers."""

    def test_zero_load_member_appears(self, make_ticket):
        analyzer = LoadAnalyzer()
        members = [
            _make_member("dev-1", "Alice"),
            _make_member("dev-2", "Bob"),  # no tickets
        ]
        tickets = [make_ticket(consultant="Alice")]
        result = analyzer.calculate(tickets, members=members)
        names = {e.member_name for e in result}
        assert "Alice" in names
        assert "Bob" in names

    def test_bob_has_zero_tickets(self, make_ticket):
        analyzer = LoadAnalyzer()
        members = [_make_member("dev-1", "Alice"), _make_member("dev-2", "Bob")]
        tickets = [make_ticket(consultant="Alice")]
        result = analyzer.calculate(tickets, members=members)
        bob = next(e for e in result if e.member_name == "Bob")
        assert bob.open_tickets == 0

    def test_inactive_members_excluded(self, make_ticket):
        analyzer = LoadAnalyzer()
        members = [
            _make_member("dev-1", "Alice"),
            _make_member("dev-inactive", "Carol", active=False),
        ]
        tickets = [make_ticket(consultant="Carol")]
        result = analyzer.calculate(tickets, members=members)
        names = {e.member_name for e in result}
        assert "Carol" not in names

    def test_coordinator_excluded(self, make_ticket):
        analyzer = LoadAnalyzer()
        members = [
            _make_member("dev-1", "Alice"),
            _make_member("coord-1", "Boss", role="coordinator"),
        ]
        tickets = [make_ticket(consultant="Alice")]
        result = analyzer.calculate(tickets, members=members)
        names = {e.member_name for e in result}
        assert "Boss" not in names

    def test_sorted_highest_load_first(self, make_ticket):
        analyzer = LoadAnalyzer()
        members = [
            _make_member("dev-1", "Alice"),
            _make_member("dev-2", "Bob"),
        ]
        tickets = [
            make_ticket(consultant="Bob"),
            make_ticket(consultant="Bob"),
            make_ticket(consultant="Alice"),
        ]
        result = analyzer.calculate(tickets, members=members)
        assert result[0].member_name == "Bob"
        assert result[1].member_name == "Alice"

    def test_member_id_populated(self, make_ticket):
        analyzer = LoadAnalyzer()
        members = [_make_member("dev-1", "Alice")]
        result = analyzer.calculate([make_ticket(consultant="Alice")], members=members)
        assert result[0].member_id == "dev-1"

    def test_empty_tickets_all_members_zero(self):
        analyzer = LoadAnalyzer()
        members = [_make_member("dev-1", "Alice"), _make_member("dev-2", "Bob")]
        result = analyzer.calculate([], members=members)
        assert len(result) == 2
        assert all(e.open_tickets == 0 for e in result)

    def test_empty_members_falls_back_to_legacy(self, make_ticket):
        analyzer = LoadAnalyzer()
        tickets = [make_ticket(consultant="Alice")]
        result = analyzer.calculate(tickets, members=[])
        assert len(result) == 1
        assert result[0].member_id == ""  # legacy path
