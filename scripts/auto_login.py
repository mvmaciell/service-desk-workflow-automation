"""Auto-login: opens browser, waits for the queue page to be visible, then closes."""
from __future__ import annotations

import sys
from pathlib import Path

# Ensure project root is on sys.path
project_root = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(project_root))

from src.megahub_monitor.config import Settings  # noqa: E402

settings = Settings.load()
source = settings.get_source("fila-geral")
context = settings.get_context(source.context_id)

from playwright.sync_api import sync_playwright  # noqa: E402

print(f"Abrindo browser no contexto '{context.id}'...")
print(f"URL: {source.url}")
print("Aguardando pagina 'Fila' ficar visivel (timeout 90s)...")

with sync_playwright() as pw:
    ctx = pw.chromium.launch_persistent_context(
        user_data_dir=str(context.profile_dir),
        channel=settings.playwright_channel,
        headless=False,
        viewport={"width": 1600, "height": 1200},
        locale="pt-BR",
        args=["--start-maximized"],
    )
    page = ctx.pages[0] if ctx.pages else ctx.new_page()
    page.goto(source.url, wait_until="domcontentloaded")

    try:
        page.locator("text=Fila").first.wait_for(timeout=90000)
        print("Pagina 'Fila' detectada! Sessao persistida com sucesso.")
    except Exception:
        print("AVISO: Timeout atingido. Se voce fez login, a sessao foi salva mesmo assim.")

    # Small wait to ensure cookies/state are flushed to disk
    page.wait_for_timeout(2000)
    ctx.close()

print("Browser fechado. Sessao salva em:", context.profile_dir)
print("Agora rode: python main.py snapshot --source fila-geral")
