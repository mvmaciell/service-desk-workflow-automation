from __future__ import annotations

from datetime import datetime, timezone
from typing import Protocol


class Clock(Protocol):
    def now_iso(self) -> str: ...


class SystemClock:
    def now_iso(self) -> str:
        return datetime.now(timezone.utc).isoformat()
