from attribution_status import AttributionStatusStore
from app import AttributionService
from pipeline.cli import _filter_series_from, build_path_rows
import pandas as pd
import pytest
import sqlite3
import json


def test_rule_status_update_requires_action_pt():
    from app import RuleStatusUpdate

    with pytest.raises(Exception):
        RuleStatusUpdate(canonical_path="layer=a", status=1)
    with pytest.raises(Exception):
        RuleStatusUpdate(canonical_path="layer=a", status=1, action_pt=" ")


def test_rule_status_update_returns_current_history_without_warehouse_query(tmp_path, monkeypatch):
    import app as app_module

    store = AttributionStatusStore(tmp_path / "status.sqlite3")
    monkeypatch.setattr(app_module.service, "_status_store", store)

    response = app_module.update_rule_status(
        app_module.RuleStatusUpdate(
            canonical_path="layer=a",
            status=1,
            action_pt="20260901",
        ),
        {"username": "alice"},
    )
    payload = json.loads(response.body)

    assert payload["action_date"] == "20260901"
    assert payload["history"]["canonical_path"] == "layer=a"
    assert payload["history"]["status"] == 1
    assert payload["history"]["entered_pt"] == "20260901"
    assert payload["history"]["is_active"] is True


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


def test_path_rows_keep_full_lookback_and_later_zero_days_for_tracked_rule():
    day_before = pd.Timestamp("2026-08-31").date()
    day_start = pd.Timestamp("2026-09-01").date()
    day_after = pd.Timestamp("2026-09-02").date()

    class FakeRunner:
        config = {"approval_fields": ["approval"]}

        def paths_exact_daily_batch(self, condition_sets):
            return {
                "rule-2": (
                    pd.Series({day_before: 9.0, day_start: 2.0}),
                    pd.Series({day_before: 3.0, day_start: 1.0}),
                    pd.Series(dtype=float),
                    pd.Series(dtype=float),
                )
            }

        def trend_daily_totals(self):
            return pd.Series({day_before: 10.0, day_start: 12.0, day_after: 14.0})

    result = {
        "merged_alerts": [{
            "id": "rule-2",
            "canonical_path": "field=b",
            "tracking_start_pt": "20260901",
            "conditions": [{"field": "field", "value": "b"}],
        }],
        "suppressed_alerts": [],
    }

    rows = build_path_rows(FakeRunner(), result)
    by_day = {row["date"]: row for row in rows}

    assert set(by_day) == {"2026-08-31", "2026-09-01", "2026-09-02"}
    assert by_day["2026-08-31"]["application_count"] == 9.0
    assert by_day["2026-09-01"]["application_count"] == 2.0
    assert by_day["2026-09-02"]["application_count"] == 0


