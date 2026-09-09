"""资金归结归因（fund_attribution）引擎测试。

通过覆盖 FundAttributionRunner 的数据访问层（与授信归因模板一致的注入点），
用合成明细数据离线跑通完整编排，验证 v1.2 口径。
"""

from __future__ import annotations

import json
import math
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

SERVER_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SERVER_DIR))

from fund_attribution import (  # noqa: E402
    FundAttributionRunner,
    FundAttributionError,
    normalize_value,
    numeric,
)

CONFIG_PATH = SERVER_DIR / "config" / "fund_monitor_config.json"
BASE_CONFIG = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))


@pytest.fixture()
def config() -> dict:
    config = json.loads(json.dumps(BASE_CONFIG))
    config["dimensions"] = ["traffic_channel", "loan_cust_lifecycle_stage"]
    config["field_labels"] = {
        "traffic_channel": "流量渠道",
        "loan_cust_lifecycle_stage": "客户生命周期",
    }
    return config


def _detail_frame(days: int = 20, spike: bool = True, seed: int = 11) -> pd.DataFrame:
    """合成明细：每行一单（businessid 唯一），flag 为异常标记。"""
    rng = np.random.default_rng(seed)
    date_list = pd.date_range("2026-08-01", periods=days, freq="D").strftime("%Y-%m-%d")
    rows = []
    biz = 0
    for day in date_list:
        for channel in ("CH001", "CH002", "CH_OFF"):
            for stage in ("-1", "新客当月"):
                total = 500
                abnormal = int(rng.binomial(total, 0.01))
                if channel == "CH_OFF":
                    abnormal = 25  # 免归因口径：持续高异常
                if spike and day == date_list[-1] and channel == "CH001":
                    abnormal = 30  # 观察异常 ≥ Level3 门槛(20)
                for _ in range(abnormal):
                    rows.append({"date": day, "traffic_channel": channel, "loan_cust_lifecycle_stage": stage, "flag": 1, "biz": biz})
                    biz += 1
                for _ in range(total - abnormal):
                    rows.append({"date": day, "traffic_channel": channel, "loan_cust_lifecycle_stage": stage, "flag": 0, "biz": biz})
                    biz += 1
    return pd.DataFrame(rows)


class OfflineRunner(FundAttributionRunner):
    """用合成明细实现数据访问层（不触 SQL），验证 run() 编排与指标口径。"""

    def __init__(self, config: dict, detail: pd.DataFrame, offset: int = 0, partition: str = "test"):
        super().__init__(config=config, table="fake.tbl", partition=partition, offset=offset, query_rows=lambda sql: [])
        self.detail = detail

    def _visible(self) -> pd.DataFrame:
        frame = self.detail
        if self.offset > 0:
            dates = sorted(frame["date"].unique())
            drop = set(dates[-self.offset:])
            frame = frame[~frame["date"].isin(drop)]
        return frame

    def resolve_dates(self) -> list[str]:
        return [str(d) for d in sorted(self._visible()["date"].unique())]

    def daily_totals(self) -> tuple[pd.Series, pd.Series]:
        frame = self._visible()
        grouped = frame.groupby("date")["flag"].agg(["sum", "size"])
        return grouped["sum"].astype(float), grouped["size"].astype(float)

    def grouped_field(self, field: str) -> dict[str, tuple[pd.Series, pd.Series]]:
        frame = self._visible()
        grouped = frame.groupby([field, "date"])["flag"].agg(["sum", "size"])
        output: dict[str, tuple[pd.Series, pd.Series]] = {}
        for (value, day), row in grouped.iterrows():
            ab, tot = output.setdefault(normalize_value(value), (pd.Series(dtype=float), pd.Series(dtype=float)))
            ab[pd.Timestamp(day).strftime("%Y-%m-%d")] = float(row["sum"])
            tot[pd.Timestamp(day).strftime("%Y-%m-%d")] = float(row["size"])
        return output

    def grouped_for_condition_sets(
        self, condition_sets: list[dict], extension_field: str
    ) -> dict[str, dict[str, tuple[pd.Series, pd.Series]]]:
        frame = self._visible()
        output: dict[str, dict[str, tuple[pd.Series, pd.Series]]] = {}
        for item in condition_sets:
            mask = pd.Series(True, index=frame.index)
            for part in item["conditions"]:
                mask &= frame[part["field"]].map(normalize_value) == normalize_value(part["value"])
            sub = frame[mask]
            grouped = sub.groupby([extension_field, "date"])["flag"].agg(["sum", "size"])
            value_map: dict[str, tuple[pd.Series, pd.Series]] = {}
            for (value, day), row in grouped.iterrows():
                ab, tot = value_map.setdefault(normalize_value(value), (pd.Series(dtype=float), pd.Series(dtype=float)))
                ab[pd.Timestamp(day).strftime("%Y-%m-%d")] = float(row["sum"])
                tot[pd.Timestamp(day).strftime("%Y-%m-%d")] = float(row["size"])
            output[item["key"]] = value_map
        return output

    def path_daily_batch(self, condition_sets: list[dict]) -> dict[str, tuple[pd.Series, pd.Series]]:
        frame = self._visible()
        output: dict[str, tuple[pd.Series, pd.Series]] = {}
        for item in condition_sets:
            mask = pd.Series(True, index=frame.index)
            for part in item["conditions"]:
                mask &= frame[part["field"]].map(normalize_value) == normalize_value(part["value"])
            sub = frame[mask]
            grouped = sub.groupby("date")["flag"].agg(["sum", "size"])
            ab = pd.Series({pd.Timestamp(day).strftime("%Y-%m-%d"): float(row["sum"]) for day, row in grouped.iterrows()}, dtype=float)
            tot = pd.Series({pd.Timestamp(day).strftime("%Y-%m-%d"): float(row["size"]) for day, row in grouped.iterrows()}, dtype=float)
            output[item["key"]] = (ab, tot)
        return output


