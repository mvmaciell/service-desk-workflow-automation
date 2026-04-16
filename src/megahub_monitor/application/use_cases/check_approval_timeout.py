"""CheckApprovalTimeoutUseCase — sends reminders for stale pending approvals."""
from __future__ import annotations

from datetime import datetime, timezone
from logging import Logger

from ...domain.enums import AuditAction
from ...infrastructure.clock import Clock, SystemClock
from ...ports.state_repository import StateRepository
from ..services.audit_logger import AuditLogger


class CheckApprovalTimeoutUseCase:
    """Checks for pending approvals that exceeded the timeout window.

    Runs each cycle. For each timed-out approval:
      1. Logs an APPROVAL_TIMEOUT audit event (only once per ticket).
      2. Returns the list of timed-out approvals so the caller can notify.
    """

    def __init__(
        self,
        repository: StateRepository,
        logger: Logger,
        timeout_minutes: int = 60,
        clock: Clock | None = None,
    ) -> None:
        self._repo = repository
        self._logger = logger
        self._timeout_minutes = timeout_minutes
        self._clock = clock or SystemClock()
        self._audit = AuditLogger(repository, clock)
        self._already_reminded: set[tuple[str, str]] = set()

    def execute(self) -> list[dict]:
        """Return pending approvals that exceeded the timeout.

        Each dict has keys: ticket_number, source_id, created_at,
        suggestions_json, elapsed_minutes.
        """
        pending = self._repo.get_pending_approvals()
        if not pending:
            return []

        now = datetime.now(timezone.utc)
        timed_out: list[dict] = []

        for approval in pending:
            created_at = approval.get("created_at", "")
            if not created_at:
                continue

            try:
                created_dt = datetime.fromisoformat(created_at)
                if created_dt.tzinfo is None:
                    created_dt = created_dt.replace(tzinfo=timezone.utc)
            except (ValueError, TypeError):
                continue

            elapsed = (now - created_dt).total_seconds() / 60
            if elapsed < self._timeout_minutes:
                continue

            key = (approval["ticket_number"], approval["source_id"])
            if key in self._already_reminded:
                continue

            self._already_reminded.add(key)

            self._audit.log(
                action=AuditAction.APPROVAL_TIMEOUT,
                ticket_number=approval["ticket_number"],
                source_id=approval["source_id"],
                details={"elapsed_minutes": round(elapsed), "timeout_minutes": self._timeout_minutes},
            )

            self._logger.warning(
                "Chamado %s: aprovacao pendente ha %d minutos (limite: %d).",
                approval["ticket_number"],
                round(elapsed),
                self._timeout_minutes,
            )

            entry = dict(approval)
            entry["elapsed_minutes"] = round(elapsed)
            timed_out.append(entry)

        return timed_out
