"""SQLite implementation of the StateRepository port.

Implements all methods from the StateRepository ABC.
All legacy methods are preserved with identical behavior to the original
repository/sqlite_repository.py to ensure backward compatibility.
"""
from __future__ import annotations

import json
import sqlite3
from collections.abc import Iterable
from contextlib import contextmanager
from pathlib import Path
from typing import Any

from ...domain.enums import TicketWorkflowState
from ...domain.models import (
    AllocationSuggestion,
    AuditEvent,
    DeliveryRequest,
    LoadEntry,
    NotificationResult,
    Ticket,
    WorkflowItem,
    utc_now_iso,
)
from ...ports.state_repository import StateRepository
from .migrations import run_migrations


def _safe_json(raw: str | None, default: Any) -> Any:
    try:
        return json.loads(raw or json.dumps(default))
    except json.JSONDecodeError:
        return default


class SQLiteStateRepository(StateRepository):
    def __init__(self, database_path: Path) -> None:
        self.database_path = database_path

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------
    def initialize(self) -> None:
        with self._connect() as conn:
            run_migrations(conn)

    # ------------------------------------------------------------------
    # Source state (legacy — unchanged behavior)
    # ------------------------------------------------------------------
    def is_baseline_initialized(self, source_id: str) -> bool:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT baseline_initialized_at FROM source_states WHERE source_id = ?",
                (source_id,),
            ).fetchone()
        return bool(row and row["baseline_initialized_at"])

    def mark_baseline_initialized(self, source_id: str, timestamp: str, baseline_version: int = 2) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO source_states
                    (source_id, baseline_initialized_at, last_run_at, last_success_at, baseline_version)
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(source_id) DO UPDATE SET
                    baseline_initialized_at = excluded.baseline_initialized_at,
                    last_run_at = excluded.last_run_at,
                    last_success_at = excluded.last_success_at,
                    baseline_version = excluded.baseline_version
                """,
                (source_id, timestamp, timestamp, timestamp, baseline_version),
            )

    def update_source_run(self, source_id: str, run_at: str, success: bool) -> None:
        with self._connect() as conn:
            existing = conn.execute(
                "SELECT baseline_initialized_at, last_success_at FROM source_states WHERE source_id = ?",
                (source_id,),
            ).fetchone()
            baseline_initialized_at = existing["baseline_initialized_at"] if existing else None
            last_success_at = (
                run_at if success else (existing["last_success_at"] if existing else None)
            )
            conn.execute(
                """
                INSERT INTO source_states
                    (source_id, baseline_initialized_at, last_run_at, last_success_at)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(source_id) DO UPDATE SET
                    baseline_initialized_at = excluded.baseline_initialized_at,
                    last_run_at = excluded.last_run_at,
                    last_success_at = excluded.last_success_at
                """,
                (source_id, baseline_initialized_at, run_at, last_success_at),
            )

    def get_baseline_version(self, source_id: str) -> int:
        """Returns 0 if source not found, 1 if legacy, 2 if new behavior."""
        with self._connect() as conn:
            row = conn.execute(
                "SELECT baseline_version FROM source_states WHERE source_id = ?",
                (source_id,),
            ).fetchone()
        if not row:
            return 0
        return row["baseline_version"] or 1

    # ------------------------------------------------------------------
    # Seen tickets (legacy — unchanged behavior)
    # ------------------------------------------------------------------
    def get_known_numbers(self, source_id: str, ticket_numbers: Iterable[str]) -> set[str]:
        numbers = [n for n in ticket_numbers if n]
        if not numbers:
            return set()
        placeholders = ",".join("?" for _ in numbers)
        query = (
            "SELECT ticket_number FROM source_seen_tickets "
            f"WHERE source_id = ? AND ticket_number IN ({placeholders})"
        )
        with self._connect() as conn:
            rows = conn.execute(query, [source_id, *numbers]).fetchall()
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
        with self._connect() as conn:
            conn.executemany(
                """
                INSERT INTO source_seen_tickets
                    (source_id, ticket_number, first_seen_at, last_seen_at, last_payload_json)
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(source_id, ticket_number) DO UPDATE SET
                    last_seen_at = excluded.last_seen_at,
                    last_payload_json = excluded.last_payload_json
                """,
                rows,
            )

    # ------------------------------------------------------------------
    # Snapshots (legacy — unchanged behavior)
    # ------------------------------------------------------------------
    def save_snapshot(self, source_id: str, tickets: Iterable[Ticket], collected_at: str) -> None:
        payload = [t.to_dict() for t in tickets]
        with self._connect() as conn:
            conn.execute(
                "INSERT INTO source_snapshots (source_id, collected_at, ticket_count, payload_json) VALUES (?, ?, ?, ?)",
                (source_id, collected_at, len(payload), json.dumps(payload, ensure_ascii=False)),
            )

    def save_load_snapshot(self, source_id: str, entries: Iterable[LoadEntry], collected_at: str) -> None:
        payload = [e.to_dict() for e in entries]
        with self._connect() as conn:
            conn.execute(
                "INSERT INTO load_snapshots (source_id, collected_at, payload_json) VALUES (?, ?, ?)",
                (source_id, collected_at, json.dumps(payload, ensure_ascii=False)),
            )

    # ------------------------------------------------------------------
    # Delivery dedup (legacy — unchanged behavior)
    # ------------------------------------------------------------------
    def has_delivery(self, source_id: str, rule_id: str, recipient_id: str, ticket_number: str) -> bool:
        with self._connect() as conn:
            row = conn.execute(
                """
                SELECT 1 FROM notification_deliveries
                WHERE source_id = ? AND rule_id = ? AND recipient_id = ? AND ticket_number = ? AND success = 1
                LIMIT 1
                """,
                (source_id, rule_id, recipient_id, ticket_number),
            ).fetchone()
        return row is not None

    def record_delivery(self, delivery: DeliveryRequest, attempted_at: str, result: NotificationResult) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO notification_deliveries
                    (source_id, rule_id, recipient_id, ticket_number, attempted_at, success, http_status, response_text, payload_json)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
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

    # ------------------------------------------------------------------
    # Workflow items (NEW)
    # ------------------------------------------------------------------
    def get_workflow_item(self, ticket_number: str, source_id: str) -> WorkflowItem | None:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM workflow_items WHERE ticket_number = ? AND source_id = ?",
                (ticket_number, source_id),
            ).fetchone()
        if not row:
            return None
        return self._row_to_workflow_item(row)

    def upsert_workflow_item(self, item: WorkflowItem) -> None:
        suggested_json = json.dumps(item.suggested_member_ids, ensure_ascii=False)
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO workflow_items
                    (ticket_number, source_id, current_state, detected_at, last_state_change_at,
                     suggested_member_ids_json, approved_member_id, approval_received_at,
                     completed_at, last_known_itsm_status)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(ticket_number, source_id) DO UPDATE SET
                    current_state = excluded.current_state,
                    last_state_change_at = excluded.last_state_change_at,
                    suggested_member_ids_json = excluded.suggested_member_ids_json,
                    approved_member_id = excluded.approved_member_id,
                    approval_received_at = excluded.approval_received_at,
                    completed_at = excluded.completed_at,
                    last_known_itsm_status = excluded.last_known_itsm_status
                """,
                (
                    item.ticket_number,
                    item.source_id,
                    item.current_state.name,
                    item.detected_at,
                    item.last_state_change_at,
                    suggested_json,
                    item.approved_member_id,
                    item.approval_received_at,
                    item.completed_at,
                    item.last_known_itsm_status,
                ),
            )

    def get_items_in_state(self, state: TicketWorkflowState) -> list[WorkflowItem]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT * FROM workflow_items WHERE current_state = ?",
                (state.name,),
            ).fetchall()
        return [self._row_to_workflow_item(row) for row in rows]

    def _row_to_workflow_item(self, row: sqlite3.Row) -> WorkflowItem:
        try:
            suggested = json.loads(row["suggested_member_ids_json"] or "[]")
        except json.JSONDecodeError:
            suggested = []
        return WorkflowItem(
            ticket_number=row["ticket_number"],
            source_id=row["source_id"],
            current_state=TicketWorkflowState[row["current_state"]],
            detected_at=row["detected_at"],
            last_state_change_at=row["last_state_change_at"],
            suggested_member_ids=suggested,
            approved_member_id=row["approved_member_id"],
            approval_received_at=row["approval_received_at"],
            completed_at=row["completed_at"],
            last_known_itsm_status=row["last_known_itsm_status"] or "",
        )

    # ------------------------------------------------------------------
    # Audit trail (NEW)
    # ------------------------------------------------------------------
    def record_audit_event(self, event: AuditEvent) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                INSERT OR IGNORE INTO audit_events
                    (event_id, timestamp, action, ticket_number, source_id, actor, details_json)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    event.event_id,
                    event.timestamp,
                    event.action.value,
                    event.ticket_number,
                    event.source_id,
                    event.actor,
                    json.dumps(event.details, ensure_ascii=False),
                ),
            )

    def get_audit_trail(self, ticket_number: str | None = None, limit: int = 100) -> list[AuditEvent]:
        with self._connect() as conn:
            if ticket_number:
                rows = conn.execute(
                    "SELECT * FROM audit_events WHERE ticket_number = ? ORDER BY timestamp DESC LIMIT ?",
                    (ticket_number, limit),
                ).fetchall()
            else:
                rows = conn.execute(
                    "SELECT * FROM audit_events ORDER BY timestamp DESC LIMIT ?",
                    (limit,),
                ).fetchall()
        return [AuditEvent.from_dict({
            "event_id": row["event_id"],
            "timestamp": row["timestamp"],
            "action": row["action"],
            "ticket_number": row["ticket_number"],
            "source_id": row["source_id"],
            "actor": row["actor"],
            "details": _safe_json(row["details_json"], {}),
        }) for row in rows]

    # ------------------------------------------------------------------
    # Approval tracking (NEW)
    # ------------------------------------------------------------------
    def save_pending_approval(
        self,
        ticket_number: str,
        source_id: str,
        request_id: str,
        suggestions: list[AllocationSuggestion],
    ) -> None:
        suggestions_data = [
            {
                "member_id": s.member_id,
                "member_name": s.member_name,
                "rank": s.rank,
                "reason": s.reason,
                "current_load": s.current_load,
                "skill_match_score": s.skill_match_score,
            }
            for s in suggestions
        ]
        with self._connect() as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO pending_approvals
                    (ticket_number, source_id, request_id, suggestions_json, created_at)
                VALUES (?, ?, ?, ?, ?)
                """,
                (
                    ticket_number,
                    source_id,
                    request_id,
                    json.dumps(suggestions_data, ensure_ascii=False),
                    utc_now_iso(),
                ),
            )

    def get_pending_approvals(self) -> list[dict[str, Any]]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT * FROM pending_approvals WHERE resolved_at IS NULL",
            ).fetchall()
        return [dict(row) for row in rows]

    def mark_approval_received(
        self,
        ticket_number: str,
        source_id: str,
        chosen_member_id: str,
        approved_at: str,
    ) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                UPDATE pending_approvals
                SET resolved_at = ?, chosen_member_id = ?
                WHERE ticket_number = ? AND source_id = ?
                """,
                (approved_at, chosen_member_id, ticket_number, source_id),
            )

    # ------------------------------------------------------------------
    # Utility (legacy — unchanged behavior)
    # ------------------------------------------------------------------
    def forget_ticket(self, ticket_number: str, source_id: str | None = None) -> int:
        with self._connect() as conn:
            if source_id:
                cursor = conn.execute(
                    "DELETE FROM source_seen_tickets WHERE source_id = ? AND ticket_number = ?",
                    (source_id, ticket_number),
                )
            else:
                cursor = conn.execute(
                    "DELETE FROM source_seen_tickets WHERE ticket_number = ?",
                    (ticket_number,),
                )
            return cursor.rowcount

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------
    @contextmanager
    def _connect(self):
        conn = sqlite3.connect(self.database_path)
        conn.row_factory = sqlite3.Row
        try:
            yield conn
            conn.commit()
        except BaseException:
            conn.rollback()
            raise
        finally:
            conn.close()
