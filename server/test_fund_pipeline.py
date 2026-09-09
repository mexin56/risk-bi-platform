"""资金归结预计算管线测试：独立 DuckDB 写入与 serving 发布。"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

SERVER_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SERVER_DIR))

from fund_pipeline import storage  # noqa: E402
from fund_pipeline import assemble  # noqa: E402
from fund_pipeline.cli import build_fund_path_rows, publish_fund_result  # noqa: E402
from test_fund_attribution import OfflineRunner, _detail_frame  # noqa: E402


@pytest.fixture()
def payload():
    config = json.loads((SERVER_DIR / "config" / "fund_monitor_config.json").read_text(encoding="utf-8"))
    config["dimensions"] = ["traffic_channel", "loan_cust_lifecycle_stage"]
    config["field_labels"] = {"traffic_channel": "流量渠道", "loan_cust_lifecycle_stage": "客户生命周期"}
    runner = OfflineRunner(config, _detail_frame(days=20, spike=True), partition="20260903")
    return config, runner, runner.run()


def test_fund_path_rows_preserve_order_and_abnormal_counts(payload):
    _config, runner, result = payload
    rows = build_fund_path_rows(runner, result)
    assert rows
    assert {"alert_id", "date", "abnormal_order_count", "order_count"}.issubset(rows[0])
    first = rows[0]
    assert first["order_count"] >= first["abnormal_order_count"] >= 0
    assert len({row["date"] for row in rows}) == 20


def test_fund_publish_uses_separate_database_and_serving_snapshot(tmp_path: Path, payload):
    config, runner, result = payload
    db_path = tmp_path / "fund_attribution.duckdb"
    serving_dir = tmp_path / "fund_serving"
    rows = build_fund_path_rows(runner, result)
    run_id = publish_fund_result(
        db_path=db_path,
        serving_dir=serving_dir,
        result=result,
        path_rows=rows,
        pt="20260903",
        offset=0,
        config=config,
        duration_ms=12,
        source="test",
    )
    assert db_path.exists()
    assert run_id.startswith("20260903_0_")
    snapshot = assemble.read_dashboard_snapshot(serving_dir, "20260903", 0)
    assert snapshot is not None
    assert snapshot["meta"]["partition"] == "20260903"
    assert snapshot["summary"]["abnormal_order_count"] > 0
    path_frame = assemble.read_path_daily_frame(serving_dir, "20260903", 0)
    assert path_frame is not None and not path_frame.empty
    assert "order_count" in path_frame.columns


def test_fund_storage_does_not_use_credit_database_path():
    assert storage.DB_PATH.name == "fund_attribution.duckdb"
    assert storage.SERVING_DIR.name == "fund_serving"
