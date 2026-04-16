"""Tests for CheckApprovalTimeoutUseCase."""
from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone

from src.megahub_monitor.application.use_cases.check_approval_timeout import (
    CheckApprovalTimeoutUseCase,
)
from tests.fakes.fake_state_repository import FakeStateRepository


class _FakeClock:
    def __init__(self, now: datetime) -> None:
        self._now = now

    def now_iso(self) -> str:
        return self._now.isoformat()


def _make_repo_with_approval(created_at: str) -> FakeStateRepository:
    repo = FakeStateRepository()
    repo._pending_approvals.append({
        "ticket_number": "12345",
        "source_id": "src1",
        "created_at": created_at,
        "suggestions": [],
    })
    return repo


class TestCheckApprovalTimeout:
    def test_returns_empty_when_no_pending(self):
        repo = FakeStateRepository()
        uc = CheckApprovalTimeoutUseCase(repo, logging.getLogger(), timeout_minutes=60)
        assert uc.execute() == []

    def test_detects_timed_out_approval(self):
        two_hours_ago = (datetime.now(timezone.utc) - timedelta(hours=2)).isoformat()
        repo = _make_repo_with_approval(two_hours_ago)
        uc = CheckApprovalTimeoutUseCase(repo, logging.getLogger(), timeout_minutes=60)

        result = uc.execute()
        assert len(result) == 1
        assert result[0]["ticket_number"] == "12345"
        assert result[0]["elapsed_minutes"] >= 120

    def test_ignores_recent_approval(self):
        five_min_ago = (datetime.now(timezone.utc) - timedelta(minutes=5)).isoformat()
        repo = _make_repo_with_approval(five_min_ago)
        uc = CheckApprovalTimeoutUseCase(repo, logging.getLogger(), timeout_minutes=60)

        assert uc.execute() == []

    def test_does_not_remind_twice(self):
        two_hours_ago = (datetime.now(timezone.utc) - timedelta(hours=2)).isoformat()
        repo = _make_repo_with_approval(two_hours_ago)
        uc = CheckApprovalTimeoutUseCase(repo, logging.getLogger(), timeout_minutes=60)

        first = uc.execute()
        second = uc.execute()
        assert len(first) == 1
        assert len(second) == 0

    def test_logs_audit_event(self):
        two_hours_ago = (datetime.now(timezone.utc) - timedelta(hours=2)).isoformat()
        repo = _make_repo_with_approval(two_hours_ago)
        uc = CheckApprovalTimeoutUseCase(repo, logging.getLogger(), timeout_minutes=60)

        uc.execute()
        assert len(repo._audit_events) == 1
        assert repo._audit_events[0].action.value == "approval_timeout"

    def test_skips_approval_without_created_at(self):
        repo = FakeStateRepository()
        repo._pending_approvals.append({
            "ticket_number": "99999",
            "source_id": "src1",
            "suggestions": [],
        })
        uc = CheckApprovalTimeoutUseCase(repo, logging.getLogger(), timeout_minutes=60)
        assert uc.execute() == []
