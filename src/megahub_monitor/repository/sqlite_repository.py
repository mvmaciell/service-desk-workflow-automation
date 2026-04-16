from __future__ import annotations

import json
import sqlite3
from collections.abc import Iterable
from logging import Logger
from pathlib import Path

from ..models import DeliveryRequest, LoadEntry, NotificationResult, Ticket


class SQLiteRepository:
    def __init__(self, database_path: Path, logger: Logger) -> None:
        self.database_path = database_path
        self.logger = logger

    def initialize(self) -> None:
        with self._connect() as connection:
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS source_states (
                    source_id TEXT PRIMARY KEY,
                    baseline_initialized_at TEXT,
                    last_run_at TEXT,
                    last_success_at TEXT
                );

                CREATE TABLE IF NOT EXISTS source_seen_tickets (
                    source_id TEXT NOT NULL,
                    ticket_number TEXT NOT NULL,
                    first_seen_at TEXT NOT NULL,
                    last_seen_at TEXT NOT NULL,
                    last_payload_json TEXT NOT NULL,
                    PRIMARY KEY (source_id, ticket_number)
                );

                CREATE TABLE IF NOT EXISTS source_snapshots (
                    snapshot_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    source_id TEXT NOT NULL,
                    collected_at TEXT NOT NULL,
                    ticket_count INTEGER NOT NULL,
                    payload_json TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS load_snapshots (
                    snapshot_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    source_id TEXT NOT NULL,
                    collected_at TEXT NOT NULL,
                    payload_json TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS notification_deliveries (
                    delivery_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    source_id TEXT NOT NULL,
                    rule_id TEXT NOT NULL,
                    recipient_id TEXT NOT NULL,
                    ticket_number TEXT NOT NULL,
                    attempted_at TEXT NOT NULL,
                    success INTEGER NOT NULL,
                    http_status INTEGER,
                    response_text TEXT,
                    payload_json TEXT NOT NULL
                );
                """
            )

    def is_baseline_initialized(self, source_id: str) -> bool:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT baseline_initialized_at FROM source_states WHERE source_id = ?",
                (source_id,),
            ).fetchone()
        return bool(row and row["baseline_initialized_at"])

    def mark_baseline_initialized(self, source_id: str, timestamp: str) -> None:
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO source_states (source_id, baseline_initialized_at, last_run_at, last_success_at)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(source_id) DO UPDATE SET
                    baseline_initialized_at = excluded.baseline_initialized_at,
                    last_run_at = excluded.last_run_at,
                    last_success_at = excluded.last_success_at
                """,
                (source_id, timestamp, timestamp, timestamp),
            )

    def update_source_run(self, source_id: str, run_at: str, success: bool) -> None:
        with self._connect() as connection:
            existing = connection.execute(
                "SELECT baseline_initialized_at, last_success_at FROM source_states WHERE source_id = ?",
                (source_id,),
            ).fetchone()
            baseline_initialized_at = existing["baseline_initialized_at"] if existing else None
            last_success_at = run_at if success else (existing["last_success_at"] if existing else None)

            connection.execute(
                """
                INSERT INTO source_states (source_id, baseline_initialized_at, last_run_at, last_success_at)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(source_id) DO UPDATE SET
                    baseline_initialized_at = excluded.baseline_initialized_at,
                    last_run_at = excluded.last_run_at,
                    last_success_at = excluded.last_success_at
                """,
                (source_id, baseline_initialized_at, run_at, last_success_at),
            )

    def get_known_numbers(self, source_id: str, ticket_numbers: Iterable[str]) -> set[str]:
        numbers = [number for number in ticket_numbers if number]
        if not numbers:
            return set()

        placeholders = ",".join("?" for _ in numbers)
        query = (
            "SELECT ticket_number FROM source_seen_tickets "
            f"WHERE source_id = ? AND ticket_number IN ({placeholders})"
        )

        with self._connect() as connection:
            rows = connection.execute(query, [source_id, *numbers]).fetchall()
        return {row[0] for row in rows}

    def upsert_seen_tickets(self, source_id: str, tickets: Iterable[Ticket], seen_at: str) -> None:
        rows = [
            (
                source_id,
                ticket.number,
                seen_at,
                seen_at,
                json.dumps(ticket.to_dict(), ensure_ascii=False),
            )
            for ticket in tickets
        ]

        if not rows:
            return

        with self._connect() as connection:
            connection.executemany(
                """
                INSERT INTO source_seen_tickets (
                    source_id,
                    ticket_number,
                    first_seen_at,
                    last_seen_at,
                    last_payload_json
                ) VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(source_id, ticket_number) DO UPDATE SET
                    last_seen_at = excluded.last_seen_at,
                    last_payload_json = excluded.last_payload_json
                """,
                rows,
            )

    def save_snapshot(self, source_id: str, tickets: Iterable[Ticket], collected_at: str) -> None:
        payload = [ticket.to_dict() for ticket in tickets]
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO source_snapshots (source_id, collected_at, ticket_count, payload_json)
                VALUES (?, ?, ?, ?)
                """,
                (source_id, collected_at, len(payload), json.dumps(payload, ensure_ascii=False)),
            )

    def save_load_snapshot(self, source_id: str, load_entries: Iterable[LoadEntry], collected_at: str) -> None:
        payload = [entry.to_dict() for entry in load_entries]
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO load_snapshots (source_id, collected_at, payload_json)
                VALUES (?, ?, ?)
                """,
                (source_id, collected_at, json.dumps(payload, ensure_ascii=False)),
            )

    def has_delivery(self, source_id: str, rule_id: str, recipient_id: str, ticket_number: str) -> bool:
        with self._connect() as connection:
            row = connection.execute(
                """
                SELECT 1
                FROM notification_deliveries
                WHERE source_id = ?
                  AND rule_id = ?
                  AND recipient_id = ?
                  AND ticket_number = ?
                  AND success = 1
                LIMIT 1
                """,
                (source_id, rule_id, recipient_id, ticket_number),
            ).fetchone()
        return row is not None

    def record_delivery(
        self,
        delivery: DeliveryRequest,
        attempted_at: str,
        result: NotificationResult,
    ) -> None:
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO notification_deliveries (
                    source_id,
                    rule_id,
                    recipient_id,
                    ticket_number,
                    attempted_at,
                    success,
                    http_status,
                    response_text,
                    payload_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    delivery.source_id,
                    delivery.rule_id,
                    delivery.recipient_id,
                    delivery.ticket.number,
                    attempted_at,
                    1 if result.success else 0,
                    result.status_code,
                    result.response_text,
                    json.dumps(result.payload, ensure_ascii=False),
                ),
            )

    def get_ticket_from_snapshot(self, ticket_number: str, source_id: str | None = None) -> Ticket | None:
        """Retrieve a ticket from the most recent snapshot containing it."""
        with self._connect() as connection:
            if source_id:
                rows = connection.execute(
                    "SELECT payload_json FROM source_snapshots WHERE source_id = ? ORDER BY collected_at DESC LIMIT 5",
                    (source_id,),
                ).fetchall()
            else:
                rows = connection.execute(
                    "SELECT payload_json FROM source_snapshots ORDER BY collected_at DESC LIMIT 5",
                ).fetchall()
            for row in rows:
                tickets = json.loads(row["payload_json"])
                for t in tickets:
                    if t.get("number") == ticket_number:
                        return Ticket(
                            number=t["number"],
                            source_id=t.get("source_id", source_id or ""),
                            source_name=t.get("source_name", ""),
                            source_kind=t.get("source_kind", ""),
                            title=t.get("title", ""),
                            customer_ticket_number=t.get("customer_ticket_number", ""),
                            company=t.get("company", ""),
                            front=t.get("front", ""),
                            ticket_type=t.get("ticket_type", ""),
                            priority=t.get("priority", ""),
                            ticket_status=t.get("ticket_status", ""),
                            due_date=t.get("due_date", ""),
                            consultant=t.get("consultant", ""),
                        )
        return None

    def forget_ticket(self, ticket_number: str, source_id: str | None = None) -> int:
        with self._connect() as connection:
            if source_id:
                cursor = connection.execute(
                    "DELETE FROM source_seen_tickets WHERE source_id = ? AND ticket_number = ?",
                    (source_id, ticket_number),
                )
            else:
                cursor = connection.execute(
                    "DELETE FROM source_seen_tickets WHERE ticket_number = ?",
                    (ticket_number,),
                )
            return cursor.rowcount

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.database_path)
        connection.row_factory = sqlite3.Row
        return connection
