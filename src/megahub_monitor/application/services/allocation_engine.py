"""AllocationEngine — deterministic developer ranking for ticket allocation.

Ranking cascade (first criterion wins on tie):
  1. skill_match     — member has a skill matching ticket.front (case-insensitive)
  2. current_load    — fewer open tickets ranks higher
  3. historical_load — fewer historically assigned tickets ranks higher
  4. alphabetical    — member name alphabetical tiebreak (deterministic)
"""
from __future__ import annotations

from ...domain.models import AllocationSuggestion, TeamMember, Ticket


class AllocationEngine:
    """Pure stateless ranking engine — no I/O, no side effects."""

    def rank(
        self,
        ticket: Ticket,
        members: list[TeamMember],
        current_load: dict[str, int],
        historical_load: dict[str, int] | None = None,
        max_suggestions: int = 3,
    ) -> list[AllocationSuggestion]:
        """Return up to *max_suggestions* ranked AllocationSuggestion objects.

        Args:
            ticket: The ticket to be allocated.
            members: Full team catalog (active devs are filtered internally).
            current_load: Mapping member_id → open ticket count.
            historical_load: Mapping member_id → all-time assigned count.
                             Defaults to empty (all zero).
            max_suggestions: Maximum number of suggestions to return.
        """
        if historical_load is None:
            historical_load = {}

        devs = [m for m in members if m.active and m.role == "developer"]
        if not devs:
            return []

        front_lower = ticket.front.strip().lower()

        def _sort_key(m: TeamMember) -> tuple:
            has_skill = front_lower and front_lower in m.skills
            return (
                0 if has_skill else 1,          # skill match first (0 = has skill)
                current_load.get(m.id, 0),       # lower current load first
                historical_load.get(m.id, 0),    # lower historical load first
                m.name.strip().lower(),           # alphabetical tiebreak
            )

        ranked = sorted(devs, key=_sort_key)[:max_suggestions]

        result: list[AllocationSuggestion] = []
        for position, member in enumerate(ranked, start=1):
            has_skill = front_lower and front_lower in member.skills
            skill_score = 1.0 if has_skill else 0.0
            load = current_load.get(member.id, 0)

            if has_skill:
                reason = f"skill match: {ticket.front}"
            elif load == min(current_load.get(d.id, 0) for d in devs):
                reason = "menor carga atual"
            else:
                reason = "ordem alfabetica"

            result.append(AllocationSuggestion(
                member_id=member.id,
                member_name=member.name,
                rank=position,
                reason=reason,
                current_load=load,
                skill_match_score=skill_score,
            ))

        return result
