from __future__ import annotations

from logging import Logger

import requests

from ..config import Settings
from ..domain.errors import ConfigurationError, NotificationError
from ..domain.models import DeliveryRequest, NotificationResult, utc_now_iso


class TeamsWorkflowNotifier:
    def __init__(self, settings: Settings, logger: Logger) -> None:
        self.settings = settings
        self.logger = logger

    def send_delivery(self, delivery: DeliveryRequest) -> NotificationResult:
        payload = self._build_delivery_card(delivery)
        return self._post(payload, delivery.webhook_url)

    def send_test_message(
        self,
        recipient_name: str,
        recipient_role: str,
        webhook_url: str,
    ) -> NotificationResult:
        payload = self._build_test_card(recipient_name, recipient_role)
        return self._post(payload, webhook_url)

    def _post(self, payload: dict, webhook_url: str) -> NotificationResult:
        if not webhook_url:
            raise ConfigurationError("Webhook do Teams nao configurado para o destinatario.")

        try:
            response = requests.post(
                webhook_url,
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

    def _build_test_card(self, recipient_name: str, recipient_role: str) -> dict:
        now = utc_now_iso()
        return {
            "$schema": "http://adaptivecards.io/schemas/adaptive-card.json",
            "type": "AdaptiveCard",
            "version": "1.4",
            "msteams": {"width": "Full"},
            "body": [
                {
                    "type": "TextBlock",
                    "text": "Teste MegaHub",
                    "weight": "Bolder",
                    "size": "Medium",
                    "wrap": True,
                },
                {
                    "type": "FactSet",
                    "facts": [
                        {"title": "Destinatario", "value": recipient_name},
                        {"title": "Perfil", "value": recipient_role},
                        {"title": "Executado em", "value": now},
                    ],
                },
            ],
        }

    def _build_delivery_card(self, delivery: DeliveryRequest) -> dict:
        ticket = delivery.ticket
        facts = [
            {"title": "Destinatario", "value": delivery.recipient_name},
            {"title": "Perfil", "value": delivery.recipient_role},
            {"title": "Fonte", "value": delivery.source_name},
            {"title": "Chamado", "value": ticket.number},
            {"title": "Tipo", "value": ticket.ticket_type or "-"},
            {"title": "Prioridade", "value": ticket.priority or "-"},
            {"title": "Status", "value": ticket.ticket_status or "-"},
            {"title": "Empresa", "value": ticket.company or "-"},
            {"title": "Consultor", "value": ticket.consultant or "-"},
        ]

        if ticket.activity_status:
            facts.append({"title": "Status atividade", "value": ticket.activity_status})
        if ticket.front:
            facts.append({"title": "Frente", "value": ticket.front})
        if ticket.due_date:
            facts.append({"title": "Previsao", "value": ticket.due_date})
        if ticket.time_to_expire:
            facts.append({"title": "Horas a vencer", "value": ticket.time_to_expire})

        body: list[dict] = [
            {
                "type": "TextBlock",
                "text": delivery.title_prefix,
                "weight": "Bolder",
                "size": "Medium",
                "wrap": True,
            },
            {
                "type": "TextBlock",
                "text": ticket.title or "Sem titulo",
                "wrap": True,
            },
            {
                "type": "FactSet",
                "facts": facts,
            },
        ]

        if delivery.load_entries:
            load_facts = [
                {"title": entry.consultant, "value": str(entry.open_tickets)}
                for entry in delivery.load_entries
            ] or [{"title": "Carga", "value": "Nenhum chamado atribuido encontrado"}]

            body.extend(
                [
                    {
                        "type": "TextBlock",
                        "text": "Carga atual dos consultores",
                        "weight": "Bolder",
                        "wrap": True,
                    },
                    {
                        "type": "FactSet",
                        "facts": load_facts,
                    },
                ]
            )

        return {
            "$schema": "http://adaptivecards.io/schemas/adaptive-card.json",
            "type": "AdaptiveCard",
            "version": "1.4",
            "msteams": {"width": "Full"},
            "body": body,
        }
