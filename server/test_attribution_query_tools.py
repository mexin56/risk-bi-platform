import json
from datetime import date
from decimal import Decimal

import pytest

from attribution_query_tools import AttributionQueryTools, add_approval_rates


class FakeService:
    def __init__(self):
        self.latest_partition_calls = 0
        self.dashboard_calls = []
        self.path_trend_calls = []

    def latest_partition(self):
        self.latest_partition_calls += 1
        return "20260902"

    def dashboard(self, partition=None, force=False, offset=0):
        self.dashboard_calls.append((partition, force, offset))
        selected = partition or "20260902"
        dashboards = {
            "20260901": {
                "meta": {"partition": "20260901"},
                "summary": {
                    "level1_count": 1,
                    "cid_cnt": 10,
                    "approval_cid_cnt": 4,
                    "cnt": 20,
                    "approval_cnt": 6,
                },
                "merged_alerts": [
                    {
                        "id": "aaaaaaaaaaaa",
                        "canonical_path": "channel=organic",
                        "path": "渠道=自然流量",
                        "level": 2,
                        "level_label": "Level2",
                        "status": 2,
                    }
                ],
            },
            "20260902": {
                "meta": {"partition": "20260902"},
                "summary": {
                    "level1_count": 4,
                    "cid_cnt": 5,
                    "approval_cid_cnt": 1,
                    "cnt": 8,
                    "approval_cnt": 4,
                    "generated_on": date(2026, 9, 3),
                    "decimal_value": Decimal("1.25"),
                },
                "merged_alerts": [
                    {
                        "id": "aaaaaaaaaaaa",
                        "canonical_path": "channel=organic",
                        "path": "渠道=自然流量",
                        "level": 3,
                        "level_label": "Level3",
                        "status": 2,
                    },
                    {
                        "id": "bbbbbbbbbbbb",
                        "canonical_path": "product=cash",
                        "path": "产品=现金贷",
                        "level": 1,
                        "level_label": "Level1",
                        "status": 1,
                    },
                ],
            },
        }
        if selected not in dashboards:
            raise RuntimeError(f"pt={selected} 尚未发布预计算快照")
        return dashboards[selected]

    def path_trend(self, record_id, partition=None, offset=0):
        self.path_trend_calls.append((record_id, partition, offset))
        if record_id == "cccccccccccc":
            raise RuntimeError("尚无该路径的预计算趋势数据")
        return {
            "record_id": record_id,
            "partition": partition or "20260902",
            "days": [f"day-{index:02d}" for index in range(1, 66)],
            "daily": [
                {
                    "date": f"2026-08-{index:02d}",
                    "cid_cnt": 10,
                    "approval_cid_cnt": 4,
                    "application_count": 20,
                    "approval_count": 6,
                }
                for index in range(1, 21)
            ],
        }


def assert_envelope(result, *, pt=None, pt_range=None):
    assert result["source"] == "duckdb/serving"
    assert result["pt"] == pt
    assert result["pt_range"] == pt_range
    assert isinstance(result["warnings"], list)
    json.dumps(result, ensure_ascii=False)


def test_tools_expose_only_named_read_methods():
    tools = AttributionQueryTools(FakeService())
    assert sorted(tools.available_tools()) == [
        "compare_partitions",
        "dashboard_summary",
        "find_rules",
        "latest_partition",
        "path_trend",
        "rule_detail",
        "tracked_rule_followup",
    ]


def test_latest_partition_and_dashboard_summary_use_read_only_service_methods():
    service = FakeService()
    tools = AttributionQueryTools(service, page_base_url="http://monitor.example/credit")

    latest = tools.latest_partition()
    summary = tools.dashboard_summary()

    assert_envelope(latest, pt="20260902")
    assert latest["data"] == {"latest_partition": "20260902"}
    assert_envelope(summary, pt="20260902")
    assert summary["data"]["level1_count"] == 4
    assert summary["data"]["通过率（人数）"] == 0.2
    assert summary["data"]["通过率（件数）"] == 0.5
    assert summary["data"]["page_url"] == "http://monitor.example/credit?pt=20260902"
    assert service.dashboard_calls == [("20260902", False, 0)]


