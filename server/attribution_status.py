"""Persistent manual status for credit-attribution rules.

The attribution result itself is rebuilt by the pipeline, so manual review
state lives in a separate SQLite database and survives result refreshes.
"""

from __future__ import annotations

import sqlite3
from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
from typing import Any


RULE_STATUS_VALUES = frozenset({0, 1, 2})
BUSINESS_TIMEZONE = timezone(timedelta(hours=8))


class AttributionStatusStore:
    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._ensure_schema()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(str(self.path), timeout=30)
        connection.row_factory = sqlite3.Row
        return connection

    def _ensure_schema(self) -> None:
        with self._connect() as connection:
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS attribution_rule_status (
                    canonical_path TEXT PRIMARY KEY,
                    status INTEGER NOT NULL CHECK (status IN (0, 1, 2)),
                    updated_by TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    action_date TEXT,
                    rule_json TEXT
                )
                """
            )
            for column in ("action_date", "rule_json"):
                try:
                    connection.execute(
                        f"ALTER TABLE attribution_rule_status ADD COLUMN {column} TEXT"
                    )
                except sqlite3.OperationalError as exc:
                    if "duplicate column name" not in str(exc).lower():
                        raise
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS attribution_rule_status_history (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    canonical_path TEXT NOT NULL,
                    status INTEGER NOT NULL CHECK (status IN (1, 2)),
                    rule_json TEXT,
                    entered_at TEXT NOT NULL,
                    entered_pt TEXT NOT NULL,
                    entered_by TEXT NOT NULL,
                    exited_at TEXT,
                    exited_pt TEXT,
                    exited_by TEXT
                )
                """
            )

    def get_all(self) -> dict[str, dict[str, Any]]:
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT canonical_path, status, updated_by, updated_at, action_date, rule_json
                FROM attribution_rule_status
                """
            ).fetchall()
        return {
            str(row["canonical_path"]): {
                "canonical_path": str(row["canonical_path"]),
                "status": int(row["status"]),
                "updated_by": str(row["updated_by"]),
                "updated_at": str(row["updated_at"]),
                "action_date": row["action_date"],
                "rule": json.loads(row["rule_json"]) if row["rule_json"] else None,
            }
            for row in rows
        }

    def set_status(
        self,
        canonical_path: str,
        status: int,
        updated_by: str,
        *,
        action_pt: str,
        rule: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        normalized_path = str(canonical_path).strip()
        if not normalized_path:
            raise ValueError("canonical_path cannot be empty")
        normalized_status = int(status)
        if normalized_status not in RULE_STATUS_VALUES:
            raise ValueError("status must be 0, 1, or 2")
        if not isinstance(action_pt, str) or not action_pt.strip():
            raise ValueError("action_pt cannot be empty")
        normalized_action_pt = action_pt.strip()
        normalized_user = str(updated_by).strip() or "unknown"
        now = datetime.now(timezone.utc)
        updated_at = now.isoformat(timespec="seconds")
        action_date = normalized_action_pt if normalized_status in (1, 2) else None
        rule_json = json.dumps(rule, ensure_ascii=False, default=str) if rule is not None else None

        with self._connect() as connection:
            current = connection.execute(
                "SELECT status, action_date, rule_json FROM attribution_rule_status WHERE canonical_path = ?",
                [normalized_path],
            ).fetchone()
            if current and int(current["status"]) in (1, 2) and normalized_status == int(current["status"]):
                action_date = current["action_date"]
                if rule_json is None:
                    rule_json = current["rule_json"]
            elif current and int(current["status"]) in (1, 2):
                connection.execute(
                    """
                    UPDATE attribution_rule_status_history
                    SET exited_at = ?, exited_pt = ?, exited_by = ?
                    WHERE canonical_path = ? AND exited_at IS NULL
                    """,
                    [updated_at, normalized_action_pt, normalized_user, normalized_path],
                )
            if normalized_status in (1, 2) and not (
                current and int(current["status"]) == normalized_status
            ):
                connection.execute(
                    """
                    INSERT INTO attribution_rule_status_history
                        (canonical_path, status, rule_json, entered_at, entered_pt, entered_by)
                    VALUES (?, ?, ?, ?, ?, ?)
                    """,
                    [normalized_path, normalized_status, rule_json, updated_at, normalized_action_pt, normalized_user],
                )
            elif current and int(current["status"]) == normalized_status and normalized_status in (1, 2) and rule_json:
                connection.execute(
                    """
                    UPDATE attribution_rule_status_history
                    SET rule_json = ?
                    WHERE canonical_path = ? AND exited_at IS NULL
                    """,
                    [rule_json, normalized_path],
                )
            connection.execute(
                """
                INSERT INTO attribution_rule_status
                    (canonical_path, status, updated_by, updated_at, action_date, rule_json)
                VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT(canonical_path) DO UPDATE SET
                    status = excluded.status,
                    updated_by = excluded.updated_by,
                    updated_at = excluded.updated_at,
                    action_date = excluded.action_date,
                    rule_json = COALESCE(excluded.rule_json, attribution_rule_status.rule_json)
                """,
                [normalized_path, normalized_status, normalized_user, updated_at, action_date, rule_json],
            )

        return {
            "canonical_path": normalized_path,
            "status": normalized_status,
            "updated_by": normalized_user,
            "updated_at": updated_at,
            "action_date": action_date,
            "rule": rule,
        }

    def get_history(self) -> list[dict[str, Any]]:
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT id, canonical_path, status, rule_json, entered_at, entered_pt,
                       entered_by, exited_at, exited_pt, exited_by
                FROM attribution_rule_status_history
                ORDER BY entered_at DESC, id DESC
                """
            ).fetchall()
        return [
            {
                "id": int(row["id"]),
                "canonical_path": str(row["canonical_path"]),
                "status": int(row["status"]),
                "rule": json.loads(row["rule_json"]) if row["rule_json"] else None,
                "entered_at": str(row["entered_at"]),
                "entered_pt": str(row["entered_pt"]),
                "entered_by": str(row["entered_by"]),
                "exited_at": row["exited_at"],
                "exited_pt": row["exited_pt"],
                "exited_by": row["exited_by"],
                "is_active": row["exited_at"] is None,
            }
            for row in rows
        ]

    def save_rule_if_missing(self, canonical_path: str, rule: dict[str, Any]) -> None:
        rule_json = json.dumps(rule, ensure_ascii=False, default=str)
        with self._connect() as connection:
            connection.execute(
                """
                UPDATE attribution_rule_status
                SET rule_json = ?
                WHERE canonical_path = ? AND (rule_json IS NULL OR rule_json = '')
                """,
                [rule_json, str(canonical_path).strip()],
            )
