"""DOM constants and JS scripts used to scrape MegaHub ticket tables."""
from __future__ import annotations

HEADER_ALIASES: dict[str, str] = {
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
    "frente": "front",
    "criado": "created_label",
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
  const normalizeNoAccent = (value) => normalize(value)
    .normalize("NFD")
    .replace(/[\\u0300-\\u036f]/g, "")
    .toLowerCase();

  const tables = Array.from(document.querySelectorAll("table"));
  const candidates = tables.map((table) => {
    const headerRows = Array.from(table.querySelectorAll("thead tr"));
    const parsedHeaders = headerRows.map((row) =>
      Array.from(row.querySelectorAll("th")).map((th) => normalize(th.innerText))
    );

    const bestHeader = parsedHeaders.find((headers) => {
      const joined = headers.map((item) => normalizeNoAccent(item)).join(" | ");
      return joined.includes("chamado") && (
        joined.includes("titulo") ||
        joined.includes("prioridade") ||
        joined.includes("status")
      );
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

  // Extract detail links from each row (first <a> with href containing /Chamado/Exibir/)
  const rowLinks = Array.from(selected.table.querySelectorAll("tbody tr")).map((row) => {
    const link = row.querySelector('a[href*="/Chamado/Exibir/"]');
    return link ? link.href : "";
  });

  return {
    headers: selected.bestHeader,
    rows,
    rowLinks,
    bodyText: normalize(document.body.innerText),
  };
}
"""

PAGINATION_SCRIPT = """
() => {
  // MegaHub uses <ul class="pagination"> with <li class="page-item">
  // containing <div class="page-link"> (not <a> tags).
  // The active page has class "pagina-atual disabled".
  const container = document.querySelector('ul.pagination');
  if (!container) return { found: false };

  const items = Array.from(container.querySelectorAll('li.page-item'));
  for (let i = 0; i < items.length; i++) {
    if (items[i].classList.contains('pagina-atual')) {
      // Find next non-disabled sibling that is a page number or "›"
      for (let j = i + 1; j < items.length; j++) {
        if (!items[j].classList.contains('disabled')) {
          return { found: true, nextIndex: j };
        }
      }
    }
  }
  return { found: false };
}
"""

CLICK_NEXT_PAGE_SCRIPT = """
(info) => {
  const container = document.querySelector('ul.pagination');
  if (!container) return false;
  const items = Array.from(container.querySelectorAll('li.page-item'));
  if (info.nextIndex >= items.length) return false;

  const target = items[info.nextIndex];
  const clickable = target.querySelector('.page-link') || target;
  clickable.click();
  return true;
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