def test_find_rules_filters_dashboard_by_keyword_level_and_status():
    service = FakeService()
    result = AttributionQueryTools(service).find_rules(
        "20260902", keyword="自然", level="Level3", status="持续观察"
    )

    assert_envelope(result, pt="20260902")
    assert [item["id"] for item in result["data"]] == ["aaaaaaaaaaaa"]
    assert service.dashboard_calls == [("20260902", False, 0)]


def test_rule_detail_matches_id_canonical_path_or_display_path():
    tools = AttributionQueryTools(FakeService())

    by_id = tools.rule_detail("20260902", "aaaaaaaaaaaa")
    by_canonical = tools.rule_detail("20260902", "channel=organic")
    by_path = tools.rule_detail("20260902", "渠道=自然流量")

    assert_envelope(by_id, pt="20260902")
    assert by_id["data"]["id"] == "aaaaaaaaaaaa"
    assert by_canonical["data"] == by_id["data"]
    assert by_path["data"] == by_id["data"]


def test_missing_rule_returns_structured_error_with_actual_partition():
    result = AttributionQueryTools(FakeService()).rule_detail("20260902", "不存在")

    assert_envelope(result, pt="20260902")
    assert result["data"] is None
    assert result["error"] == "未找到匹配规则"
    assert result["warnings"] == ["pt=20260902 未找到匹配规则：不存在"]


@pytest.mark.parametrize("pt", ["20260902", None])
def test_path_trend_rejects_unsupported_window_without_calling_service(pt):
    service = FakeService()
    result = AttributionQueryTools(service).path_trend(
        pt, "aaaaaaaaaaaa", days=90
    )

    assert_envelope(result, pt=pt)
    assert result["data"] is None
    assert result["error"] == "days 只允许 7、15、30、60"
    assert result["warnings"] == ["days 只允许 7、15、30、60"]
    assert service.latest_partition_calls == 0
    assert service.dashboard_calls == []
    assert service.path_trend_calls == []


@pytest.mark.parametrize("days", [7.5, "7.5", True])
def test_path_trend_rejects_non_integer_days_without_calling_service(days):
    service = FakeService()
    result = AttributionQueryTools(service).path_trend(
        "20260902", "aaaaaaaaaaaa", days=days
    )

    assert_envelope(result, pt="20260902")
    assert result["data"] is None
    assert result["error"] == "days 只允许 7、15、30、60"
    assert result["warnings"] == ["days 只允许 7、15、30、60"]
    assert service.latest_partition_calls == 0
    assert service.dashboard_calls == []
    assert service.path_trend_calls == []


def test_path_trend_uses_allowed_window_and_adds_approval_rates():
    result = AttributionQueryTools(FakeService()).path_trend(
        "20260902", "aaaaaaaaaaaa", days=7
    )

    assert_envelope(result, pt="20260902")
    assert len(result["data"]["days"]) == 7
    assert len(result["data"]["daily"]) == 7
    assert result["data"]["daily"][-1]["通过率（人数）"] == 0.4
    assert result["data"]["daily"][-1]["通过率（件数）"] == 0.3


@pytest.mark.parametrize("days", [7, 15, 30, 60])
def test_path_trend_accepts_each_supported_window_without_warning(days):
    result = AttributionQueryTools(FakeService()).path_trend(
        "20260902", "aaaaaaaaaaaa", days=days
    )

    assert result["warnings"] == []
    assert len(result["data"]["days"]) == days


def test_invalid_partition_returns_error_without_calling_service():
    service = FakeService()
    result = AttributionQueryTools(service).dashboard_summary("2026-09-02")

    assert_envelope(result, pt=None)
    assert result["data"] is None
    assert result["error"] == "pt 格式不合法，应为 8 位日期 YYYYMMDD"
    assert service.dashboard_calls == []


def test_missing_precomputed_trend_returns_structured_error():
    result = AttributionQueryTools(FakeService()).path_trend(
        "20260902", "cccccccccccc", days=15
    )

    assert_envelope(result, pt="20260902")
    assert result["data"] is None
    assert result["error"] == "尚无该路径的预计算趋势数据"
    assert result["warnings"] == ["尚无该路径的预计算趋势数据"]


