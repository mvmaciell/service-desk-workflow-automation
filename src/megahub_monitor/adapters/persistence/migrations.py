"""Version-tracked SQLite schema migration runner.

Each migration is idempotent (CREATE TABLE IF NOT EXISTS / ADD COLUMN IF NOT EXISTS).
Migrations run in version order on every initialize() call.
The schema_version table tracks which migrations have been applied.
"""
from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone


@dataclass
class Migration:
    version: int
    description: str
    sql: str


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


# ---------------------------------------------------------------------------
# Migration registry
# Add new migrations at the end — never edit existing ones.
# ---------------------------------------------------------------------------
MIGRATIONS: list[Migration] = [
    Migration(
        version=1,
        description="Initial schema (legacy tables)",
        sql="""
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
        """,
    ),
    Migration(
        version=2,
        description="Workflow items, audit trail, pending approvals",
        sql="""
        CREATE TABLE IF NOT EXISTS workflow_items (
            ticket_number TEXT NOT NULL,
            source_id TEXT NOT NULL,
            current_state TEXT NOT NULL,
            detected_at TEXT NOT NULL,
            last_state_change_at TEXT NOT NULL,
            suggested_member_ids_json TEXT,
            approved_member_id TEXT,
            approval_received_at TEXT,
            completed_at TEXT,
            last_known_itsm_status TEXT NOT NULL DEFAULT '',
            PRIMARY KEY (ticket_number, source_id)
        );

        CREATE INDEX IF NOT EXISTS idx_workflow_state
            ON workflow_items(current_state);

        CREATE TABLE IF NOT EXISTS audit_events (
            event_id TEXT PRIMARY KEY,
            timestamp TEXT NOT NULL,
            action TEXT NOT NULL,
            ticket_number TEXT,
            source_id TEXT,
            actor TEXT NOT NULL,
            details_json TEXT NOT NULL
        );

        CREATE INDEX IF NOT EXISTS idx_audit_ticket
            ON audit_events(ticket_number);

        CREATE INDEX IF NOT EXISTS idx_audit_timestamp
            ON audit_events(timestamp);

        CREATE TABLE IF NOT EXISTS pending_approvals (
            ticket_number TEXT NOT NULL,
            source_id TEXT NOT NULL,
            request_id TEXT NOT NULL UNIQUE,
            suggestions_json TEXT NOT NULL,
            created_at TEXT NOT NULL,
            resolved_at TEXT,
            chosen_member_id TEXT,
            PRIMARY KEY (ticket_number, source_id)
        );
        """,
    ),
    Migration(
        version=3,
        description="Add baseline_version to source_states",
        sql="""
        ALTER TABLE source_states ADD COLUMN baseline_version INTEGER NOT NULL DEFAULT 1;
        """,
    ),
]


def run_migrations(connection: sqlite3.Connection) -> list[int]:
    """Apply all pending migrations. Returns list of applied version numbers."""
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS schema_version (
            version INTEGER PRIMARY KEY,
            applied_at TEXT NOT NULL,
            description TEXT NOT NULL
        )
        """
    )
    connection.commit()

    applied = {
        row[0]
        for row in connection.execute("SELECT version FROM schema_version").fetchall()
    }

    newly_applied: list[int] = []
    for migration in sorted(MIGRATIONS, key=lambda m: m.version):
        if migration.version in applied:
            continue

        _apply_migration(connection, migration)
        newly_applied.append(migration.version)

    return newly_applied


def _apply_migration(connection: sqlite3.Connection, migration: Migration) -> None:
    """Apply a single migration, handling column-already-exists gracefully."""
    statements = [s.strip() for s in migration.sql.split(";") if s.strip()]

    for stmt in statements:
        try:
            connection.execute(stmt)
        except sqlite3.OperationalError as exc:
            # ALTER TABLE ADD COLUMN fails if column already exists (pre-existing DBs)
            if "duplicate column name" in str(exc).lower():
                continue
            raise

    connection.execute(
        "INSERT OR IGNORE INTO schema_version (version, applied_at, description) VALUES (?, ?, ?)",
        (migration.version, _utc_now(), migration.description),
    )
    connection.commit()
