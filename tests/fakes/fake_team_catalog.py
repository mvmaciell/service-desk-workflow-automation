from __future__ import annotations

from src.megahub_monitor.domain.models import TeamMember
from src.megahub_monitor.ports.team_catalog import TeamCatalog


class FakeTeamCatalog(TeamCatalog):
    def __init__(self, members: list[TeamMember] | None = None) -> None:
        self._members = members or []

    def list_active_members(self) -> list[TeamMember]:
        return [m for m in self._members if m.active]

    def get_member(self, member_id: str) -> TeamMember | None:
        for m in self._members:
            if m.id == member_id:
                return m
        return None

    def get_members_with_skill(self, skill: str) -> list[TeamMember]:
        skill_lower = skill.lower()
        return [
            m for m in self._members
            if m.active and any(s.lower() == skill_lower for s in m.skills)
        ]

    def get_coordinator(self) -> TeamMember | None:
        for m in self._members:
            if m.active and m.role == "coordinator":
                return m
        return None
