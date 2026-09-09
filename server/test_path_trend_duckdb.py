import duckdb
import pandas as pd

import app
from pipeline.cli import build_path_rows


def test_path_trend_reads_precomputed_duckdb_rows(monkeypatch, tmp_path):
    db_path = tmp_path / "attribution.duckdb"
    conn = duckdb.connect(str(db_path))
    conn.execute(
        """
        CREATE TABLE attr_runs (
            run_id VARCHAR, pt VARCHAR, offset_days INTEGER, generated_at TIMESTAMP
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE attr_path_daily (
            run_id VARCHAR, alert_id VARCHAR, date DATE,
            application_count DOUBLE, total_application_count DOUBLE,
            approval_count DOUBLE, cid_cnt DOUBLE, approval_cid_cnt DOUBLE
        )
        """
    )
    conn.execute("INSERT INTO attr_runs VALUES ('run-1', '20260830', 0, '2026-08-31 01:00:00')")
    conn.executemany(
        "INSERT INTO attr_path_daily VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        [
            ("run-1", "abc123abc123", "2026-08-29", 4, 10, 2, 3, 1),
            ("run-1", "other0000000", "2026-08-29", 1, 10, 1, 1, 1),
            ("run-1", "abc123abc123", "2026-08-30", 6, 12, 3, 5, 2),
        ],
    )
    conn.close()

    record = {
        "id": "abc123abc123",
        "path": "traffic_channel=organic",
        "source": "dimension",
        "level": 1,
        "level_label": "Level1",
        "severity": "warning",
        "primary_window": "1d",
        "primary_window_label": "近1天",
        "windows": {
            "1d": {
                "label": "近1天",
                "observation_start": "2026-08-30",
                "observation_end": "2026-08-30",
                "baseline_daily": 5,
            }
        },
    }
    service = app.AttributionService.__new__(app.AttributionService)
    service._path_trend_cache = {}
    service.dashboard = lambda **_kwargs: {
        "meta": {"partition": "20260830"},
        "merged_alerts": [record],
    }

    monkeypatch.setattr(app, "DB_PATH", db_path)

    class OnlineQueryMustNotRun:
        def __init__(self, **_kwargs):
            raise AssertionError("趋势图不应实时查询 MaxCompute")

    monkeypatch.setattr(app, "WarehouseAttributionRunner", OnlineQueryMustNotRun)
    monkeypatch.setattr(app, "serving_assemble", None)

    result = service.path_trend(record_id=record["id"])

    assert result["summary"]["period_days"] == 2
    assert result["daily"][-1]["date"] == "2026-08-30"
    assert result["daily"][-1]["application_count"] == 6.0
    assert result["daily"][-1]["total_application_count"] == 12.0
    assert result["daily"][-1]["approval_count"] == 3.0
    assert result["daily"][-1]["cid_cnt"] == 5.0
    assert result["daily"][-1]["approval_cid_cnt"] == 2.0
    assert result["daily"][-1]["cid_approval_rate_pct"] == 40.0
    assert result["summary"]["latest_cid_approval_rate_pct"] == 40.0


def test_precomputed_trend_keeps_full_lookback_for_tracked_rule():
    record = {
        "id": "tracked000001",
        "path": "traffic_channel=organic",
        "source": "已跟踪规则",
        "level": 0,
        "level_label": "无预警",
        "severity": "slate",
        "primary_window": "1d",
        "primary_window_label": "近1天",
        "tracking_start_pt": "20260901",
        "windows": {
            "1d": {
                "label": "近1天",
                "observation_start": "2026-09-02",
                "observation_end": "2026-09-02",
                "baseline_daily": 0,
            }
        },
    }
    rows = [
        {"alert_id": "tracked000001", "date": "2026-08-31", "application_count": 5, "total_application_count": 10},
        {"alert_id": "other0000000", "date": "2026-08-31", "application_count": 1, "total_application_count": 10},
        {"alert_id": "tracked000001", "date": "2026-09-01", "application_count": 0, "total_application_count": 12},
        {"alert_id": "other0000000", "date": "2026-09-01", "application_count": 1, "total_application_count": 12},
        {"alert_id": "tracked000001", "date": "2026-09-02", "application_count": 3, "total_application_count": 13},
        {"alert_id": "other0000000", "date": "2026-09-02", "application_count": 1, "total_application_count": 13},
    ]

    result = app.AttributionService._format_precomputed_path_trend(record, rows)

    assert result["summary"]["period_days"] == 3
    assert [item["date"] for item in result["daily"]] == ["2026-08-31", "2026-09-01", "2026-09-02"]
    assert result["daily"][0]["application_count"] == 5.0


def test_build_path_rows_keeps_pre_tag_days_for_tracked_rule():
    class Runner:
        config = {}
        cid_count_field = ""
        cid_approval_field = ""

        def paths_exact_daily_batch(self, _condition_sets):
            dates = [pd.Timestamp("2026-08-31").date(), pd.Timestamp("2026-09-01").date(), pd.Timestamp("2026-09-02").date()]
            return {
                "tracked000001": (
                    pd.Series([5, 0, 3], index=dates),
                    pd.Series([0, 0, 0], index=dates),
                    pd.Series([0, 0, 0], index=dates),
                    pd.Series([0, 0, 0], index=dates),
                )
            }

        def trend_daily_totals(self):
            return {
                pd.Timestamp("2026-08-31").date(): 10,
                pd.Timestamp("2026-09-01").date(): 12,
                pd.Timestamp("2026-09-02").date(): 13,
            }

    result = {
        "merged_alerts": [
            {
                "id": "tracked000001",
                "conditions": [],
                "tracking_start_pt": "20260901",
            }
        ],
        "suppressed_alerts": [],
    }

    rows = build_path_rows(Runner(), result)

    assert [row["date"] for row in rows] == ["2026-08-31", "2026-09-01", "2026-09-02"]
    assert rows[0]["application_count"] == 5.0
