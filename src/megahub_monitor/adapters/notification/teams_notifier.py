"""TeamsWorkflowNotifier — full implementation of the Notifier port.

Implements all 5 Notifier methods using Microsoft Teams Adaptive Cards
delivered via Power Automate webhooks.
"""
from __future__ import annotations

from logging import Logger

import requests

from ...config import Settings
from ...domain.models import (
    AllocationSuggestion,
    DeliveryRequest,
    EnhancedLoadEntry,
    NotificationResult,
    Ticket,
    utc_now_iso,
)
from ...errors import ConfigurationError, NotificationError
from ...ports.notifier import Notifier


class TeamsNotifier(Notifier):
    """Sends Adaptive Cards to Teams via Power Automate webhooks."""

    def __init__(self, settings: Settings, logger: Logger) -> None:
        self._settings = settings
        self._logger = logger

    # ------------------------------------------------------------------
    # Notifier port methods
    # ------------------------------------------------------------------

    def send_new_ticket_alert(
        self,
        recipient_name: str,
        recipient_role: str,
        webhook_url: str,
        ticket: Ticket,
        load_entries: list[EnhancedLoadEntry],
        title_prefix: str,
    ) -> NotificationResult:
        payload = self._build_alert_card(
            recipient_name, recipient_role, ticket, load_entries, title_prefix
        )
        return self._post(payload, webhook_url)

    def send_allocation_suggestion(
        self,
        coordinator_name: str,
        webhook_url: str,
        ticket: Ticket,
        suggestions: list[AllocationSuggestion],
        load_board: list[EnhancedLoadEntry],
    ) -> NotificationResult:
        payload = self._build_suggestion_card(
            coordinator_name, ticket, suggestions, load_board
        )
        return self._post(payload, webhook_url)

    def send_batch_allocation_suggestion(
        self,
        coordinator_name: str,
        webhook_url: str,
        ticket_suggestions: list[tuple[Ticket, list[AllocationSuggestion]]],
        load_board: list[EnhancedLoadEntry],
    ) -> NotificationResult:
        payload = self._build_batch_suggestion_card(
            coordinator_name, ticket_suggestions, load_board
        )
        return self._post(payload, webhook_url)

    def send_assignment_notice(
        self,
        developer_name: str,
        webhook_url: str,
        ticket: Ticket,
    ) -> NotificationResult:
        payload = self._build_assignment_card(developer_name, ticket)
        return self._post(payload, webhook_url)

    def send_completion_notice(
        self,
        coordinator_name: str,
        webhook_url: str,
        ticket: Ticket,
        completed_by: str,
    ) -> NotificationResult:
        payload = self._build_completion_card(coordinator_name, ticket, completed_by)
        return self._post(payload, webhook_url)

    def send_return_notice(
        self,
        recipient_name: str,
        webhook_url: str,
        ticket: Ticket,
        current_status: str,
    ) -> NotificationResult:
        payload = self._build_return_card(recipient_name, ticket, current_status)
        return self._post(payload, webhook_url)

    def send_approval_reminder(
        self,
        coordinator_name: str,
        webhook_url: str,
        timed_out_approvals: list[dict],
    ) -> NotificationResult:
        payload = self._build_reminder_card(coordinator_name, timed_out_approvals)
        return self._post(payload, webhook_url)

    def send_test_message(
        self,
        recipient_name: str,
        recipient_role: str,
        webhook_url: str,
    ) -> NotificationResult:
        payload = self._build_test_card(recipient_name, recipient_role)
        return self._post(payload, webhook_url)

    # ------------------------------------------------------------------
    # Legacy delivery method (used by legacy notification path)
    # ------------------------------------------------------------------

    def send_delivery(self, delivery: DeliveryRequest) -> NotificationResult:
        payload = self._build_delivery_card(delivery)
        return self._post(payload, delivery.webhook_url)

    # ------------------------------------------------------------------
    # Card builders
    # ------------------------------------------------------------------

    def _build_suggestion_card(
        self,
        coordinator_name: str,
        ticket: Ticket,
        suggestions: list[AllocationSuggestion],
        load_board: list[EnhancedLoadEntry],
    ) -> dict:
        chamado_value = (
            f"[{ticket.number}]({ticket.detail_url})"
            if ticket.detail_url
            else ticket.number
        )
        ticket_facts = [
            {"title": "Chamado", "value": chamado_value},
            {"title": "Tipo", "value": ticket.ticket_type or "-"},
            {"title": "Prioridade", "value": ticket.priority or "-"},
            {"title": "Status", "value": ticket.ticket_status or "-"},
        ]
        if ticket.company:
            ticket_facts.append({"title": "Empresa", "value": ticket.company})
        if ticket.front:
            ticket_facts.append({"title": "Frente", "value": ticket.front})

        names = ", ".join(s.member_name for s in suggestions) if suggestions else "—"

        body: list[dict] = [
            {
                "type": "TextBlock",
                "text": "Sugestao de Alocacao",
                "weight": "Bolder",
                "size": "Large",
                "wrap": True,
            },
            {
                "type": "TextBlock",
                "text": ticket.title or "Sem titulo",
                "wrap": True,
                "isSubtle": True,
            },
            {"type": "FactSet", "facts": ticket_facts},
            {
                "type": "TextBlock",
                "text": names,
                "wrap": True,
            },
        ]

        return self._adaptive_card(body)

    def _build_batch_suggestion_card(
        self,
        coordinator_name: str,
        ticket_suggestions: list[tuple[Ticket, list[AllocationSuggestion]]],
        load_board: list[EnhancedLoadEntry],
    ) -> dict:
        priority_colors = {
            "imediata": "Attention",
            "urgente": "Warning",
        }
        count = len(ticket_suggestions)

        body: list[dict] = [
            {
                "type": "TextBlock",
                "text": f"Sugestao de Alocacao — {count} chamado(s) novo(s)",
                "weight": "Bolder",
                "size": "Large",
                "wrap": True,
            },
        ]

        for ticket, suggestions in ticket_suggestions:
            prio_lower = ticket.priority.strip().lower()
            color = priority_colors.get(prio_lower, "Default")
            prio_label = f" [{ticket.priority}]" if prio_lower in priority_colors else ""

            chamado_value = (
                f"[{ticket.number}]({ticket.detail_url}){prio_label}"
                if ticket.detail_url
                else f"{ticket.number}{prio_label}"
            )
            ticket_facts = [
                {"title": "Chamado", "value": chamado_value},
                {"title": "Frente", "value": ticket.front or "-"},
                {"title": "Empresa", "value": ticket.company or "-"},
            ]
            if ticket.ticket_type:
                ticket_facts.append({"title": "Tipo", "value": ticket.ticket_type})

            names = ", ".join(s.member_name for s in suggestions) if suggestions else "—"

            items: list[dict] = [
                {
                    "type": "TextBlock",
                    "text": ticket.title or "Sem titulo",
                    "weight": "Bolder",
                    "wrap": True,
                    "color": color,
                },
                {"type": "FactSet", "facts": ticket_facts},
                {
                    "type": "TextBlock",
                    "text": names,
                    "wrap": True,
                },
            ]

            body.append({"type": "ColumnSet", "separator": True, "columns": [
                {"type": "Column", "width": "stretch", "items": items},
            ]})

        return self._adaptive_card(body)

    def _build_assignment_card(self, developer_name: str, ticket: Ticket) -> dict:
        chamado_value = (
            f"[{ticket.number}]({ticket.detail_url})"
            if ticket.detail_url
            else ticket.number
        )
        facts = [
            {"title": "Chamado", "value": chamado_value},
            {"title": "Tipo", "value": ticket.ticket_type or "-"},
            {"title": "Prioridade", "value": ticket.priority or "-"},
            {"title": "Status", "value": ticket.ticket_status or "-"},
        ]
        if ticket.company:
            facts.append({"title": "Empresa", "value": ticket.company})
        if ticket.front:
            facts.append({"title": "Frente", "value": ticket.front})
        if ticket.due_date:
            facts.append({"title": "Previsao", "value": ticket.due_date})

        body = [
            {
                "type": "TextBlock",
                "text": "Chamado Atribuido a Voce",
                "weight": "Bolder",
                "size": "Large",
                "wrap": True,
            },
            {
                "type": "TextBlock",
                "text": ticket.title or "Sem titulo",
                "wrap": True,
                "isSubtle": True,
            },
            {"type": "FactSet", "facts": facts},
        ]
        return self._adaptive_card(body)

    def _build_completion_card(
        self, coordinator_name: str, ticket: Ticket, completed_by: str
    ) -> dict:
        chamado_value = (
            f"[{ticket.number}]({ticket.detail_url})"
            if ticket.detail_url
            else ticket.number
        )
        facts = [
            {"title": "Chamado", "value": chamado_value},
            {"title": "Concluido por", "value": completed_by},
            {"title": "Tipo", "value": ticket.ticket_type or "-"},
            {"title": "Prioridade", "value": ticket.priority or "-"},
        ]
        body = [
            {
                "type": "TextBlock",
                "text": "Chamado Concluido",
                "weight": "Bolder",
                "size": "Large",
                "wrap": True,
            },
            {
                "type": "TextBlock",
                "text": ticket.title or "Sem titulo",
                "wrap": True,
                "isSubtle": True,
            },
            {"type": "FactSet", "facts": facts},
        ]
        return self._adaptive_card(body)

    def _build_alert_card(
        self,
        recipient_name: str,
        recipient_role: str,
        ticket: Ticket,
        load_entries: list[EnhancedLoadEntry],
        title_prefix: str,
    ) -> dict:
        chamado_value = (
            f"[{ticket.number}]({ticket.detail_url})"
            if ticket.detail_url
            else ticket.number
        )
        facts = [
            {"title": "Destinatario", "value": recipient_name},
            {"title": "Chamado", "value": chamado_value},
            {"title": "Tipo", "value": ticket.ticket_type or "-"},
            {"title": "Prioridade", "value": ticket.priority or "-"},
            {"title": "Status", "value": ticket.ticket_status or "-"},
        ]
        if ticket.company:
            facts.append({"title": "Empresa", "value": ticket.company})
        if ticket.front:
            facts.append({"title": "Frente", "value": ticket.front})
        if ticket.consultant:
            facts.append({"title": "Consultor", "value": ticket.consultant})

        body: list[dict] = [
            {
                "type": "TextBlock",
                "text": title_prefix,
                "weight": "Bolder",
                "size": "Medium",
                "wrap": True,
            },
            {
                "type": "TextBlock",
                "text": ticket.title or "Sem titulo",
                "wrap": True,
            },
            {"type": "FactSet", "facts": facts},
        ]

        if load_entries:
            load_facts = [
                {"title": e.member_name, "value": str(e.open_tickets)}
                for e in load_entries
            ]
            body += [
                {
                    "type": "TextBlock",
                    "text": "Carga atual",
                    "weight": "Bolder",
                    "wrap": True,
                },
                {"type": "FactSet", "facts": load_facts},
            ]

        return self._adaptive_card(body)

    def _build_delivery_card(self, delivery: DeliveryRequest) -> dict:
        """Legacy card builder for backward compat with DeliveryRequest objects."""
        ticket = delivery.ticket
        facts = [
            {"title": "Destinatario", "value": delivery.recipient_name},
            {"title": "Perfil", "value": delivery.recipient_role},
            {"title": "Fonte", "value": delivery.source_name},
            {"title": "Chamado", "value": (
                f"[{ticket.number}]({ticket.detail_url})"
                if ticket.detail_url
                else ticket.number
            )},
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
            {"type": "FactSet", "facts": facts},
        ]

        if delivery.load_entries:
            load_facts = [
                {"title": entry.consultant, "value": str(entry.open_tickets)}
                for entry in delivery.load_entries
            ] or [{"title": "Carga", "value": "Nenhum chamado atribuido encontrado"}]
            body += [
                {
                    "type": "TextBlock",
                    "text": "Carga atual dos consultores",
                    "weight": "Bolder",
                    "wrap": True,
                },
                {"type": "FactSet", "facts": load_facts},
            ]

        return self._adaptive_card(body)

    def _build_return_card(
        self, recipient_name: str, ticket: Ticket, current_status: str
    ) -> dict:
        facts = [
            {"title": "Chamado", "value": ticket.number},
            {"title": "Status atual", "value": current_status},
            {"title": "Tipo", "value": ticket.ticket_type or "-"},
            {"title": "Prioridade", "value": ticket.priority or "-"},
        ]
        if ticket.company:
            facts.append({"title": "Empresa", "value": ticket.company})
        if ticket.front:
            facts.append({"title": "Frente", "value": ticket.front})

        body = [
            {
                "type": "TextBlock",
                "text": "\u26a0\ufe0f Chamado Retornou — Acao Necessaria",
                "weight": "Bolder",
                "size": "Large",
                "color": "Warning",
                "wrap": True,
            },
            {
                "type": "TextBlock",
                "text": ticket.title or "Sem titulo",
                "wrap": True,
                "isSubtle": True,
            },
            {"type": "FactSet", "facts": facts},
            {
                "type": "TextBlock",
                "text": "O chamado voltou para processamento. Verifique e retome o atendimento.",
                "wrap": True,
                "isSubtle": True,
            },
        ]
        return self._adaptive_card(body)

    def _build_reminder_card(
        self,
        coordinator_name: str,
        timed_out_approvals: list[dict],
    ) -> dict:
        import json as _json

        count = len(timed_out_approvals)
        body: list[dict] = [
            {
                "type": "TextBlock",
                "text": f"Lembrete: {count} aprovacao(oes) pendente(s)",
                "weight": "Bolder",
                "size": "Large",
                "color": "Warning",
                "wrap": True,
            },
        ]

        for approval in timed_out_approvals:
            elapsed = approval.get("elapsed_minutes", "?")
            ticket_num = approval.get("ticket_number", "?")

            suggestions_raw = approval.get("suggestions_json", "[]")
            try:
                suggestions = _json.loads(suggestions_raw) if isinstance(suggestions_raw, str) else suggestions_raw
            except (ValueError, TypeError):
                suggestions = []

            approve_cmds = "\n".join(
                f"python main.py approve --ticket {ticket_num} --member {s['member_id']}"
                for s in suggestions
                if isinstance(s, dict) and "member_id" in s
            ) or f"python main.py approve --ticket {ticket_num} --member <id>"

            body.append({
                "type": "Container",
                "separator": True,
                "items": [
                    {
                        "type": "TextBlock",
                        "text": f"Chamado {ticket_num} — pendente ha {elapsed} min",
                        "weight": "Bolder",
                        "color": "Attention",
                        "wrap": True,
                    },
                    {
                        "type": "TextBlock",
                        "text": approve_cmds,
                        "fontType": "Monospace",
                        "wrap": True,
                        "size": "Small",
                    },
                ],
            })

        return self._adaptive_card(body)

    def _build_test_card(self, recipient_name: str, recipient_role: str) -> dict:
        return self._adaptive_card([
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
                    {"title": "Executado em", "value": utc_now_iso()},
                ],
            },
        ])

    @staticmethod
    def _adaptive_card(body: list[dict]) -> dict:
        return {
            "$schema": "http://adaptivecards.io/schemas/adaptive-card.json",
            "type": "AdaptiveCard",
            "version": "1.4",
            "msteams": {"width": "Full"},
            "body": body,
        }

    def _post(self, payload: dict, webhook_url: str) -> NotificationResult:
        if not webhook_url:
            raise ConfigurationError("Webhook do Teams nao configurado para o destinatario.")
        try:
            response = requests.post(
                webhook_url,
                json=payload,
                timeout=self._settings.teams_request_timeout_seconds,
            )
        except requests.RequestException as exc:
            raise NotificationError(f"Falha de comunicacao com Teams/Workflow: {exc}") from exc

        success = 200 <= response.status_code < 300
        self._logger.info("Resposta do Teams/Workflow: HTTP %s", response.status_code)
        return NotificationResult(
            success=success,
            status_code=response.status_code,
            response_text=response.text.strip(),
            payload=payload,
        )