def _run(config: dict, detail: pd.DataFrame | None = None, offset: int = 0) -> dict:
    runner = OfflineRunner(config, detail if detail is not None else _detail_frame(), offset=offset)
    return runner.run()


# ---------------------------------------------------------------------------
# 基础工具
# ---------------------------------------------------------------------------

def test_normalize_value_maps_missing_to_minus_one():
    assert normalize_value(None) == "-1"
    assert normalize_value(float("nan")) == "-1"
    assert normalize_value("  ") == "-1"
    assert normalize_value("CH001") == "CH001"


def test_numeric_rounding():
    assert numeric(3.0000001) == 3
    assert numeric(0.123456, 6) == 0.123456
    assert numeric(float("nan")) == 0


# ---------------------------------------------------------------------------
# 窗口与指标口径（v1.2）
# ---------------------------------------------------------------------------

def test_v12_window_split_uses_full_history(config):
    payload = _run(config)
    windows = {item["key"]: item for item in payload["window_overview"]}
    assert windows["1d"]["baseline_days"] == 19
    assert windows["3d"]["baseline_days"] == 17
    assert windows["7d"]["baseline_days"] == 13
    # 三个窗口观察期不同，基准期互不相同
    assert windows["1d"]["baseline_end"] != windows["3d"]["baseline_end"]
    # 全历史基准（不截断为 15 天）
    assert payload["meta"]["date_count"] == 20


def test_offset_shifts_observation_window(config):
    payload = _run(config, offset=1)
    # 回看 1 天：观察期 = 2026-08-19，基准期到此之前
    windows = {item["key"]: item for item in payload["window_overview"]}
    assert windows["1d"]["observation_start"] == "2026-08-19"
    assert windows["1d"]["baseline_end"] == "2026-08-18"


def test_proportion_z_matches_manual_formula(config):
    from fund_attribution import FundMetrics  # noqa: F402

    z = FundMetrics._proportion_z(x_obs=30, n_obs=500, x_base=100, n_base=9000)
    p_pool = 130 / 9500
    expected = (30 / 500 - 100 / 9000) / math.sqrt(p_pool * (1 - p_pool) * (1 / 500 + 1 / 9000))
    assert abs(z - expected) < 1e-9


def test_level_thresholds_all_gates_required(config):
    payload = _run(config)
    thresholds = {t["level"]: t for t in payload["rules"]["thresholds"]}
    assert thresholds[1]["min_observation_count"] == 5
    assert thresholds[2]["min_observation_count"] == 10
    assert thresholds[3]["min_observation_count"] == 20
    assert thresholds[3]["min_z_score"] == 5


# ---------------------------------------------------------------------------
# 主流程
# ---------------------------------------------------------------------------

def test_run_detects_spike_and_attributes_channel(config):
    payload = _run(config)
    alerts = payload["merged_alerts"]
    assert alerts, "尖峰样本应产生正式预警"
    top = alerts[0]
    assert top["level"] >= 1
    assert any(c["field"] == "traffic_channel" and c["value"] == "CH001" for c in top["conditions"])
    # 尖峰在最后一天 → 主窗口应为近1天
    assert top["primary_window"] == "1d"
    assert top["hit_window_count"] >= 1
    # 记录内嵌每日序列（路径趋势数据源）
    assert len(top["daily"]) == 20
    assert top["daily"][-1]["abnormal_order_count"] >= 20


def test_run_no_alert_when_no_spike_and_internal_top_has_reason(config):
    payload = _run(config, _detail_frame(spike=False, seed=13))
    assert payload["merged_alerts"] == []
    internal = payload["top_k"]["internal_top"]
    assert any(item and item.get("reason") for item in internal.values())


def test_suppressed_value_excluded_from_alerts(config):
    config["suppression_rules"] = [
        {"field": "traffic_channel", "value": "CH_OFF", "reason": "免归因：线下渠道口径"}
    ]
    payload = _run(config)
    for record in payload["merged_alerts"] + payload["top_k"]["single_downstream"]:
        assert "CH_OFF" not in record["path"]


