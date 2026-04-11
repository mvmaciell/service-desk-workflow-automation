from __future__ import annotations

import json
import sqlite3
from collections.abc import Iterable
from logging import Logger
from pathlib import Path

from ..models import NotificationResult, Ticket


class SQLiteRepository:
    def __init__(self, database_path: Path, logger: Logger) -> None:
        self.database_path = database_path
        self.logger = logger

    def initialize(self) -> None:
        with self._connect() as connection:
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS app_state (
                    state_key TEXT PRIMARY KEY,
                    state_value TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS seen_tickets (
                    ticket_number TEXT PRIMARY KEY,
                    first_seen_at TEXT NOT NULL,
                    last_seen_at TEXT NOT NULL,
                    last_payload_json TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS snapshots (
                    snapshot_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    collected_at TEXT NOT NULL,
                    ticket_count INTEGER NOT NULL,
                    payload_json TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS notification_attempts (
                    attempt_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    ticket_number TEXT NOT NULL,
                    attempted_at TEXT NOT NULL,
                    success INTEGER NOT NULL,
                    http_status INTEGER,
                    response_text TEXT,
                    payload_json TEXT NOT NULL
                );
                """
            )

    def is_baseline_initialized(self) -> bool:
        return self.get_state("baseline_initialized_at") is not None

    def mark_baseline_initialized(self, timestamp: str) -> None:
        self.set_state("baseline_initialized_at", timestamp)

    def get_known_numbers(self, ticket_numbers: Iterable[str]) -> set[str]:
        numbers = [number for number in ticket_numbers if number]
        if not numbers:
            return set()

        placeholders = ",".join("?" for _ in numbers)
        query = f"SELECT ticket_number FROM seen_tickets WHERE ticket_number IN ({placeholders})"

        with self._connect() as connection:
            rows = connection.execute(query, numbers).fetchall()
        return {row[0] for row in rows}

    def upsert_seen_tickets(self, tickets: Iterable[Ticket], seen_at: str) -> None:
        rows = [
            (
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
                INSERT INTO seen_tickets (
                    ticket_number,
                    first_seen_at,
                    last_seen_at,
                    last_payload_json
                ) VALUES (?, ?, ?, ?)
                ON CONFLICT(ticket_number) DO UPDATE SET
                    last_seen_at = excluded.last_seen_at,
                    last_payload_json = excluded.last_payload_json
                """,
                rows,
            )

    def save_snapshot(self, tickets: Iterable[Ticket], collected_at: str) -> None:
        payload = [ticket.to_dict() for ticket in tickets]
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO snapshots (collected_at, ticket_count, payload_json)
                VALUES (?, ?, ?)
                """,
                (collected_at, len(payload), json.dumps(payload, ensure_ascii=False)),
            )

    def record_notification_attempt(
        self,
        ticket_number: str,
        attempted_at: str,
        result: NotificationResult,
    ) -> None:
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO notification_attempts (
                    ticket_number,
                    attempted_at,
                    success,
                    http_status,
                    response_text,
                    payload_json
                ) VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    ticket_number,
                    attempted_at,
                    1 if result.success else 0,
                    result.status_code,
                    result.response_text,
                    json.dumps(result.payload, ensure_ascii=False),
                ),
            )

    def forget_ticket(self, ticket_number: str) -> int:
        with self._connect() as connection:
            cursor = connection.execute(
                "DELETE FROM seen_tickets WHERE ticket_number = ?",
                (ticket_number,),
            )
            return cursor.rowcount

    def set_state(self, key: str, value: str) -> None:
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO app_state (state_key, state_value)
                VALUES (?, ?)
                ON CONFLICT(state_key) DO UPDATE SET
                    state_value = excluded.state_value
                """,
                (key, value),
            )

    def get_state(self, key: str) -> str | None:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT state_value FROM app_state WHERE state_key = ?",
                (key,),
            ).fetchone()
        return row[0] if row else None

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.database_path)
        connection.row_factory = sqlite3.Row
        return connection

