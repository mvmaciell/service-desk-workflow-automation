"""Unit tests for TomlTeamCatalog."""
from __future__ import annotations

from pathlib import Path

import pytest

from src.megahub_monitor.adapters.catalog.toml_catalog import TomlTeamCatalog


TEAMS_TOML = """\
[[members]]
id = "dev-1"
name = "Alice"
role = "developer"
skills = ["abap", "fiori"]
active = true
webhook_url = "https://example.com/hook/alice"
max_concurrent_tickets = 5

[[members]]
id = "dev-2"
name = "Bob"
role = "developer"
skills = ["abap", "basis"]
active = true
webhook_url = ""
max_concurrent_tickets = 3

[[members]]
id = "dev-inactive"
name = "Carol"
role = "developer"
skills = ["fiori"]
active = false
webhook_url = ""
max_concurrent_tickets = 5

[[members]]
id = "coord-1"
name = "Coord One"
role = "coordinator"
skills = []
active = true
webhook_url = "https://example.com/hook/coord"
max_concurrent_tickets = 0

[allocation]
enabled = true
novo_status_labels = ["NOVO", "Novo"]
"""


@pytest.fixture
def catalog(tmp_path) -> TomlTeamCatalog:
    p = tmp_path / "teams.toml"
    p.write_text(TEAMS_TOML, encoding="utf-8")
    return TomlTeamCatalog(p)


class TestMissingFile:
    def test_missing_file_returns_empty_list(self, tmp_path):
        cat = TomlTeamCatalog(tmp_path / "nonexistent.toml")
        assert cat.list_active_members() == []

    def test_missing_file_get_member_returns_none(self, tmp_path):
        cat = TomlTeamCatalog(tmp_path / "nonexistent.toml")
        assert cat.get_member("dev-1") is None

    def test_missing_file_coordinator_returns_none(self, tmp_path):
        cat = TomlTeamCatalog(tmp_path / "nonexistent.toml")
        assert cat.get_coordinator() is None

    def test_missing_file_skill_lookup_returns_empty(self, tmp_path):
        cat = TomlTeamCatalog(tmp_path / "nonexistent.toml")
        assert cat.get_members_with_skill("abap") == []


class TestMemberParsing:
    def test_active_members_excludes_inactive(self, catalog):
        active = catalog.list_active_members()
        ids = {m.id for m in active}
        assert "dev-inactive" not in ids

    def test_active_members_count(self, catalog):
        # dev-1, dev-2, coord-1 are active; dev-inactive is not
        assert len(catalog.list_active_members()) == 3

    def test_member_fields_parsed(self, catalog):
        m = catalog.get_member("dev-1")
        assert m is not None
        assert m.name == "Alice"
        assert m.role == "developer"
        assert m.skills == ["abap", "fiori"]
        assert m.active is True
        assert m.webhook_url == "https://example.com/hook/alice"
        assert m.max_concurrent_tickets == 5

    def test_skills_normalized_lowercase(self, catalog):
        m = catalog.get_member("dev-1")
        for skill in m.skills:
            assert skill == skill.lower()

    def test_get_member_nonexistent_returns_none(self, catalog):
        assert catalog.get_member("ghost") is None


class TestSkillLookup:
    def test_abap_returns_two_devs(self, catalog):
        members = catalog.get_members_with_skill("abap")
        ids = {m.id for m in members}
        assert ids == {"dev-1", "dev-2"}

    def test_fiori_returns_only_active(self, catalog):
        # dev-1 has fiori; dev-inactive also has fiori but is inactive
        members = catalog.get_members_with_skill("fiori")
        ids = {m.id for m in members}
        assert "dev-inactive" not in ids
        assert "dev-1" in ids

    def test_skill_lookup_case_insensitive(self, catalog):
        members_lower = catalog.get_members_with_skill("abap")
        members_upper = catalog.get_members_with_skill("ABAP")
        assert {m.id for m in members_lower} == {m.id for m in members_upper}

    def test_unknown_skill_returns_empty(self, catalog):
        assert catalog.get_members_with_skill("java") == []


class TestCoordinator:
    def test_get_coordinator_returns_active_coordinator(self, catalog):
        coord = catalog.get_coordinator()
        assert coord is not None
        assert coord.id == "coord-1"
        assert coord.role == "coordinator"

    def test_no_coordinator_returns_none(self, tmp_path):
        p = tmp_path / "teams.toml"
        p.write_text('[[members]]\nid="d1"\nname="Dev"\nrole="developer"\nskills=[]\nactive=true\nwebhook_url=""\nmax_concurrent_tickets=5\n', encoding="utf-8")
        cat = TomlTeamCatalog(p)
        assert cat.get_coordinator() is None
