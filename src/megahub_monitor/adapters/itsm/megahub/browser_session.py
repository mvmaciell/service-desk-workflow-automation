"""Playwright persistent browser session for MegaHub."""
from __future__ import annotations

from contextlib import contextmanager
from logging import Logger

from playwright.sync_api import sync_playwright

from ....config import BrowserContextConfig, Settings
from ....domain.errors import AuthenticationRequiredError


class BrowserSession:
    def __init__(
        self,
        settings: Settings,
        browser_context: BrowserContextConfig,
        logger: Logger,
    ) -> None:
        self.settings = settings
        self.browser_context = browser_context
        self.logger = logger

    @contextmanager
    def open_page(self, force_headed: bool = False):
        headless = False if force_headed else self.settings.browser_headless

        with sync_playwright() as playwright:
            context = playwright.chromium.launch_persistent_context(
                user_data_dir=str(self.browser_context.profile_dir),
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

    def interactive_login(self, login_url: str, validation_text: str) -> None:
        self.logger.info(
            "Abrindo navegador persistente para login manual no contexto '%s'.",
            self.browser_context.id,
        )
        with self.open_page(force_headed=True) as page:
            page.goto(login_url, wait_until="domcontentloaded")
            input(
                "Conclua o login manual no navegador aberto e pressione ENTER aqui "
                "quando a tela correta estiver visivel."
            )

            if not self.is_authenticated(page, validation_text):
                raise AuthenticationRequiredError(
                    f"A tela esperada '{validation_text}' nao ficou acessivel "
                    f"no contexto '{self.browser_context.id}'."
                )

    def is_authenticated(self, page, validation_text: str) -> bool:
        try:
            page.locator(f"text={validation_text}").first.wait_for(timeout=5000)
            return True
        except Exception:
            return False
