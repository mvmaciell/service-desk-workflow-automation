"""MegaHubReader — ITSMReader implementation backed by Playwright scraping."""
from __future__ import annotations

from logging import Logger

from ....config import Settings
from ....domain.models import Ticket
from ....ports.itsm_reader import ITSMReader
from .browser_session import BrowserSession
from .collector_fila import FilaCollector
from .collector_minha_fila import MinhaFilaCollector


_COLLECTOR_MAP = {
    "minha_fila": MinhaFilaCollector,
    "fila": FilaCollector,
}


class MegaHubReader(ITSMReader):
    """Reads ticket queues from MegaHub via Playwright browser scraping."""

    def __init__(self, settings: Settings, logger: Logger) -> None:
        self._settings = settings
        self._logger = logger

    def read_queue(self, source_id: str) -> list[Ticket]:
        source = self._settings.get_source(source_id)
        context_cfg = self._settings.get_context(source.context_id)
        session = BrowserSession(self._settings, context_cfg, self._logger)

        collector_cls = _COLLECTOR_MAP.get(source.kind)
        if collector_cls is None:
            raise ValueError(f"Tipo de fonte nao suportado pelo MegaHubReader: '{source.kind}'")

        collector = collector_cls(self._settings, source, self._logger)

        with session.open_page() as page:
            return collector.collect(page)

    def read_ticket_status(self, source_id: str, ticket_number: str) -> str | None:
        """Not yet implemented — MegaHub does not expose a direct ticket status API."""
        return None

    def interactive_login(self, source_id: str) -> None:
        source = self._settings.get_source(source_id)
        context_cfg = self._settings.get_context(source.context_id)
        session = BrowserSession(self._settings, context_cfg, self._logger)
        session.interactive_login(source.url, "Minha Fila")
