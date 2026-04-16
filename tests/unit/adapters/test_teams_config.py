"""Unit tests for Settings._load_teams_config()."""
from __future__ import annotations

from src.megahub_monitor.config import Settings

FULL_ALLOCATION_TOML = """\
[[members]]
id = "dev-1"
name = "Alice"
role = "developer"
skills = []
active = true
webhook_url = ""
max_concurrent_tickets = 5

[allocation]
enabled = true
novo_status_labels = ["NOVO", "Novo", "novo"]
completion_status_labels = ["Fechado", "Cancelado"]
approval_timeout_minutes = 30
"""


class TestLoadTeamsConfig:
    def test_missing_file_returns_defaults(self, tmp_path):
        result = Settings._load_teams_config(tmp_path / "nonexistent.toml")
        assert result["enabled"] is False
        assert result["novo_status_labels"] == ["Novo"]
        assert "Fechado" in result["completion_status_labels"]
        assert "Não Homologado" in result["return_to_developer_labels"]
        assert result["approval_timeout_minutes"] == 60
        assert result["max_new_tickets_per_cycle"] == 10

    def test_allocation_enabled_true(self, tmp_path):
        p = tmp_path / "teams.toml"
        p.write_text(FULL_ALLOCATION_TOML, encoding="utf-8")
        result = Settings._load_teams_config(p)
        assert result["enabled"] is True

    def test_novo_status_labels_loaded(self, tmp_path):
        p = tmp_path / "teams.toml"
        p.write_text(FULL_ALLOCATION_TOML, encoding="utf-8")
        result = Settings._load_teams_config(p)
        assert result["novo_status_labels"] == ["NOVO", "Novo", "novo"]

    def test_completion_status_labels_loaded(self, tmp_path):
        p = tmp_path / "teams.toml"
        p.write_text(FULL_ALLOCATION_TOML, encoding="utf-8")
        result = Settings._load_teams_config(p)
        assert result["completion_status_labels"] == ["Fechado", "Cancelado"]

    def test_approval_timeout_loaded(self, tmp_path):
        p = tmp_path / "teams.toml"
        p.write_text(FULL_ALLOCATION_TOML, encoding="utf-8")
        result = Settings._load_teams_config(p)
        assert result["approval_timeout_minutes"] == 30

    def test_file_without_allocation_section_uses_defaults(self, tmp_path):
        p = tmp_path / "teams.toml"
        p.write_text('[[members]]\nid="d1"\nname="X"\nrole="developer"\nskills=[]\nactive=true\nwebhook_url=""\nmax_concurrent_tickets=5\n', encoding="utf-8")
        result = Settings._load_teams_config(p)
        assert result["enabled"] is False
        assert result["approval_timeout_minutes"] == 60
