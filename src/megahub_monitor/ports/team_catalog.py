from __future__ import annotations

from abc import ABC, abstractmethod

from ..domain.models import TeamMember


class TeamCatalog(ABC):
    @abstractmethod
    def list_active_members(self) -> list[TeamMember]: ...

    @abstractmethod
    def get_member(self, member_id: str) -> TeamMember | None: ...

    @abstractmethod
    def get_members_with_skill(self, skill: str) -> list[TeamMember]: ...

    @abstractmethod
    def get_coordinator(self) -> TeamMember | None: ...