@pytest.mark.parametrize("currently_hit", [True, False])
def test_compute_and_publish_rebuilds_hit_and_non_hit_tracked_rules_from_entry_pt(monkeypatch, currently_hit):
    import pipeline.cli as cli

    day_before = pd.Timestamp("2026-08-31").date()
    day_start = pd.Timestamp("2026-09-01").date()
    day_after = pd.Timestamp("2026-09-02").date()
    rule = {
        "canonical_path": "field=tracked",
        "conditions": [{"field": "field", "value": "tracked"}],
        "source": "已跟踪规则",
    }
    active = {
        "field=tracked": {
            "canonical_path": "field=tracked",
            "status": 2,
            "rule": rule,
            "entered_pt": "20260901",
        }
    }

    class FakeStatusStore:
        def get_active_tagged_rules(self):
            return active

    class FakeRunner:
        config = {"approval_fields": ["approval"]}

        def __init__(self, **_kwargs):
            self.filtered_counts = None

        def run(self):
            return {
                "meta": {},
                "merged_alerts": ([{
                    "id": "tracked-id",
                    "canonical_path": "field=tracked",
                    "conditions": rule["conditions"],
                    "windows": {},
                }] if currently_hit else []),
                "suppressed_alerts": [],
            }

        def paths_exact_daily_batch(self, condition_sets):
            key = condition_sets[0]["key"]
            assert key in {"field=tracked", "tracked-id"}
            return {
                key: (
                    pd.Series({day_before: 9.0, day_start: 2.0}),
                    pd.Series({day_before: 3.0, day_start: 1.0}),
                    pd.Series(dtype=float),
                    pd.Series(dtype=float),
                )
            }

        def trend_daily_totals(self):
            return pd.Series({day_before: 10.0, day_start: 12.0, day_after: 14.0})

        def build_tracked_record(self, _rule, counts):
            self.filtered_counts = counts
            return {
                "id": "tracked-id",
                "canonical_path": "field=tracked",
                "path": "field=tracked",
                "source": "已跟踪规则",
                "level": 0,
                "level_label": "无预警",
                "severity": "slate",
                "conditions": rule["conditions"],
                "windows": {},
            }

    captured = {}
    monkeypatch.setattr(cli, "WarehouseAttributionRunner", FakeRunner)
    monkeypatch.setattr(cli, "refresh_partition_ranges", lambda *_args: {})
    monkeypatch.setattr(cli, "publish_result", lambda **kwargs: captured.update(kwargs) or "run-1")

    class FakeService:
        table_name = "sample_table"
        _status_store = FakeStatusStore()

        def _run_sql_rows(self, _sql):
            return []

    stats = cli.compute_and_publish(FakeService(), {}, "20260902", 0, "test")

    assert stats["run_id"] == "run-1"
    assert captured["result"]["merged_alerts"][0]["tracking_start_pt"] == "20260901"
    assert captured["result"]["merged_alerts"][0].get("is_tracked_only") is (None if currently_hit else True)
    assert captured["result"]["summary"]["tracked_rule_count"] == 1
    assert list(captured["path_rows"][0].keys())
    assert {row["date"] for row in captured["path_rows"]} == {"2026-08-31", "2026-09-01", "2026-09-02"}


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


def test_all_tagged_rules_includes_historical_records_and_current_legacy_rows(tmp_path):
    store = AttributionStatusStore(tmp_path / "attribution_status.sqlite3")
    historical_rule = {
        "canonical_path": "field=historical",
        "conditions": [{"field": "field", "value": "historical"}],
    }
    current_rule = {
        "canonical_path": "field=current",
        "conditions": [{"field": "field", "value": "current"}],
    }

    store.set_status("field=historical", 1, "alice", action_pt="20260831", rule=historical_rule)
    store.set_status("field=historical", 0, "bob", action_pt="20260901")
    store.set_status("field=current", 2, "carol", action_pt="20260902", rule=current_rule)

    rules = store.get_all_tagged_rules()

    assert set(rules) == {"field=historical", "field=current"}
    assert rules["field=historical"] == historical_rule
    assert rules["field=current"] == current_rule


def test_get_active_tagged_rules_uses_current_interval(tmp_path):
    db_path = tmp_path / "attribution_status.sqlite3"
    store = AttributionStatusStore(db_path)
    switched_rule = {
        "canonical_path": "field=switched",
        "conditions": [{"field": "field", "value": "switched"}],
    }
    legacy_rule = {
        "canonical_path": "field=legacy",
        "conditions": [{"field": "field", "value": "legacy"}],
    }

    store.set_status("field=switched", 1, "alice", action_pt="20260831", rule=switched_rule)
    store.set_status("field=switched", 2, "bob", action_pt="20260902")
    with sqlite3.connect(db_path) as connection:
        connection.execute(
            """
            INSERT INTO attribution_rule_status
                (canonical_path, status, updated_by, updated_at, action_date, rule_json)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            ["field=legacy", 1, "carol", "2026-09-02T01:02:03+00:00", "20260901", json.dumps(legacy_rule)],
        )

    active = store.get_active_tagged_rules()

    assert active["field=switched"]["status"] == 2
    assert active["field=switched"]["entered_pt"] == "20260902"
    assert active["field=legacy"]["entered_pt"] == "20260901"


def test_filter_series_from_entered_pt_excludes_prior_days():
    series = pd.Series(
        {
            pd.Timestamp("2026-08-31").date(): 5.0,
            pd.Timestamp("2026-09-01").date(): 7.0,
            pd.Timestamp("2026-09-02").date(): 0.0,
        }
    )

    filtered = _filter_series_from(series, "20260901")

    assert list(filtered.index) == [
        pd.Timestamp("2026-09-01").date(),
        pd.Timestamp("2026-09-02").date(),
    ]
    assert filtered.tolist() == [7.0, 0.0]


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
