from __future__ import annotations

from logging import Logger

import requests

from ..config import Settings
from ..errors import ConfigurationError, NotificationError
from ..models import NotificationResult, Ticket, utc_now_iso


class TeamsWorkflowNotifier:
    def __init__(self, settings: Settings, logger: Logger) -> None:
        self.settings = settings
        self.logger = logger

    def send_ticket(self, ticket: Ticket) -> NotificationResult:
        payload = {
            "text": f"Novo chamado detectado na {ticket.source_view}: {ticket.short_text()}",
            "event_type": "new_ticket",
            "timestamp_utc": utc_now_iso(),
            "source_view": ticket.source_view,
            "consultant": ticket.consultant,
            "ticket": ticket.to_dict(),
        }
        return self._post(payload)

    def send_test_message(self) -> NotificationResult:
        payload = {
            "text": "Teste do monitor MegaHub: integracao com Teams/Power Automate ativa.",
            "event_type": "test_message",
            "timestamp_utc": utc_now_iso(),
            "source_view": self.settings.source_view_name,
            "consultant": self.settings.consultant_name,
        }
        return self._post(payload)

    def _post(self, payload: dict) -> NotificationResult:
        if not self.settings.teams_webhook_url:
            raise ConfigurationError("Defina TEAMS_WEBHOOK_URL no .env antes de enviar notificacoes.")

        try:
            response = requests.post(
                self.settings.teams_webhook_url,
                json=payload,
                timeout=self.settings.teams_request_timeout_seconds,
            )
        except requests.RequestException as exc:
            raise NotificationError(f"Falha de comunicacao com Teams/Workflow: {exc}") from exc

        success = 200 <= response.status_code < 300
        self.logger.info("Resposta do Teams/Workflow: HTTP %s", response.status_code)
        return NotificationResult(
            success=success,
            status_code=response.status_code,
            response_text=response.text.strip(),
            payload=payload,
        )
