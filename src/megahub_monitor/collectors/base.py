# Shim — canonical implementation moved to adapters/itsm/megahub/collector_base.py
from __future__ import annotations

from ..adapters.itsm.megahub.collector_base import BaseQueueCollector  # noqa: F401
from ..adapters.itsm.megahub.dom_constants import (  # noqa: F401
    CHECKBOX_SCRIPT,
    HEADER_ALIASES,
    TABLE_EXTRACTION_SCRIPT,
)

__all__ = ["BaseQueueCollector", "HEADER_ALIASES", "TABLE_EXTRACTION_SCRIPT", "CHECKBOX_SCRIPT"]
