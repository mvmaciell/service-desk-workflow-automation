from __future__ import annotations

import sys
from pathlib import Path

import pytest

# Ensure src/ is on the path so imports like `from src.megahub_monitor...` work.
_project_root = Path(__file__).resolve().parent.parent
if str(_project_root) not in sys.path:
    sys.path.insert(0, str(_project_root))

from src.megahub_monitor.domain.models import Ticket


@pytest.fixture
def make_ticket():
    """Factory fixture that creates Ticket instances with sensible defaults."""

    def _factory(**overrides) -> Ticket:
        defaults = {
            "number": "10001",
            "source_id": "source-1",
            "source_name": "Minha Fila",
            "source_kind": "minha_fila",
            "title": "Chamado de teste",
            "ticket_type": "Incidente",
            "priority": "Alta",
            "ticket_status": "NOVO",
            "company": "Empresa ABC",
            "consultant": "Marcus Vinicius",
            "front": "ABAP",
            "collected_at": "2026-04-14T00:00:00+00:00",
        }
        defaults.update(overrides)
        return Ticket(**defaults)

    return _factory