def test_invalid_record_id_does_not_call_trend_service():
    service = FakeService()
    result = AttributionQueryTools(service).path_trend(
        "20260902", "not-a-record-id", days=15
    )

    assert_envelope(result, pt="20260902")
    assert result["error"] == "record_id 格式不合法，应为 12 位十六进制"
    assert service.path_trend_calls == []


def test_tracked_rule_followup_reads_each_serving_partition_in_range():
    service = FakeService()
    result = AttributionQueryTools(service).tracked_rule_followup(
        "channel=organic", "20260901", "20260902"
    )

    assert_envelope(result, pt_range={"start": "20260901", "end": "20260902"})
    assert [item["pt"] for item in result["data"]] == ["20260901", "20260902"]
    assert [item["level"] for item in result["data"]] == [2, 3]
    assert service.dashboard_calls == [
        ("20260901", False, 0),
        ("20260902", False, 0),
    ]


def test_tracked_rule_followup_keeps_a_placeholder_for_missing_snapshot():
    result = AttributionQueryTools(FakeService()).tracked_rule_followup(
        "channel=organic", "20260902", "20260903"
    )

    assert_envelope(result, pt_range={"start": "20260902", "end": "20260903"})
    assert [item["pt"] for item in result["data"]] == ["20260902", "20260903"]
    assert result["data"][-1] == {
        "pt": "20260903",
        "matched": False,
        "available": False,
    }
    assert result["warnings"] == [
        "pt=20260903: pt=20260903 尚未发布预计算快照"
    ]


def test_latest_partition_falls_back_to_real_public_dashboard_method():
    class DashboardOnlyService:
        def __init__(self):
            self.calls = []

        def dashboard(self, partition=None, force=False, offset=0):
            self.calls.append((partition, force, offset))
            return {"meta": {"partition": "20260902"}}

    service = DashboardOnlyService()
    result = AttributionQueryTools(service).latest_partition()

    assert_envelope(result, pt="20260902")
    assert result["data"] == {"latest_partition": "20260902"}
    assert service.calls == [(None, False, 0)]


def test_compare_partitions_returns_summary_and_level_deltas():
    service = FakeService()
    result = AttributionQueryTools(service).compare_partitions("20260901", "20260902")

    assert_envelope(result, pt_range={"start": "20260901", "end": "20260902"})
    assert result["data"]["pt_a"]["level1_count"] == 1
    assert result["data"]["pt_b"]["level1_count"] == 4
    assert result["data"]["delta"]["level1_count"] == 3
    assert result["data"]["delta"]["通过率（人数）"] == -0.2
    assert result["data"]["delta"]["通过率（件数）"] == 0.2
    assert service.dashboard_calls == [
        ("20260901", False, 0),
        ("20260902", False, 0),
    ]


def test_person_and_item_approval_rates_are_named_and_safe():
    result = add_approval_rates(
        {"cid_cnt": 10, "approval_cid_cnt": 4, "cnt": 20, "approval_cnt": 6}
    )

    assert result["通过率（人数）"] == 0.4
    assert result["通过率（件数）"] == 0.3
    assert result["warnings"] == []


def test_approval_rates_return_none_and_warning_for_zero_denominators():
    result = add_approval_rates(
        {"cid_cnt": 0, "approval_cid_cnt": 4, "cnt": 0, "approval_cnt": 6}
    )

    assert result["通过率（人数）"] is None
    assert result["通过率（件数）"] is None
    assert result["warnings"] == [
        "通过率（人数）分母 cid_cnt 为 0",
        "通过率（件数）分母 cnt 为 0",
    ]


def test_approval_rates_warn_only_for_missing_or_non_numeric_metrics():
    result = add_approval_rates(
        {
            "cid_cnt": 10,
            "cnt": 20,
            "approval_cnt": "not-a-number",
        }
    )

    assert result["通过率（人数）"] is None
    assert result["通过率（件数）"] is None
    assert result["warnings"] == [
        "通过率（人数）缺少指标 approval_cid_cnt",
        "通过率（件数）指标 approval_cnt 非数字",
    ]
