"""MinhaFilaCollector — scrapes the personal queue (Minha Fila)."""
from __future__ import annotations

from playwright.sync_api import Page

from .collector_base import BaseQueueCollector


class MinhaFilaCollector(BaseQueueCollector):
    page_title = "Minha Fila"

    def apply_pre_filters(self, page: Page) -> None:
        self._ensure_checkbox(page, "Somente Abertos", self.source.only_open)
        self._ensure_checkbox(page, "Apenas chamados atribuidos a mim", self.source.only_assigned_to_me)
