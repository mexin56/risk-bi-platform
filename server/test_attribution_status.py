from attribution_status import AttributionStatusStore
from app import AttributionService
from pipeline.cli import build_path_rows
import pandas as pd
import pytest
import sqlite3


def test_rule_status_can_be_updated_cleared_and_reopened(tmp_path):
    db_path = tmp_path / "attribution_status.sqlite3"
    store = AttributionStatusStore(db_path)

    assert store.get_all() == {}

    rule = {
        "id": "abc123456789",
        "canonical_path": "field=a/value=b",
        "path": "field=a / value=b",
        "conditions": [{"field": "field", "value": "a"}, {"field": "value", "value": "b"}],
        "source": "Top-K",
    }
    updated = store.set_status("field=a/value=b", 2, "analyst", action_pt="20260901", rule=rule)
    assert updated["canonical_path"] == "field=a/value=b"
    assert updated["status"] == 2
    assert updated["updated_by"] == "analyst"
    assert updated["updated_at"]
    assert updated["action_date"]
    assert updated["rule"]["conditions"] == rule["conditions"]

    reopened = AttributionStatusStore(db_path)
    assert reopened.get_all()["field=a/value=b"]["status"] == 2

    cleared = reopened.set_status("field=a/value=b", 0, "reviewer", action_pt="20260902")
    assert cleared["status"] == 0
    assert cleared["updated_by"] == "reviewer"
    assert cleared["action_date"] is None
    assert reopened.get_all()["field=a/value=b"]["status"] == 0


def test_dashboard_payload_gets_persisted_status_by_canonical_path(tmp_path):
    store = AttributionStatusStore(tmp_path / "status.sqlite3")
    store.set_status("field=a/value=b", 1, "analyst", action_pt="20260901")
    service = AttributionService()
    service._status_store = store

    payload = {
        "merged_alerts": [
            {"canonical_path": "field=a/value=b"},
            {"canonical_path": "field=x/value=y"},
        ],
        "highlight": {"canonical_path": "field=a/value=b"},
    }

    result = service.with_rule_statuses(payload)
    assert result["merged_alerts"][0]["status"] == 1
    assert result["merged_alerts"][0]["status_updated_by"] == "analyst"
    assert result["merged_alerts"][1]["status"] == 0
    assert result["highlight"]["status"] == 1


def test_path_rows_include_zero_days_for_tracked_rules():
    day_one = pd.Timestamp("2026-09-01").date()
    day_two = pd.Timestamp("2026-09-02").date()

    class FakeRunner:
        config = {"approval_fields": ["approval"]}

        def paths_exact_daily_batch(self, condition_sets):
            assert [item["key"] for item in condition_sets] == ["rule-1"]
            return {
                "rule-1": (
                    pd.Series({day_one: 3.0}),
                    pd.Series({day_one: 1.0}),
                    pd.Series(dtype=float),
                    pd.Series(dtype=float),
                )
            }

        def trend_daily_totals(self):
            return pd.Series({day_one: 10.0, day_two: 12.0})

    result = {
        "merged_alerts": [{
            "id": "rule-1",
            "canonical_path": "field=a",
            "conditions": [{"field": "field", "value": "a"}],
        }],
        "suppressed_alerts": [],
    }

    rows = build_path_rows(FakeRunner(), result)
    by_day = {row["date"]: row for row in rows}
    assert set(by_day) == {"2026-09-01", "2026-09-02"}
    assert by_day["2026-09-02"]["application_count"] == 0
    assert by_day["2026-09-02"]["approval_count"] == 0


def test_status_history_records_entry_exit_switch_and_reentry(tmp_path):
    store = AttributionStatusStore(tmp_path / "status.sqlite3")
    rule = {"canonical_path": "layer=a", "conditions": [{"field": "x"}]}

    store.set_status("layer=a", 1, "alice", action_pt="20260831", rule=rule)
    store.set_status("layer=a", 2, "bob", action_pt="20260901", rule=rule)
    store.set_status("layer=a", 0, "carol", action_pt="20260902", rule=rule)
    store.set_status("layer=a", 2, "dave", action_pt="20260903", rule=rule)

    history = store.get_history()
    assert [item["status"] for item in history] == [2, 2, 1]
    assert history[0]["entered_pt"] == "20260903"
    assert history[0]["exited_pt"] is None
    assert history[1]["entered_pt"] == "20260901"
    assert history[1]["exited_pt"] == "20260902"
    assert history[2]["entered_pt"] == "20260831"
    assert history[2]["exited_pt"] == "20260901"


def test_repeating_same_status_keeps_original_entry_pt(tmp_path):
    store = AttributionStatusStore(tmp_path / "status.sqlite3")
    store.set_status("layer=b", 1, "alice", action_pt="20260831")
    result = store.set_status("layer=b", 1, "bob", action_pt="20260901")

    assert result["action_date"] == "20260831"
    history = store.get_history()
    assert len(history) == 1
    assert history[0]["entered_pt"] == "20260831"
    assert history[0]["entered_by"] == "alice"


def test_action_pt_is_required_and_saved_as_current_action_date(tmp_path):
    store = AttributionStatusStore(tmp_path / "status.sqlite3")
    with pytest.raises(ValueError, match="action_pt"):
        store.set_status("layer=c", 1, "alice", action_pt=" ")

    store.set_status("layer=c", 1, "alice", action_pt="20260901")
    assert store.get_all()["layer=c"]["action_date"] == "20260901"


def test_legacy_status_row_is_preserved_during_schema_migration(tmp_path):
    db_path = tmp_path / "status.sqlite3"
    with sqlite3.connect(db_path) as connection:
        connection.execute(
            """
            CREATE TABLE attribution_rule_status (
                canonical_path TEXT PRIMARY KEY,
                status INTEGER NOT NULL,
                updated_by TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                action_date TEXT,
                rule_json TEXT
            )
            """
        )
        connection.execute(
            """
            INSERT INTO attribution_rule_status
                (canonical_path, status, updated_by, updated_at, action_date, rule_json)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            ["legacy", 1, "alice", "2026-09-01T01:02:03+00:00", None, '{"old":true}'],
        )

    AttributionStatusStore(db_path)

    with sqlite3.connect(db_path) as connection:
        row = connection.execute(
            """
            SELECT canonical_path, status, updated_by, updated_at, action_date, rule_json
            FROM attribution_rule_status
            WHERE canonical_path = ?
            """,
            ["legacy"],
        ).fetchone()
    assert row == ("legacy", 1, "alice", "2026-09-01T01:02:03+00:00", None, '{"old":true}')
