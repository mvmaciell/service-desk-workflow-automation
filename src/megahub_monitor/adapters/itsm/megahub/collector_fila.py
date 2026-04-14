"""FilaCollector — scrapes the shared MegaHub queue (Fila)."""
from __future__ import annotations

from playwright.sync_api import Page

from .collector_base import BaseQueueCollector


class FilaCollector(BaseQueueCollector):
    page_title = "Fila"

    def apply_pre_filters(self, page: Page) -> None:
        self._ensure_checkbox(page, "Incluir Fechados", self.source.include_closed)
        self._ensure_checkbox(page, "Incluir Atribuidos", self.source.include_assigned)
