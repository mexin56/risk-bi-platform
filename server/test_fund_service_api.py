"""资金归结监控 API 测试（离线注入数据层，隔离临时目录）。"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

SERVER_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SERVER_DIR))
sys.path.insert(0, str(SERVER_DIR))  # noqa: E305  确保 test_fund_attribution 可复用

from test_fund_attribution import OfflineRunner, _detail_frame  # noqa: E402


@pytest.fixture()
def client(monkeypatch, tmp_path: Path):
    import app as attribution_app
    import auth
    import fund_service

    monkeypatch.setattr(fund_service, "DISK_CACHE_DIR", tmp_path / "fund_cache")
    monkeypatch.setattr(fund_service, "FUND_SERVING_DIR", tmp_path / "fund_serving")
    monkeypatch.setattr(fund_service, "STATUS_DB_PATH", tmp_path / "fund_status.sqlite3")
    # 重建 service 单例（指向临时路径）；维度裁剪到合成数据范围
    test_service = fund_service.FundAttributionService()
    test_service.config = json.loads(json.dumps(test_service.config))
    test_service.config["dimensions"] = ["traffic_channel", "loan_cust_lifecycle_stage"]
    test_service.config["field_labels"] = {
        "traffic_channel": "流量渠道",
        "loan_cust_lifecycle_stage": "客户生命周期",
    }
    monkeypatch.setattr(fund_service, "service", test_service)

    real_runner = fund_service.FundAttributionRunner
    detail = _detail_frame(days=20, spike=True)

    def fake_runner_factory(*, config, table, partition, offset=0, query_rows):
        assert table.endswith("lj_cap_flow_analysis_base")
        assert partition == "20260903"
        return OfflineRunner(config, detail, offset=offset, partition=partition)

    monkeypatch.setattr(fund_service, "FundAttributionRunner", fake_runner_factory)
    monkeypatch.setattr(
        fund_service.service, "available_partitions", lambda: ["20260903"]
    )
    monkeypatch.setattr(
        fund_service.service,
        "partition_ranges",
        lambda: {"20260903": {"min": "2026-08-01", "max": "2026-08-20"}},
    )
    # 免登录：以管理员身份调用
    monkeypatch.setattr(
        auth,
        "user_by_token",
        lambda token: (
            {"username": "tester", "display_name": "测试", "role_key": "admin", "enabled": True}
            if token
            else None
        ),
    )
    with TestClient(attribution_app.app) as test_client:
        yield test_client


AUTH = {"Authorization": "Bearer test-token"}


def test_health_configured(client: TestClient):
    response = client.get("/api/fund-attribution/health", headers=AUTH)
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "configured"
    assert body["table"].endswith("lj_cap_flow_analysis_base")
    assert body["version"] == "v1.2"


def test_partitions_endpoint(client: TestClient):
    response = client.get("/api/fund-attribution/partitions", headers=AUTH)
    assert response.status_code == 200
    body = response.json()
    assert body["partitions"] == ["20260903"]
    assert body["ranges"]["20260903"]["max"] == "2026-08-20"


def test_dashboard_requires_compute_first(client: TestClient):
    # 无缓存且非 force → 503 提示自动触发首次计算
    response = client.get("/api/fund-attribution/dashboard", headers=AUTH)
    assert response.status_code == 503
    assert "正在自动触发首次计算" in response.json()["detail"]


def test_dashboard_force_computes_and_caches(client: TestClient):
    response = client.get(
        "/api/fund-attribution/dashboard?force=true", headers=AUTH
    )
    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["meta"]["partition"] == "20260903"
    assert payload["meta"]["date_count"] == 20
    assert payload["summary"]["date_count"] == 20
    assert payload["merged_alerts"], "尖峰样本应产生正式预警"
    # 规则状态字段已 overlay
    assert "status" in payload["merged_alerts"][0]

    # 第二次（非 force）走缓存
    cached = client.get("/api/fund-attribution/dashboard", headers=AUTH)
    assert cached.status_code == 200
    assert cached.json()["meta"]["cache_hit"] is True


def test_dashboard_reads_published_fund_serving_before_online_compute(client: TestClient, tmp_path: Path, monkeypatch):
    import fund_service
    from fund_pipeline.cli import build_fund_path_rows, publish_fund_result

    config = fund_service.service.config
    detail = _detail_frame(days=20, spike=True)
    runner = OfflineRunner(config, detail, partition="20260903")
    result = runner.run()
    publish_fund_result(
        db_path=tmp_path / "published.duckdb",
        serving_dir=tmp_path / "fund_serving",
        result=result,
        path_rows=build_fund_path_rows(runner, result),
        pt="20260903",
        offset=0,
        config=config,
        duration_ms=1,
        source="test",
    )

    def fail_online(*_args, **_kwargs):
        raise AssertionError("published serving should be used before online compute")

    monkeypatch.setattr(fund_service, "FundAttributionRunner", fail_online)
    response = client.get("/api/fund-attribution/dashboard", headers=AUTH)
    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["meta"]["serving"] is True
    assert payload["summary"]["abnormal_order_count"] > 0


def test_path_trend_from_dashboard(client: TestClient):
    dashboard = client.get("/api/fund-attribution/dashboard?force=true", headers=AUTH).json()
    record_id = dashboard["merged_alerts"][0]["id"]
    response = client.get(
        f"/api/fund-attribution/path-trend?record_id={record_id}", headers=AUTH
    )
    assert response.status_code == 200
    trend = response.json()
    assert trend["record_id"] == record_id
    assert len(trend["daily"]) == 20
    assert trend["summary"]["peak_date"]
    # 未知的 record_id → 404/503
    missing = client.get(
        "/api/fund-attribution/path-trend?record_id=000000000000", headers=AUTH
    )
    assert missing.status_code in (404, 503)


def test_rule_status_roundtrip(client: TestClient):
    dashboard = client.get("/api/fund-attribution/dashboard?force=true", headers=AUTH).json()
    record = dashboard["merged_alerts"][0]

    updated = client.put(
        "/api/fund-attribution/rule-status",
        headers=AUTH,
        json={
            "canonical_path": record["canonical_path"],
            "status": 1,
            "action_pt": "20260903",
            "rule": record,
        },
    )
    assert updated.status_code == 200, updated.text
    assert updated.json()["status"] == 1

    # dashboard overlay 显示已标记状态
    after = client.get("/api/fund-attribution/dashboard?force=true", headers=AUTH).json()
    tagged = next(
        (r for r in after["merged_alerts"] if r["canonical_path"] == record["canonical_path"]),
        None,
    )
    assert tagged is not None and tagged["status"] == 1

    history = client.get("/api/fund-attribution/rule-status-history", headers=AUTH)
    assert history.status_code == 200
    assert any(item["canonical_path"] == record["canonical_path"] for item in history.json()["records"])


def test_auth_required(client: TestClient):
    import auth as auth_module

    saved = auth_module.user_by_token
    try:
        auth_module.user_by_token = lambda token: None  # type: ignore[assignment]
        denied = client.get("/api/fund-attribution/partitions")
        assert denied.status_code == 401
    finally:
        auth_module.user_by_token = saved  # type: ignore[assignment]
