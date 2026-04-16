"""LoadAnalyzer — computes open ticket counts per team member.

Enhanced version of the original services/load_analyzer.py:
  - Legacy mode (no catalog): counts from visible tickets only (old behavior preserved)
  - Catalog mode: includes all active developers with zero tickets visible in load board
"""
from __future__ import annotations

from collections import Counter

from ...domain.models import EnhancedLoadEntry, LoadEntry, TeamMember, Ticket


class LoadAnalyzer:
    """Calculates open ticket workload.

    When `members` is provided, every active developer appears in the result
    even if they have zero tickets currently visible in the queue.
    When `members` is None or empty, falls back to legacy ticket-counting behavior.
    """

    def calculate(
        self,
        tickets: list[Ticket],
        members: list[TeamMember] | None = None,
        internal_assignments: dict[str, int] | None = None,
    ) -> list[EnhancedLoadEntry]:
        """Calculate open ticket load per developer.

        Args:
            tickets: All visible tickets from the source.
            members: Team catalog members (enables catalog mode).
            internal_assignments: Optional {member_id: count} of SDWA-internal
                allocations not yet reflected in the queue's consultant field.
                These are added on top of the queue-visible count.
        """
        counts: Counter[str] = Counter()

        for ticket in tickets:
            consultant = ticket.consultant.strip()
            if not consultant or consultant == "-":
                continue
            counts[consultant] += 1

        if members:
            return self._with_catalog(counts, members, internal_assignments)
        return self._legacy(counts)

    def calculate_legacy(self, tickets: list[Ticket]) -> list[LoadEntry]:
        """Original behavior — returns LoadEntry list for backward compat with existing code."""
        counts: Counter[str] = Counter()
        for ticket in tickets:
            consultant = ticket.consultant.strip()
            if not consultant or consultant == "-":
                continue
            counts[consultant] += 1
        ordered = sorted(counts.items(), key=lambda item: (-item[1], item[0].lower()))
        return [LoadEntry(consultant=name, open_tickets=count) for name, count in ordered]

    def _with_catalog(
        self,
        counts: Counter[str],
        members: list[TeamMember],
        internal_assignments: dict[str, int] | None = None,
    ) -> list[EnhancedLoadEntry]:
        """Build load board anchored to the team catalog.

        - All active developers appear, including those with zero tickets.
        - Ticket counts are matched by member.name (case-insensitive, stripped).
        - internal_assignments adds SDWA-tracked load not yet visible in queue.
        """
        name_to_member: dict[str, TeamMember] = {
            m.name.strip().lower(): m
            for m in members
            if m.active and m.role in ("developer",)
        }
        extra = internal_assignments or {}

        result: list[EnhancedLoadEntry] = []
        for name_lower, member in name_to_member.items():
            queue_count = counts.get(member.name.strip(), 0)
            internal_count = extra.get(member.id, 0)
            result.append(EnhancedLoadEntry(
                member_id=member.id,
                member_name=member.name,
                open_tickets=queue_count + internal_count,
                role=member.role,
            ))

        result.sort(key=lambda e: (-e.open_tickets, e.member_name.lower()))
        return result

    def _legacy(self, counts: Counter[str]) -> list[EnhancedLoadEntry]:
        """Ticket-based only — same sort order as original, wrapped in EnhancedLoadEntry."""
        ordered = sorted(counts.items(), key=lambda item: (-item[1], item[0].lower()))
        return [
            EnhancedLoadEntry(
                member_id="",
                member_name=name,
                open_tickets=count,
                role="developer",
            )
            for name, count in ordered
        ]