def test_expert_forced_single_bypasses_topk_and_merges_source(config):
    config["expert_forced_single"] = [
        {"field": "loan_cust_lifecycle_stage", "values": ["-1", "新客当月"], "label": "强制单维"}
    ]
    payload = _run(config)
    expert_single = payload["expert"]["single"]
    assert {r["path"] for r in expert_single} == {
        "loan_cust_lifecycle_stage=-1",
        "loan_cust_lifecycle_stage=新客当月",
    }
    assert all(r["is_expert_forced"] and r["rule_note"] for r in expert_single)
    # 同路径双链发现 → 来源合并
    merged_sources = {r["source"] for r in payload["merged_alerts"]}
    assert any("专家" in source for source in merged_sources)


def test_merge_dedupes_by_canonical_path(config):
    payload = _run(config)
    canonicals = [r["canonical_path"] for r in payload["merged_alerts"]]
    assert len(canonicals) == len(set(canonicals))


def test_no_baseline_path_is_labelled(config):
    """基准总订单=0 的路径 → 无基准标签，不自动定级，进入人工复核清单。"""
    days = pd.date_range("2026-08-01", periods=10, freq="D").strftime("%Y-%m-%d")
    rows = []
    biz = 0
    for day in days:
        for _ in range(100):
            rows.append({"date": day, "traffic_channel": "CH001", "loan_cust_lifecycle_stage": "-1", "flag": 0, "biz": biz})
            biz += 1
    # 最后一天出现全新取值（历史无任何订单）
    for i in range(8):
        rows.append({"date": days[-1], "traffic_channel": "CH_NEW", "loan_cust_lifecycle_stage": "-1", "flag": 1, "biz": biz})
        biz += 1
    for _ in range(92):
        rows.append({"date": days[-1], "traffic_channel": "CH_NEW", "loan_cust_lifecycle_stage": "-1", "flag": 0, "biz": biz})
        biz += 1
    payload = _run(config, pd.DataFrame(rows))
    ch_new = next((r for r in payload["review_items"] if "CH_NEW" in r["path"]), None)
    assert ch_new is not None, "无基准路径应进入人工复核清单"
    assert ch_new["level"] == 0
    assert "无基准，人工复核" in ch_new["special_labels"]


def test_new_anomaly_path_labelled_when_baseline_abnormal_zero(config):
    """基准异常=0、观察期新增 → 新增异常标签 + 按观察/z 定级。"""
    config["thresholds"] = [
        {"level": 1, "label": "Level1 黄色", "min_observation_count": 5, "min_growth_factor": 1.5,
         "min_rate_lift_factor": 1.5, "min_z_score": 2}
    ]
    days = pd.date_range("2026-08-01", periods=15, freq="D").strftime("%Y-%m-%d")
    rows = []
    biz = 0
    for day in days:
        for channel, total, abnormal in (("CH001", 1000, 2), ("CH002", 800, 0)):
            for _ in range(abnormal):
                rows.append({"date": day, "traffic_channel": channel, "loan_cust_lifecycle_stage": "-1", "flag": 1, "biz": biz})
                biz += 1
            for _ in range(total - abnormal):
                rows.append({"date": day, "traffic_channel": channel, "loan_cust_lifecycle_stage": "-1", "flag": 0, "biz": biz})
                biz += 1
    # 最后一天 CH002 突然出现 6 单异常（观察≥5 且 z 显著）
    for _ in range(6):
        rows.append({"date": days[-1], "traffic_channel": "CH002", "loan_cust_lifecycle_stage": "-1", "flag": 1, "biz": biz})
        biz += 1
    for _ in range(294):
        rows.append({"date": days[-1], "traffic_channel": "CH002", "loan_cust_lifecycle_stage": "-1", "flag": 0, "biz": biz})
        biz += 1
    payload = _run(config, pd.DataFrame(rows))
    ch002 = next(r for r in payload["merged_alerts"] if "CH002" in r["path"])
    window = ch002["windows"][ch002["primary_window"]]
    assert window["is_new_anomaly"]
    assert "新增异常" in ch002["special_labels"]
    assert ch002["level"] >= 1
    assert window["growth_display"] is None  # 增长倍数展示“新增”


def test_sql_field_whitelist_raises(config):
    runner = FundAttributionRunner(
        config=config, table="t", partition="p", offset=0, query_rows=lambda sql: []
    )
    with pytest.raises(FundAttributionError):
        runner._field("not_a_dimension_field")


def test_sql_builders_safe(config):
    """SQL 构造安全：字段白名单 + 取值转义。"""
    runner = FundAttributionRunner(
        config=config, table="pb_biz_credit.lj_cap_flow_analysis_base", partition="20260903",
        offset=0, query_rows=lambda sql: [],
    )
    expr = runner._value_expr("traffic_channel")
    assert "traffic_channel" in expr and "'-1'" in expr
    condition = runner._condition_sql("traffic_channel", "O'Brien")
    assert "''" in condition  # 单引号已转义
    with pytest.raises(FundAttributionError):
        runner._field("drop_table")


def test_internal_top_and_review_shape(config):
    payload = _run(config)
    for layer_item in payload["top_k"]["internal_top"].values():
        if layer_item:
            assert {"layer", "path", "reason", "observation_abnormal_count"} <= set(layer_item)
    assert isinstance(payload["conclusions"], list) and payload["conclusions"]
    assert payload["config_summary"][0]["item"] == "方案版本"
