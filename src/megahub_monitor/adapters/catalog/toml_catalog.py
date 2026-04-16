"""TeamCatalog adapter backed by a TOML file (config/teams.toml)."""
from __future__ import annotations

import tomllib
from pathlib import Path

from ...domain.models import TeamMember
from ...ports.team_catalog import TeamCatalog


class TomlTeamCatalog(TeamCatalog):
    """Reads team members from a TOML file.

    If the file does not exist, returns empty lists (graceful fallback).
    Members are loaded once at construction time.
    """

    def __init__(self, teams_path: Path) -> None:
        self._members: dict[str, TeamMember] = {}
        if teams_path.exists():
            self._load(teams_path)

    def _load(self, path: Path) -> None:
        with path.open("rb") as fh:
            document = tomllib.load(fh)

        for raw in document.get("members", []):
            member_id = str(raw["id"]).strip()
            member = TeamMember(
                id=member_id,
                name=str(raw.get("name", member_id)).strip(),
                role=str(raw.get("role", "developer")).strip().lower(),
                skills=[str(s).strip().lower() for s in raw.get("skills", [])],
                active=bool(raw.get("active", True)),
                webhook_url=str(raw.get("webhook_url", "")).strip(),
                max_concurrent_tickets=int(raw.get("max_concurrent_tickets", 5)),
                managed_fronts=[str(f).strip().lower() for f in raw.get("managed_fronts", [])],
            )
            self._members[member_id] = member

    def list_active_members(self) -> list[TeamMember]:
        return [m for m in self._members.values() if m.active]

    def get_member(self, member_id: str) -> TeamMember | None:
        return self._members.get(member_id)

    def get_members_with_skill(self, skill: str) -> list[TeamMember]:
        skill_lower = skill.strip().lower()
        return [m for m in self._members.values() if m.active and skill_lower in m.skills]

    def get_coordinator(self) -> TeamMember | None:
        for m in self._members.values():
            if m.active and m.role == "coordinator":
                return m
        return None
