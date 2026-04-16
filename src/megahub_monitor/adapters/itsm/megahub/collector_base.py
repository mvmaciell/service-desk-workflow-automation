"""Base HTML collector for MegaHub ticket queues."""
from __future__ import annotations

import re
import unicodedata
from logging import Logger

from playwright.sync_api import Error as PlaywrightError, Page, TimeoutError as PlaywrightTimeoutError

from ....config import Settings, SourceConfig
from ....domain.errors import AuthenticationRequiredError, CollectionError
from ....domain.models import Ticket
from .dom_constants import CHECKBOX_SCRIPT, HEADER_ALIASES, TABLE_EXTRACTION_SCRIPT


def _normalize_text(value: str) -> str:
    normalized = unicodedata.normalize("NFD", value)
    normalized = "".join(char for char in normalized if unicodedata.category(char) != "Mn")
    normalized = normalized.lower()
    normalized = re.sub(r"[^a-z0-9]+", " ", normalized)
    return re.sub(r"\s+", " ", normalized).strip()


class BaseQueueCollector:
    page_title = ""

    def __init__(self, settings: Settings, source: SourceConfig, logger: Logger) -> None:
        self.settings = settings
        self.source = source
        self.logger = logger

    def collect(self, page: Page) -> list[Ticket]:
        if not self.source.first_page_only:
            self.logger.warning(
                "A leitura alem da primeira pagina ainda nao esta implementada para '%s'.",
                self.source.id,
            )

        page.goto(self.source.url, wait_until="domcontentloaded")
        self._ensure_page_is_ready(page)
        self.apply_pre_filters(page)
        self._apply_filters_if_possible(page)
        self._wait_for_grid(page)

        extracted = page.evaluate(TABLE_EXTRACTION_SCRIPT)
        tickets = self._build_tickets(extracted)
        self.logger.info(
            "Captura concluida para '%s' com %s chamado(s) visivel(is).",
            self.source.id,
            len(tickets),
        )
        return tickets

    def apply_pre_filters(self, page: Page) -> None:
        return None

    def _ensure_page_is_ready(self, page: Page) -> None:
        try:
            page.locator(f"text={self.page_title}").first.wait_for(
                timeout=self.settings.playwright_timeout_ms
            )
        except PlaywrightTimeoutError as exc:
            raise AuthenticationRequiredError(
                f"Nao foi possivel acessar a tela '{self.page_title}' "
                f"para a fonte '{self.source.id}'."
            ) from exc

    def _ensure_checkbox(self, page: Page, label_text: str, expected: bool) -> None:
        result = page.evaluate(CHECKBOX_SCRIPT, [label_text, expected])
        if result.get("found"):
            self.logger.info(
                "Fonte '%s': filtro '%s' ajustado para %s.",
                self.source.id,
                label_text,
                expected,
            )

    def _apply_filters_if_possible(self, page: Page) -> None:
        try:
            button = page.get_by_role("button", name="Filtrar").first
            if button.is_visible():
                button.click()
                page.wait_for_load_state("networkidle", timeout=10000)
                return
        except (PlaywrightTimeoutError, PlaywrightError):
            pass

        page.wait_for_timeout(1000)

    def _wait_for_grid(self, page: Page) -> None:
        try:
            page.locator("table").last.wait_for(timeout=10000)
            page.wait_for_timeout(1500)
        except PlaywrightTimeoutError as exc:
            raise CollectionError(
                f"A grade da fonte '{self.source.id}' nao ficou disponivel para leitura."
            ) from exc

    def _build_tickets(self, extracted: dict) -> list[Ticket]:
        headers = extracted.get("headers") or []
        rows = extracted.get("rows") or []
        body_text = extracted.get("bodyText", "")

        if not headers and "Nenhum chamado encontrado" in body_text:
            return []

        if not headers:
            raise CollectionError(
                f"Nao foi possivel identificar a tabela principal da fonte '{self.source.id}'."
            )

        normalized_headers = [_normalize_text(header) for header in headers]
        tickets: list[Ticket] = []
        seen_numbers: set[str] = set()

        for row in rows:
            if not row:
                continue
            if len(row) == 1 and "Nenhum chamado encontrado" in row[0]:
                continue

            raw_fields: dict[str, str] = {}
            canonical_fields: dict[str, str] = {}

            for index, cell in enumerate(row):
                if index >= len(headers):
                    break

                raw_header = headers[index].strip()
                normalized_header = normalized_headers[index]
                cell_value = cell.strip()

                if not raw_header:
                    continue

                raw_fields[raw_header] = cell_value
                canonical_name = HEADER_ALIASES.get(normalized_header)
                if canonical_name and cell_value:
                    canonical_fields[canonical_name] = cell_value

            number = canonical_fields.get("number", "").strip()
            if not number or number in seen_numbers:
                continue
            if not any(character.isdigit() for character in number):
                continue

            seen_numbers.add(number)
            tickets.append(
                Ticket(
                    number=number,
                    source_id=self.source.id,
                    source_name=self.source.name,
                    source_kind=self.source.kind,
                    title=canonical_fields.get("title", ""),
                    customer_ticket_number=canonical_fields.get("customer_ticket_number", ""),
                    activity=canonical_fields.get("activity", ""),
                    company=canonical_fields.get("company", ""),
                    front=canonical_fields.get("front", ""),
                    created_label=canonical_fields.get("created_label", ""),
                    ticket_type=canonical_fields.get("ticket_type", ""),
                    priority=canonical_fields.get("priority", ""),
                    ticket_status=canonical_fields.get("ticket_status", ""),
                    activity_status=canonical_fields.get("activity_status", ""),
                    available_estimate=canonical_fields.get("available_estimate", ""),
                    start_date=canonical_fields.get("start_date", ""),
                    end_date=canonical_fields.get("end_date", ""),
                    due_date=canonical_fields.get("due_date", ""),
                    time_to_expire=canonical_fields.get("time_to_expire", ""),
                    consultant=canonical_fields.get("consultant", self.source.consultant_name),
                    raw_fields=raw_fields,
                )
            )

        return tickets
