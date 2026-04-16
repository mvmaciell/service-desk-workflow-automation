"""Tests for CLI status and bulk-approve commands."""
from __future__ import annotations

import pytest

from src.megahub_monitor.cli import build_parser


class TestBuildParser:
    def test_status_command_parses(self):
        parser = build_parser()
        args = parser.parse_args(["status"])
        assert args.command == "status"
        assert args.state is None

    def test_status_with_state_filter(self):
        parser = build_parser()
        args = parser.parse_args(["status", "--state", "ASSIGNED"])
        assert args.state == "ASSIGNED"

    def test_bulk_approve_parses_multiple(self):
        parser = build_parser()
        args = parser.parse_args(["bulk-approve", "123:dev-1", "456:dev-2"])
        assert args.command == "bulk-approve"
        assert args.approvals == ["123:dev-1", "456:dev-2"]
        assert args.source_id is None

    def test_bulk_approve_with_source(self):
        parser = build_parser()
        args = parser.parse_args(["bulk-approve", "123:dev-1", "--source", "src-1"])
        assert args.source_id == "src-1"

    def test_bulk_approve_requires_at_least_one(self):
        parser = build_parser()
        with pytest.raises(SystemExit):
            parser.parse_args(["bulk-approve"])
