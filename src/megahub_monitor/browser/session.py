from __future__ import annotations

from contextlib import contextmanager
from logging import Logger

from playwright.sync_api import Page, sync_playwright

from ..config import Settings
from ..errors import AuthenticationRequiredError


class BrowserSession:
    def __init__(self, settings: Settings, logger: Logger) -> None:
        self.settings = settings
        self.logger = logger

    @contextmanager
    def open_page(self, force_headed: bool = False):
        headless = False if force_headed else self.settings.browser_headless

        with sync_playwright() as playwright:
            context = playwright.chromium.launch_persistent_context(
                user_data_dir=str(self.settings.browser_profile_dir),
                channel=self.settings.playwright_channel,
                headless=headless,
                viewport={"width": 1600, "height": 1200},
                locale="pt-BR",
                args=["--start-maximized"],
            )

            page = context.pages[0] if context.pages else context.new_page()
            page.set_default_timeout(self.settings.playwright_timeout_ms)
            page.set_default_navigation_timeout(self.settings.playwright_timeout_ms)

            try:
                yield page
            finally:
                context.close()

    def interactive_login(self) -> None:
        self.logger.info("Abrindo navegador persistente para login manual.")
        with self.open_page(force_headed=True) as page:
            page.goto(self.settings.target_url, wait_until="domcontentloaded")
            input(
                "Conclua o login manual no navegador aberto e pressione ENTER aqui quando a tela 'Minha Fila' estiver visivel."
            )

            if not self.is_authenticated(page):
                raise AuthenticationRequiredError(
                    "A tela 'Minha Fila' nao ficou acessivel apos o login manual."
                )

    def is_authenticated(self, page: Page) -> bool:
        try:
            page.locator("text=Minha Fila").first.wait_for(timeout=5000)
            return True
        except Exception:
            return False

