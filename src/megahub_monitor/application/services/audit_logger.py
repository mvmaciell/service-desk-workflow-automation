"""AuditLogger — typed wrapper over StateRepository.record_audit_event()."""
from __future__ import annotations

from ...domain.enums import AuditAction
from ...domain.models import AuditEvent
from ...infrastructure.clock import Clock, SystemClock
from ...ports.state_repository import StateRepository


class AuditLogger:
    def __init__(self, repository: StateRepository, clock: Clock | None = None) -> None:
        self._repo = repository
        self._clock = clock or SystemClock()

    def log(
        self,
        action: AuditAction,
        actor: str = "system",
        ticket_number: str | None = None,
        source_id: str | None = None,
        details: dict | None = None,
    ) -> None:
        event = AuditEvent(
            timestamp=self._clock.now_iso(),
            action=action,
            actor=actor,
            ticket_number=ticket_number,
            source_id=source_id,
            details=details or {},
        )
        self._repo.record_audit_event(event)
