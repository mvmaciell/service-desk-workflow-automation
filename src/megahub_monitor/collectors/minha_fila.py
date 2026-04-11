from __future__ import annotations

import re
import unicodedata
from logging import Logger

from playwright.sync_api import Page

from ..config import Settings
from ..errors import AuthenticationRequiredError, CollectionError
from ..models import Ticket

HEADER_ALIASES = {
    "numero": "number",
    "numero chamado": "number",
    "chamado": "number",
    "n chamado cliente": "customer_ticket_number",
    "n ch cliente": "customer_ticket_number",
    "atividade": "activity",
    "titulo": "title",
    "status chamado": "ticket_status",
    "status": "ticket_status",
    "estimado disponivel": "available_estimate",
    "empresa": "company",
    "tipo": "ticket_type",
    "prioridade": "priority",
    "status atividade": "activity_status",
    "dt inicial atividade": "start_date",
    "dt final atividade": "end_date",
    "previsao chamado": "due_date",
    "previsao": "due_date",
    "horas a vencer": "time_to_expire",
    "consultor": "consultant",
}

TABLE_EXTRACTION_SCRIPT = """
() => {
  const normalize = (value) => (value || "").replace(/\\s+/g, " ").trim();
  const tables = Array.from(document.querySelectorAll("table"));

  const candidates = tables.map((table) => {
    const headerRows = Array.from(table.querySelectorAll("thead tr"));
    const parsedHeaders = headerRows.map((row) =>
      Array.from(row.querySelectorAll("th")).map((th) => normalize(th.innerText))
    );

    const bestHeader = parsedHeaders.find((headers) => {
      const joined = headers.join(" | ").toLowerCase();
      return joined.includes("chamado") && (joined.includes("titulo") || joined.includes("título"));
    }) || [];

    return { table, bestHeader };
  });

  const selected = candidates.find((item) => item.bestHeader.length > 0);
  if (!selected) {
    return {
      headers: [],
      rows: [],
      bodyText: normalize(document.body.innerText),
    };
  }

  const rows = Array.from(selected.table.querySelectorAll("tbody tr")).map((row) =>
    Array.from(row.querySelectorAll("td")).map((cell) => normalize(cell.innerText))
  );

  return {
    headers: selected.bestHeader,
    rows,
    bodyText: normalize(document.body.innerText),
  };
}
"""

CHECKBOX_SCRIPT = """
([labelText, expected]) => {
  const normalize = (value) => (value || "")
    .normalize("NFD")
    .replace(/[\\u0300-\\u036f]/g, "")
    .replace(/\\s+/g, " ")
    .trim()
    .toLowerCase();

  const target = normalize(labelText);
  const labels = Array.from(document.querySelectorAll("label"));

  for (const label of labels) {
    if (!normalize(label.innerText).includes(target)) {
      continue;
    }

    let input = label.control || label.querySelector('input[type="checkbox"]');

    if (!input && label.previousElementSibling && label.previousElementSibling.matches('input[type="checkbox"]')) {
      input = label.previousElementSibling;
    }

    if (!input && label.parentElement) {
      input = label.parentElement.querySelector('input[type="checkbox"]');
    }

    if (!input) {
      return { found: false, checked: false };
    }

    if (Boolean(input.checked) !== Boolean(expected)) {
      input.click();
    }

    return { found: true, checked: Boolean(input.checked) };
  }

  return { found: false, checked: false };
}
"""


def _normalize_text(value: str) -> str:
    normalized = unicodedata.normalize("NFD", value)
    normalized = "".join(char for char in normalized if unicodedata.category(char) != "Mn")
    normalized = normalized.lower()
    normalized = re.sub(r"[^a-z0-9]+", " ", normalized)
    return re.sub(r"\s+", " ", normalized).strip()


class MinhaFilaCollector:
    def __init__(self, settings: Settings, logger: Logger) -> None:
        self.settings = settings
        self.logger = logger

    def collect(self, page: Page) -> list[Ticket]:
        if not self.settings.first_page_only:
            self.logger.warning("FIRST_PAGE_ONLY=false ainda nao esta implementado. Usando apenas a primeira pagina.")

        page.goto(self.settings.target_url, wait_until="domcontentloaded")
        self._ensure_page_is_ready(page)
        self._ensure_checkbox(page, "Somente Abertos", self.settings.only_open)
        self._ensure_checkbox(page, "Apenas chamados atribuídos a mim", self.settings.only_assigned_to_me)
        self._apply_filters_if_possible(page)
        self._wait_for_grid(page)

        extracted = page.evaluate(TABLE_EXTRACTION_SCRIPT)
        tickets = self._build_tickets(extracted)
        self.logger.info("Captura concluida com %s chamado(s) visivel(is).", len(tickets))
        return tickets

    def _ensure_page_is_ready(self, page: Page) -> None:
        try:
            page.locator("text=Minha Fila").first.wait_for(timeout=self.settings.playwright_timeout_ms)
        except Exception as exc:
            raise AuthenticationRequiredError(
                "Nao foi possivel acessar a tela 'Minha Fila'. Verifique a sessao salva no perfil do navegador."
            ) from exc

    def _ensure_checkbox(self, page: Page, label_text: str, expected: bool) -> None:
        result = page.evaluate(CHECKBOX_SCRIPT, [label_text, expected])
        if result.get("found"):
            self.logger.info("Filtro '%s' ajustado para %s.", label_text, expected)

    def _apply_filters_if_possible(self, page: Page) -> None:
        try:
            button = page.get_by_role("button", name="Filtrar").first
            if button.is_visible():
                button.click()
                page.wait_for_load_state("networkidle", timeout=10000)
                return
        except Exception:
            pass

        page.wait_for_timeout(1000)

    def _wait_for_grid(self, page: Page) -> None:
        try:
            page.locator("table").last.wait_for(timeout=10000)
            page.wait_for_timeout(1500)
        except Exception as exc:
            raise CollectionError("A grade da fila nao ficou disponivel para leitura.") from exc

    def _build_tickets(self, extracted: dict) -> list[Ticket]:
        headers = extracted.get("headers") or []
        rows = extracted.get("rows") or []
        body_text = extracted.get("bodyText", "")

        if not headers and "Nenhum chamado encontrado" in body_text:
            return []

        if not headers:
            raise CollectionError("Nao foi possivel identificar a tabela principal da fila.")

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
                    title=canonical_fields.get("title", ""),
                    customer_ticket_number=canonical_fields.get("customer_ticket_number", ""),
                    activity=canonical_fields.get("activity", ""),
                    company=canonical_fields.get("company", ""),
                    ticket_type=canonical_fields.get("ticket_type", ""),
                    priority=canonical_fields.get("priority", ""),
                    ticket_status=canonical_fields.get("ticket_status", ""),
                    activity_status=canonical_fields.get("activity_status", ""),
                    available_estimate=canonical_fields.get("available_estimate", ""),
                    start_date=canonical_fields.get("start_date", ""),
                    end_date=canonical_fields.get("end_date", ""),
                    due_date=canonical_fields.get("due_date", ""),
                    time_to_expire=canonical_fields.get("time_to_expire", ""),
                    consultant=canonical_fields.get("consultant", self.settings.consultant_name),
                    source_view=self.settings.source_view_name,
                    raw_fields=raw_fields,
                )
            )

        return tickets

