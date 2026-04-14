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
