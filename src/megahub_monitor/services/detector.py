# Shim — canonical implementation moved to application/use_cases/detect_new_tickets.py
# TicketDetector kept as alias for backward compat with existing run_once.py code.
from __future__ import annotations

from ..application.use_cases.detect_new_tickets import DetectNewTicketsUseCase  # noqa: F401

# Backward-compat alias
TicketDetector = DetectNewTicketsUseCase

__all__ = ["DetectNewTicketsUseCase", "TicketDetector"]
