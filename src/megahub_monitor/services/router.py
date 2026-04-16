from __future__ import annotations

import unicodedata
from logging import Logger

from ..config import Settings, SourceConfig, SubscriptionConfig
from ..domain.models import DeliveryRequest, LoadEntry, Ticket
from ..repository.sqlite_repository import SQLiteRepository


def _normalize(value: str) -> str:
    normalized = unicodedata.normalize("NFD", value or "")
    normalized = "".join(char for char in normalized if unicodedata.category(char) != "Mn")
    return normalized.strip().lower()


class NotificationRouter:
    def __init__(self, settings: Settings, repository: SQLiteRepository, logger: Logger) -> None:
        self.settings = settings
        self.repository = repository
        self.logger = logger

    def build_deliveries(
        self,
        source: SourceConfig,
        new_tickets: list[Ticket],
        load_entries: list[LoadEntry],
    ) -> list[DeliveryRequest]:
        deliveries: list[DeliveryRequest] = []

        for ticket in new_tickets:
            for subscription in self.settings.subscriptions:
                if not subscription.enabled or source.id not in subscription.source_ids:
                    continue
                if not self._matches_rule(subscription, ticket):
                    continue

                for profile_id in subscription.profile_ids:
                    profile = self.settings.get_profile(profile_id)
                    if not profile.enabled:
                        continue
                    if not profile.webhook_url:
                        self.logger.warning(
                            "Perfil '%s' esta sem webhook configurado. Subscricao '%s' ignorada.",
                            profile.id,
                            subscription.id,
                        )
                        continue
                    if self.repository.has_delivery(source.id, subscription.id, profile.id, ticket.number):
                        continue

                    deliveries.append(
                        DeliveryRequest(
                            source_id=source.id,
                            source_name=source.name,
                            rule_id=subscription.id,
                            title_prefix=subscription.title_prefix,
                            recipient_id=profile.id,
                            recipient_name=profile.name,
                            recipient_role=profile.role,
                            webhook_url=profile.webhook_url,
                            ticket=ticket,
                            load_entries=load_entries if subscription.include_load else [],
                        )
                    )

        return deliveries

    def _matches_rule(self, subscription: SubscriptionConfig, ticket: Ticket) -> bool:
        if subscription.ticket_types and _normalize(ticket.ticket_type) not in subscription.ticket_types:
            return False
        if subscription.priorities and _normalize(ticket.priority) not in subscription.priorities:
            return False
        if subscription.companies and _normalize(ticket.company) not in subscription.companies:
            return False
        if subscription.consultants and _normalize(ticket.consultant) not in subscription.consultants:
            return False
        return True
