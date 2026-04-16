"""Inspect pagination controls on the MegaHub queue page."""
from __future__ import annotations

import sys
from pathlib import Path

project_root = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(project_root))

from src.megahub_monitor.config import Settings  # noqa: E402
from playwright.sync_api import sync_playwright  # noqa: E402

settings = Settings.load()
source = settings.get_source("fila-geral")
context = settings.get_context(source.context_id)

INSPECT_SCRIPT = """
() => {
  const results = {};

  // 1. Find all pagination-related elements
  const paginationEls = document.querySelectorAll(
    '.pagination, [class*="paginat"], [class*="pager"], nav[aria-label*="page"], [class*="pagina"]'
  );
  results.paginationContainers = Array.from(paginationEls).map(el => ({
    tag: el.tagName,
    className: el.className,
    innerHTML: el.innerHTML.substring(0, 500),
    childCount: el.children.length,
  }));

  // 2. Look for page size selectors or "show all" buttons
  const selects = document.querySelectorAll('select');
  results.selects = Array.from(selects).map(sel => ({
    id: sel.id,
    name: sel.name,
    className: sel.className,
    options: Array.from(sel.options).map(o => ({ value: o.value, text: o.text.trim() })),
  }));

  // 3. Look for "Total" text to find the record count element
  const totalEl = Array.from(document.querySelectorAll('*')).find(
    el => el.children.length === 0 && /total.*\\d+.*registro/i.test(el.textContent)
  );
  if (totalEl) {
    results.totalElement = {
      tag: totalEl.tagName,
      className: totalEl.className,
      id: totalEl.id,
      text: totalEl.textContent.trim(),
      parentHTML: totalEl.parentElement ? totalEl.parentElement.innerHTML.substring(0, 300) : '',
    };
  }

  // 4. Look for links/buttons with page numbers
  const pageNumberLinks = Array.from(document.querySelectorAll('a, button')).filter(el => {
    const text = el.textContent.trim();
    return /^\\d+$/.test(text) && parseInt(text) <= 20;
  });
  results.pageNumberLinks = pageNumberLinks.slice(0, 20).map(el => ({
    tag: el.tagName,
    text: el.textContent.trim(),
    className: el.className,
    href: el.href || '',
    onclick: el.getAttribute('onclick') || '',
    parentClass: el.parentElement ? el.parentElement.className : '',
  }));

  // 5. Look for anything with "proximo", "next", "anterior", etc.
  const navButtons = Array.from(document.querySelectorAll('a, button')).filter(el => {
    const text = (el.textContent + ' ' + el.getAttribute('aria-label') + ' ' + el.getAttribute('title')).toLowerCase();
    return /prox|next|anterior|prev|>>|<<|›|‹/.test(text);
  });
  results.navButtons = navButtons.map(el => ({
    tag: el.tagName,
    text: el.textContent.trim().substring(0, 50),
    className: el.className,
    href: el.href || '',
    ariaLabel: el.getAttribute('aria-label') || '',
  }));

  // 6. Count table rows
  const tables = document.querySelectorAll('table');
  results.tableInfo = Array.from(tables).map(t => ({
    rowCount: t.querySelectorAll('tbody tr').length,
    className: t.className,
  }));

  return results;
}
"""

with sync_playwright() as pw:
    ctx = pw.chromium.launch_persistent_context(
        user_data_dir=str(context.profile_dir),
        channel=settings.playwright_channel,
        headless=True,
        viewport={"width": 1600, "height": 1200},
        locale="pt-BR",
    )
    page = ctx.pages[0] if ctx.pages else ctx.new_page()
    page.goto(source.url, wait_until="domcontentloaded")
    page.locator("text=Fila").first.wait_for(timeout=30000)

    # Click Filtrar to load the grid
    try:
        btn = page.get_by_role("button", name="Filtrar").first
        if btn.is_visible():
            btn.click()
            page.wait_for_load_state("networkidle", timeout=10000)
    except Exception:
        pass

    page.wait_for_timeout(2000)

    import json
    results = page.evaluate(INSPECT_SCRIPT)
    print(json.dumps(results, indent=2, ensure_ascii=False))

    ctx.close()
