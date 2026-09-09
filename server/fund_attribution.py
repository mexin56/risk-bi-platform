"""中介团伙异常订单异常升高归因（贷前资金归结监控）· 方案 v1.2

与授信归因（warehouse.py）同款架构：数据访问全部在 MaxCompute 侧聚合，
只把结果切片传回进程内；指标/预警/Top-K/专家规则为纯计算层。

方案 v1.2 口径（与授信归因 v2.4 的差异点）：
- 三窗口（近1/3/7天）：观察期固定取最新 1/3/7 天；观察期以外的全部历史日期
  作为该窗口基准期（v1.2 取消 15 天截断，三个窗口基准期互不相同）。
- 双序列：每条路径同时有「异常订单数」（payee_last1_cnt_cate 求和）与
  「总订单数」（行计数）两条日序列；总订单数作为异常率分母。
- 三项核心预警指标：异常订单量增长倍数（观察日均/基准日均）、异常率提升倍数
  （窗口汇总异常率之比）、两样本比例差异 z-score（只看正向升高）。
- 三级预警：Level1 黄(≥5/×1.5/×1.5/z≥2)、Level2 橙(≥10/×2/×2/z≥3)、
  Level3 红(≥20/×3/×3/z≥5)，四项门槛必须全部满足。
- 特殊场景：基准异常=0 & 观察>0 → "新增异常"（按观察订单门槛 + z 定级）；
  基准总订单=0 → "无基准，人工复核"，不自动定级。
- Top-K：单维全量 → 内部 Top10 → 二级 → 内部 Top5 → 三级终止；
  候选门槛：至少一个窗口观察异常订单数 ≥ 5。
- 专家规则：免归因抑制 + 强制单维/双维/三维；只改变"算不算"，不改变指标与阈值。
- 合并去重：规范化路径唯一键；同路径双链发现标记 "Top-K + 专家规则"；
  最终等级 = max(近1/3/7天)；命中窗口数表示持续性，不自动升级。
"""

from __future__ import annotations

import copy
import hashlib
import math
import os
import re
from concurrent.futures import ThreadPoolExecutor
from typing import Any, Callable, Iterable, Sequence

import pandas as pd

SAFE_FIELD = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")

WINDOW_ORDER = ("1d", "3d", "7d")
LEVEL_LABELS = {0: "Level0 无预警", 1: "Level1 黄色", 2: "Level2 橙色", 3: "Level3 红色"}
LEVEL_SEVERITY = {0: "slate", 1: "yellow", 2: "orange", 3: "red"}
LAYER_NAMES = {1: "单维", 2: "二级", 3: "三级"}


def normalize_value(value: Any) -> str:
    """维度取值规范化：空值统一为 "-1"（与样本运行口径一致）。"""
    if value is None:
        return "-1"
    text = str(value).strip()
    if text == "" or text.lower() in {"nan", "none", "null", "nat"}:
        return "-1"
    return text


def numeric(value: Any, digits: int = 4) -> int | float:
    """JSON 友好的数值：整数值化整、浮点保留指定位数。"""
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return 0
    if not math.isfinite(parsed):
        return 0
    if abs(parsed - round(parsed)) < 1e-9:
        return int(round(parsed))
    return round(parsed, digits)


class FundAttributionError(RuntimeError):
    """数据源/配置问题等可安全暴露给前端的错误。"""


class FundMetrics:
    """纯 v1.2 指标与预警逻辑（与数据传输方式无关）。"""

    def __init__(self, config: dict[str, Any], days: list[str], ab_total: pd.Series, tot_total: pd.Series):
        self.config = config
        self.version = str(config.get("version", "v1.2"))
        self.dimensions = list(config["dimensions"])
        self.field_labels = dict(config.get("field_labels", {}))
        self.thresholds = sorted(config["thresholds"], key=lambda item: item["level"])
        self.window_config = list(config["windows"])
        self.candidate_min = float(config.get("candidate_min_observation_count", 5))
        self.top_single = int(config.get("top_k", {}).get("single_limit", 10))
        self.top_pair = int(config.get("top_k", {}).get("pair_limit", 5))
        self.suppression_rules = [
            {**rule, "value": normalize_value(rule.get("value"))}
            for rule in config.get("suppression_rules", [])
        ]
        self.baseline_short_days = int(config.get("baseline_short_days", 14))
        self.small_sample_total = float(config.get("small_sample_observation_total", 30))
        self.level1_min_obs = float(self.thresholds[0]["min_observation_count"])

        self.days = [str(day) for day in days]
        if len(self.days) < 8:
            raise FundAttributionError(f"可用统计日期不足（仅 {len(self.days)} 天），无法构建观察期与基准期。")
        self.ab_total = ab_total.reindex(self.days, fill_value=0.0).astype(float)
        self.tot_total = tot_total.reindex(self.days, fill_value=0.0).astype(float)
        self.window_specs = self._build_window_specs()

    # ------------------------------------------------------------------
    # 窗口切分（v1.2：观察期固定，观察期以外全部历史为基准）
    # ------------------------------------------------------------------
    def _build_window_specs(self) -> list[dict[str, Any]]:
        specs: list[dict[str, Any]] = []
        for item in self.window_config:
            observation_days = int(item["observation_days"])
            if len(self.days) < observation_days + 1:
                raise FundAttributionError(f"可用日期不足 {observation_days + 1} 天，无法构建{item['label']}观察期与基准期。")
            observation = self.days[-observation_days:]
            baseline = self.days[:-observation_days]
            specs.append(
                {
                    "key": item["key"],
                    "label": item["label"],
                    "color": item.get("color", "#5B9BD5"),
                    "purpose": item.get("purpose", ""),
                    "observation_days": observation_days,
                    "observation": observation,
                    "baseline": baseline,
                    "baseline_days": len(baseline),
                    "observation_start": observation[0],
                    "observation_end": observation[-1],
                    "baseline_start": baseline[0] if baseline else None,
                    "baseline_end": baseline[-1] if baseline else None,
                }
            )
        return specs

    # ------------------------------------------------------------------
    # 预警门槛
    # ------------------------------------------------------------------
    def _level_for_gates(self, observation_count: float, growth: float, lift: float, z: float) -> int:
        for threshold in reversed(self.thresholds):
            if (
                observation_count >= float(threshold["min_observation_count"])
                and growth >= float(threshold["min_growth_factor"])
                and lift >= float(threshold["min_rate_lift_factor"])
                and z >= float(threshold["min_z_score"])
            ):
                return int(threshold["level"])
        return 0

    def _level_new_anomaly(self, observation_count: float, z: float) -> int:
        """基准异常=0、观察期新增：只按观察订单门槛 + z 判断（方案 5.1）。"""
        for threshold in reversed(self.thresholds):
            if observation_count >= float(threshold["min_observation_count"]) and z >= float(threshold["min_z_score"]):
                return int(threshold["level"])
        return 0

    @staticmethod
    def _proportion_z(x_obs: float, n_obs: float, x_base: float, n_base: float) -> float:
        """两样本比例差异检验（方案 4.4），只看正向升高。"""
        if n_obs <= 0 or n_base <= 0:
            return 0.0
        p_obs = x_obs / n_obs
        p_base = x_base / n_base
        p_pool = (x_obs + x_base) / (n_obs + n_base)
        variance = p_pool * (1 - p_pool) * (1 / n_obs + 1 / n_base)
        if variance <= 0:
            return 0.0
        return (p_obs - p_base) / math.sqrt(variance)

    # ------------------------------------------------------------------
    # 窗口指标
    # ------------------------------------------------------------------
    def window_metrics(self, spec: dict[str, Any], ab: pd.Series, tot: pd.Series) -> dict[str, Any]:
        ab = ab.reindex(self.days, fill_value=0.0).astype(float)
        tot = tot.reindex(self.days, fill_value=0.0).astype(float)
        obs_idx = spec["observation"]
        base_idx = spec["baseline"]

        ab_obs = float(ab[obs_idx].sum())
        ab_base = float(ab[base_idx].sum())
        tot_obs = float(tot[obs_idx].sum())
        tot_base = float(tot[base_idx].sum())
        g_ab_obs = float(self.ab_total[obs_idx].sum())
        g_ab_base = float(self.ab_total[base_idx].sum())

        obs_days = max(len(obs_idx), 1)
        base_days = max(len(base_idx), 1)
        ab_obs_daily = ab_obs / obs_days
        ab_base_daily = ab_base / base_days
        rate_obs = (ab_obs / tot_obs) if tot_obs > 0 else 0.0
        rate_base = (ab_base / tot_base) if tot_base > 0 else 0.0

        no_baseline = tot_base <= 0
        is_new = (not no_baseline) and ab_base <= 0 and ab_obs > 0

        def ratio(numerator: float, denominator: float) -> float:
            return numerator / denominator if denominator > 0 else 0.0

        growth = ratio(ab_obs_daily, ab_base_daily)
        lift = ratio(rate_obs, rate_base)
        z = self._proportion_z(ab_obs, tot_obs, ab_base, tot_base)
        expected = tot_obs * rate_base if tot_base > 0 else 0.0
        excess = ab_obs - expected
        bp = (rate_obs - rate_base) * 10_000
        # 异常订单结构占比提升倍数：该路径异常订单 ÷ 当期全部异常订单
        obs_structure = (ab_obs / g_ab_obs) if g_ab_obs > 0 else 0.0
        base_structure = (ab_base / g_ab_base) if g_ab_base > 0 else 0.0
        structure_lift = ratio(obs_structure, base_structure)

        if no_baseline:
            level, growth_display, lift_display = 0, None, None
        elif is_new:
            level, growth_display, lift_display = self._level_new_anomaly(ab_obs, z), None, None
        else:
            level = self._level_for_gates(ab_obs, growth, lift, z)
            growth_display, lift_display = growth, lift

        labels: list[str] = []
        if no_baseline:
            labels.append("无基准，人工复核")
        if is_new:
            labels.append("新增异常")
        if 0 < len(base_idx) < self.baseline_short_days:
            labels.append("基准偏短")
        if 0 < tot_obs < self.small_sample_total:
            labels.append("样本偏小")

        return {
            "key": spec["key"],
            "label": spec["label"],
            "color": spec["color"],
            "purpose": spec["purpose"],
            "observation_days": len(obs_idx),
            "baseline_days": len(base_idx),
            "observation_start": spec["observation_start"],
            "observation_end": spec["observation_end"],
            "baseline_start": spec["baseline_start"],
            "baseline_end": spec["baseline_end"],
            "baseline_abnormal_count": numeric(ab_base),
            "observation_abnormal_count": numeric(ab_obs),
            "baseline_abnormal_daily": numeric(ab_base_daily),
            "observation_abnormal_daily": numeric(ab_obs_daily),
            "baseline_total_count": numeric(tot_base),
            "observation_total_count": numeric(tot_obs),
            "baseline_rate": numeric(rate_base, 8),
            "observation_rate": numeric(rate_obs, 8),
            "growth_factor": numeric(growth),
            "growth_display": growth_display,
            "rate_lift_factor": numeric(lift),
            "rate_lift_display": lift_display,
            "rate_change_bp": numeric(bp),
            "z_score": numeric(z, 6),
            "expected_abnormal_count": numeric(expected),
            "excess_abnormal_count": numeric(excess),
            "structure_lift_factor": numeric(structure_lift),
            "level": level,
            "level_label": LEVEL_LABELS[level],
            "severity": LEVEL_SEVERITY[level],
            "special_labels": labels,
            "no_baseline": no_baseline,
            "is_new_anomaly": is_new,
        }

    # ------------------------------------------------------------------
    # 记录构建
    # ------------------------------------------------------------------
    def record(
        self,
        conditions: Sequence[tuple[str, str]],
        ab: pd.Series,
        tot: pd.Series,
        *,
        source: str,
        forced: bool = False,
        rule_note: str = "",
        parent_path: str = "",
        drilldown_rule: str = "",
        enters_next_level: bool = False,
    ) -> dict[str, Any]:
        metrics = [self.window_metrics(spec, ab, tot) for spec in self.window_specs]
        primary = self._primary_window(metrics)
        hits = [item["key"] for item in metrics if item["level"] > 0]
        if len(hits) >= 2:
            anomaly_type = "持续高位"
        elif hits == ["1d"]:
            anomaly_type = "单日尖峰"
        elif hits == ["3d"]:
            anomaly_type = "短期放量"
        elif hits == ["7d"]:
            anomaly_type = "趋势抬升"
        else:
            anomaly_type = "无预警"
        level = max(item["level"] for item in metrics)
        canonical = self.canonical_path(conditions)
        lookup = dict(conditions)
        suppression = [rule["reason"] for rule in self.suppression_rules if lookup.get(rule["field"]) == rule["value"]]
        layer = LAYER_NAMES.get(len(conditions), f"{len(conditions)}维")
        special: list[str] = []
        for item in metrics:
            for label in item["special_labels"]:
                if label not in special:
                    special.append(label)

        ab_r = ab.reindex(self.days, fill_value=0.0).astype(float)
        tot_r = tot.reindex(self.days, fill_value=0.0).astype(float)
        daily = [
            {
                "date": day,
                "abnormal_order_count": numeric(ab_r[day]),
                "order_count": numeric(tot_r[day]),
                "abnormal_rate": numeric(ab_r[day] / tot_r[day], 8) if tot_r[day] > 0 else 0.0,
            }
            for day in self.days
        ]
        return {
            "id": hashlib.sha1(canonical.encode("utf-8")).hexdigest()[:12],
            "source": source,
            "layer": layer,
            "path": self.display_path(conditions),
            "canonical_path": canonical,
            "conditions": [
                {"field": field, "value": value, "label": self.field_labels.get(field, field)}
                for field, value in conditions
            ],
            "level": level,
            "level_label": LEVEL_LABELS[level],
            "severity": LEVEL_SEVERITY[level],
            "anomaly_type": anomaly_type,
            "primary_window": primary["key"],
            "primary_window_label": primary["label"],
            "hit_windows": hits,
            "hit_window_count": len(hits),
            "observation_abnormal_count": primary["observation_abnormal_count"],
            "growth_factor": primary["growth_factor"],
            "rate_lift_factor": primary["rate_lift_factor"],
            "z_score": primary["z_score"],
            "excess_abnormal_count": primary["excess_abnormal_count"],
            "relative_strength": numeric(min(float(primary["growth_factor"]), float(primary["rate_lift_factor"]))),
            "is_expert_forced": forced,
            "rule_note": rule_note,
            "parent_path": parent_path,
            "is_suppressed": bool(suppression),
            "suppression_reasons": suppression,
            "special_labels": special,
            "enters_next_level": enters_next_level,
            "drilldown_rule": drilldown_rule,
            "windows": {item["key"]: item for item in metrics},
            "daily": daily,
        }

    def _primary_window(self, metrics: list[dict[str, Any]]) -> dict[str, Any]:
        eligible = [item for item in metrics if not item["no_baseline"]]
        pool = eligible or metrics
        return max(
            pool,
            key=lambda item: (
                item["level"],
                min(float(item["growth_factor"]), float(item["rate_lift_factor"])),
                float(item["z_score"]),
                float(item["observation_abnormal_count"]),
            ),
        )

    @staticmethod
    def canonical_path(conditions: Iterable[tuple[str, str]]) -> str:
        return " / ".join(sorted(f"{field}={value}" for field, value in conditions))

    @staticmethod
    def display_path(conditions: Iterable[tuple[str, str]]) -> str:
        return " / ".join(f"{field}={value}" for field, value in conditions)

    @staticmethod
    def sort_records(records: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
        """方案 9.1 综合排序：Level → 命中窗口数 → min(增长,提升) → z → 观察异常订单数。"""
        return sorted(
            records,
            key=lambda item: (
                -int(item["level"]),
                -int(item["hit_window_count"]),
                -float(item["relative_strength"]),
                -float(item["z_score"]),
                -float(item["observation_abnormal_count"]),
                item["canonical_path"],
            ),
        )

    def dedupe(self, records: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
        selected: dict[str, dict[str, Any]] = {}
        for record in records:
            existing = selected.get(record["canonical_path"])
            selected[record["canonical_path"]] = record if existing is None else self.sort_records([existing, record])[0]
        return self.sort_records(selected.values())

    @staticmethod
    def mark_downstream(records: list[dict[str, Any]], message: str) -> list[dict[str, Any]]:
        output: list[dict[str, Any]] = []
        for record in records:
            updated = copy.deepcopy(record)
            updated["enters_next_level"] = True
            updated["drilldown_rule"] = message
            output.append(updated)
        return output

    def candidate_ok(self, record: dict[str, Any]) -> bool:
        """Top-K 下钻候选门槛：至少一个窗口观察异常订单数 ≥ 阈值（方案 6.1）。"""
        return any(
            float(item["observation_abnormal_count"]) >= self.candidate_min
            for item in record["windows"].values()
        )

    @staticmethod
    def is_alert(record: dict[str, Any]) -> bool:
        return int(record["level"]) >= 1 and not record["is_suppressed"]

    # ------------------------------------------------------------------
    # 文案与配置说明
    # ------------------------------------------------------------------
    def no_alert_reason(self, record: dict[str, Any]) -> str:
        window = record["windows"][record["primary_window"]]
        if record["is_suppressed"]:
            return "免归因取值"
        if window["no_baseline"]:
            return "无基准，人工复核"
        obs = float(window["observation_abnormal_count"])
        if obs < self.level1_min_obs:
            return f"观察异常订单<{int(self.level1_min_obs)}"
        if window["is_new_anomaly"]:
            if float(window["z_score"]) < float(self.thresholds[0]["min_z_score"]):
                return f"新增异常但z<{int(self.thresholds[0]['min_z_score'])}"
            return "新增异常门槛未同时满足"
        if float(window["growth_factor"]) < float(self.thresholds[0]["min_growth_factor"]):
            return f"异常订单量增长未达{self.thresholds[0]['min_growth_factor']}倍"
        if float(window["rate_lift_factor"]) < float(self.thresholds[0]["min_rate_lift_factor"]):
            return f"异常率提升未达{self.thresholds[0]['min_rate_lift_factor']}倍"
        if float(window["z_score"]) < float(self.thresholds[0]["min_z_score"]):
            return f"统计显著性不足（z<{int(self.thresholds[0]['min_z_score'])}）"
        return "Level1多项门槛未同时满足"

    def conclusions(
        self,
        summary: dict[str, Any],
        window_overview: list[dict[str, Any]],
        merged: list[dict[str, Any]],
        internal_public: dict[str, dict[str, Any] | None],
    ) -> list[str]:
        lines: list[str] = []
        baselines = "、".join(f"{w['label']}基准{w['baseline_days']}天" for w in window_overview)
        lines.append(
            f"1. 按v1.2全历史基准期口径，本分区共{summary['date_count']}天：{baselines}；观察期以外的全部历史日期均参与基准，不再截断为15天。"
        )
        level_text = (
            f"Level3 {summary['level3_count']}条 / Level2 {summary['level2_count']}条 / Level1 {summary['level1_count']}条"
            if summary["merged_alert_count"]
            else "0条"
        )
        lines.append(
            f"2. 本轮正式预警共{summary['merged_alert_count']}条（{level_text}）；"
            f"Top-K单维候选池{summary['single_candidate_count']}个、二级候选池{summary['pair_candidate_count']}个、三级候选池{summary['third_candidate_count']}个。"
        )
        rate_text = "；".join(
            f"{w['label']}观察异常率{float(w['observation_rate']) * 100:.4f}%、基准{float(w['baseline_rate']) * 100:.4f}%、"
            f"异常量增长{float(w['growth_factor']):.2f}倍"
            for w in window_overview
        )
        lines.append(f"3. 大盘三窗口对比：{rate_text}。")
        top_items = [item for item in internal_public.values() if item]
        if top_items:
            item = top_items[0]
            lines.append(
                f"4. 内部最高{item['layer']}候选为 {item['path']}："
                f"{item['primary_window_label']}观察异常订单{item['observation_abnormal_count']}，未达预警门槛（{item['reason']}），保留观察不直接案件化。"
            )
        else:
            lines.append("4. 各层级候选均无待复核的Level0路径。")
        if summary["merged_alert_count"] == 0:
            lines.append(
                "5. 本轮无任何路径达到Level1及以上。原因并非近期无异常订单，而是全历史基准期口径下基准异常水平相对稳定；"
                "若历史包含既往攻击高峰，会抬高基准，使当前较低水平不再被判为异常升高，这是v1.2的预期行为。"
            )
        else:
            top_alert = merged[0]
            lines.append(
                f"5. 最高预警路径：{top_alert['path']}（{top_alert['level_label']}，{top_alert['anomaly_type']}，"
                f"命中{top_alert['hit_window_count']}个窗口，主窗口{top_alert['primary_window_label']}），建议按P0-P3复核优先级处理。"
            )
        return lines

    def config_summary(self) -> list[dict[str, str]]:
        items: list[dict[str, str]] = [
            {"item": "方案版本", "content": f"{self.config.get('scheme_name', '')} {self.version}"},
            {
                "item": "时间口径",
                "content": "近1/3/7天为观察期；每个窗口观察期以外的全部历史日期均作为该窗口基准期。",
            },
        ]
        for spec in self.window_specs:
            baseline_text = f"{spec['baseline_start']} ~ {spec['baseline_end']}" if spec["baseline"] else "无历史基准"
            items.append(
                {
                    "item": spec["label"],
                    "content": f"最新{spec['observation_days']}天（{spec['observation_start']} ~ {spec['observation_end']}）vs 其余全部{spec['baseline_days']}天（{baseline_text}）",
                }
            )
        items.append({"item": "核心指标", "content": "异常订单量增长倍数、异常率提升倍数、两样本比例z-score"})
        for threshold in self.thresholds:
            items.append(
                {
                    "item": threshold["label"],
                    "content": (
                        f"观察异常订单≥{threshold['min_observation_count']}、异常量增长≥{threshold['min_growth_factor']}、"
                        f"异常率提升≥{threshold['min_rate_lift_factor']}、z≥{threshold['min_z_score']}，全部满足"
                    ),
                }
            )
        items.append(
            {"item": "候选保护", "content": f"自动Top-K候选要求至少一个窗口观察异常订单数≥{int(self.candidate_min)}"}
        )
        items.append(
            {
                "item": "Top-K",
                "content": f"单维全量→内部Top{self.top_single}进入二级→内部Top{self.top_pair}进入三级→三级终止",
            }
        )
        items.append(
            {
                "item": "同Level排序",
                "content": "最终Level→命中窗口数→min(异常量增长倍数,异常率提升倍数)→z-score→观察异常订单数",
            }
        )
        for name, rules in (
            ("强制单维", self.config.get("expert_forced_single", [])),
            ("强制双维", self.config.get("expert_forced_pair", [])),
            ("强制三维", self.config.get("expert_forced_third", [])),
        ):
            content = "；".join(
                rule.get("label") or f"{rule.get('field')}={rule.get('values') or rule.get('value')}" for rule in rules
            )
            items.append({"item": name, "content": content or "暂无"})
        return items


class FundAttributionRunner:
    """在 MaxCompute 侧完成全部聚合，只把结果切片传回进程内。

    数据访问层（resolve_dates / daily_totals / grouped_field /
    grouped_for_condition_sets / path_daily_batch）可被子类覆盖，便于离线测试。
    """

    def __init__(
        self,
        *,
        config: dict[str, Any],
        table: str,
        partition: str,
        offset: int = 0,
        query_rows: Callable[[str], list[dict[str, Any]]],
    ) -> None:
        self.config = config
        self.table = table
        self.partition = partition
        self.offset = max(0, int(offset))
        self.query_rows = query_rows
        self.dimensions = list(config["dimensions"])
        self.date_field = config["date_field"]
        self.abnormal_field = config.get("abnormal_field", "payee_last1_cnt_cate")
        self.workers = max(1, min(int(os.getenv("FUND_QUERY_WORKERS", os.getenv("ATTRIBUTION_QUERY_WORKERS", "8"))), 8))
        self._date_filter = ""
        self._table_date_min: str | None = None
        self._table_date_max: str | None = None

    # ------------------------------------------------------------------
    # SQL 构造（与授信归因 warehouse 同款）
    # ------------------------------------------------------------------
    @staticmethod
    def _escape(value: str) -> str:
        return value.replace("'", "''")

    def _field(self, field: str) -> str:
        if field not in self.dimensions or not SAFE_FIELD.fullmatch(field):
            raise FundAttributionError(f"不支持的资金归结归因字段：{field}")
        return field

    def _value_expr(self, field: str) -> str:
        field = self._field(field)
        # 空值统一为 -1（方案字段字典口径）
        return f"CASE WHEN {field} IS NULL OR TRIM(CAST({field} AS STRING)) = '' THEN '-1' ELSE TRIM(CAST({field} AS STRING)) END"

    def _condition_sql(self, field: str, value: str) -> str:
        expression = self._value_expr(field)
        return f"{expression} = '{self._escape(normalize_value(value))}'"

    def _abnormal_expr(self, condition: str = "1=1") -> str:
        safe_field = SAFE_FIELD.fullmatch(self.abnormal_field)
        expression = self.abnormal_field if safe_field else "0"
        return f"SUM(CASE WHEN {condition} THEN CAST({expression} AS BIGINT) ELSE 0 END)"

    @staticmethod
    def _parse_day(value: Any) -> str:
        return pd.Timestamp(str(value)).strftime("%Y-%m-%d")

    # ------------------------------------------------------------------
    # 数据访问层（可被子类覆盖以便离线测试）
    # ------------------------------------------------------------------
    def resolve_dates(self) -> list[str]:
        """定位观察截止日（max_day - offset 天）并列出全部历史日期（v1.2 不截断）。"""
        rows = self.query_rows(
            f"""
            SELECT MAX(TO_CHAR({self.date_field}, 'yyyy-MM-dd')) AS max_day,
                   MIN(TO_CHAR({self.date_field}, 'yyyy-MM-dd')) AS min_day
            FROM {self.table}
            WHERE pt = '{self._escape(self.partition)}'
            """
        )
        max_day = rows[0].get("max_day") if rows else None
        if not max_day:
            raise FundAttributionError(f"pt={self.partition} 无数据，请确认分区日期。")
        min_day = rows[0].get("min_day") or max_day
        self._table_date_min, self._table_date_max = min_day, max_day
        end = (pd.Timestamp(max_day) - pd.Timedelta(days=self.offset)).strftime("%Y-%m-%d")
        end_exclusive = (pd.Timestamp(end) + pd.Timedelta(days=1)).strftime("%Y-%m-%d")
        # v1.2 全历史基准：只裁剪观察截止日之后的数据，不设历史下限
        self._date_filter = f"AND {self.date_field} < TO_DATE('{end_exclusive}', 'yyyy-mm-dd')"
        day_rows = self.query_rows(
            f"""
            SELECT DISTINCT TO_CHAR({self.date_field}, 'yyyy-MM-dd') AS day
            FROM {self.table}
            WHERE pt = '{self._escape(self.partition)}'
              {self._date_filter}
            ORDER BY day
            """
        )
        dates = [self._parse_day(row["day"]) for row in day_rows if row.get("day")]
        if not dates:
            raise FundAttributionError(
                f"pt={self.partition} 在观察截止日 {end} 前无可用日期（数据范围 {min_day} ~ {max_day}，请调小回看天数）。"
            )
        return dates

    def daily_totals(self) -> tuple[pd.Series, pd.Series]:
        """全样本每日异常订单数与总订单数。"""
        sql = f"""
            SELECT TO_CHAR({self.date_field}, 'yyyy-MM-dd') AS day,
                   {self._abnormal_expr()} AS abnormal_order_count,
                   COUNT(1) AS order_count
            FROM {self.table}
            WHERE pt = '{self._escape(self.partition)}'
              {self._date_filter}
            GROUP BY TO_CHAR({self.date_field}, 'yyyy-MM-dd')
            ORDER BY day
        """
        rows = self.query_rows(sql)
        if not rows:
            raise FundAttributionError(f"pt={self.partition} 无聚合数据。")
        ab = pd.Series(
            {self._parse_day(row["day"]): float(row.get("abnormal_order_count") or 0) for row in rows},
            dtype=float,
        )
        tot = pd.Series(
            {self._parse_day(row["day"]): float(row.get("order_count") or 0) for row in rows},
            dtype=float,
        )
        return ab, tot

    def grouped_field(self, field: str) -> dict[str, tuple[pd.Series, pd.Series]]:
        """单维扫描：每个取值的每日（异常订单数, 总订单数）。"""
        expression = self._value_expr(field)
        sql = f"""
            SELECT {expression} AS value,
                   TO_CHAR({self.date_field}, 'yyyy-MM-dd') AS day,
                   SUM(CAST({self.abnormal_field} AS BIGINT)) AS abnormal_order_count,
                   COUNT(1) AS order_count
            FROM {self.table}
            WHERE pt = '{self._escape(self.partition)}'
              {self._date_filter}
            GROUP BY {expression}, TO_CHAR({self.date_field}, 'yyyy-MM-dd')
        """
        return self._pair_series_map(self.query_rows(sql))

    def grouped_for_condition_sets(
        self,
        condition_sets: list[dict[str, Any]],
        extension_field: str,
    ) -> dict[str, dict[str, tuple[pd.Series, pd.Series]]]:
        """对若干父路径批量求「扩展维度取值 → 每日（异常, 总量）」序列。

        与授信归因同款条件聚合：一次扫描服务同一扩展维度下的全部父路径。
        """
        if not condition_sets:
            return {}
        extension_expr = self._value_expr(extension_field)
        aliases: list[str] = []
        expressions: list[str] = []
        where_conditions: list[str] = []
        for index, item in enumerate(condition_sets):
            conditions = [(part["field"], part["value"]) for part in item["conditions"]]
            condition = " AND ".join(self._condition_sql(field, value) for field, value in conditions)
            alias = f"seed_{index}"
            aliases.append(alias)
            expressions.append(f"{self._abnormal_expr(condition)} AS {alias}")
            expressions.append(f"SUM(CASE WHEN {condition} THEN 1 ELSE 0 END) AS {alias}_tot")
            where_conditions.append(f"({condition})")
        sql = f"""
            SELECT {extension_expr} AS value,
                   TO_CHAR({self.date_field}, 'yyyy-MM-dd') AS day,
                   {', '.join(expressions)}
            FROM {self.table}
            WHERE pt = '{self._escape(self.partition)}'
              {self._date_filter}
            GROUP BY {extension_expr}, TO_CHAR({self.date_field}, 'yyyy-MM-dd')
        """
        rows = self.query_rows(sql)
        buckets: dict[str, dict[str, dict[str, float]]] = {
            item["key"]: {} for item in condition_sets
        }
        for row in rows:
            value = normalize_value(row.get("value"))
            day = self._parse_day(row["day"])
            for index, item in enumerate(condition_sets):
                abnormal = float(row.get(aliases[index]) or 0)
                total = float(row.get(f"{aliases[index]}_tot") or 0)
                bucket = buckets[item["key"]].setdefault(value, {})
                bucket.setdefault("_ab", {})[day] = abnormal
                bucket.setdefault("_tot", {})[day] = total
        output: dict[str, dict[str, tuple[pd.Series, pd.Series]]] = {}
        for key, value_map in buckets.items():
            output[key] = {
                value: (
                    pd.Series(series["_ab"], dtype=float),
                    pd.Series(series["_tot"], dtype=float),
                )
                for value, series in value_map.items()
            }
        return output

    def path_daily_batch(
        self, condition_sets: list[dict[str, Any]]
    ) -> dict[str, tuple[pd.Series, pd.Series]]:
        """一次（分块多次）扫描求任意路径集合的每日（异常, 总量）序列。"""
        if not condition_sets:
            return {}
        merged_ab: dict[str, dict[str, float]] = {item["key"]: {} for item in condition_sets}
        merged_tot: dict[str, dict[str, float]] = {item["key"]: {} for item in condition_sets}
        chunk_size = 80
        for start in range(0, len(condition_sets), chunk_size):
            chunk = condition_sets[start:start + chunk_size]
            aliases: list[str] = []
            expressions: list[str] = []
            where_conditions: list[str] = []
            for index, item in enumerate(chunk):
                conditions = [(part["field"], part["value"]) for part in item["conditions"]]
                condition = " AND ".join(self._condition_sql(field, value) for field, value in conditions)
                alias = f"path_{index}"
                aliases.append(alias)
                expressions.append(f"{self._abnormal_expr(condition)} AS {alias}")
                expressions.append(f"SUM(CASE WHEN {condition} THEN 1 ELSE 0 END) AS {alias}_tot")
                where_conditions.append(f"({condition})")
            sql = f"""
                SELECT TO_CHAR({self.date_field}, 'yyyy-MM-dd') AS day,
                       {', '.join(expressions)}
                FROM {self.table}
                WHERE pt = '{self._escape(self.partition)}'
                  {self._date_filter}
                  AND ({' OR '.join(where_conditions)})
                GROUP BY TO_CHAR({self.date_field}, 'yyyy-MM-dd')
            """
            for row in self.query_rows(sql):
                day = self._parse_day(row["day"])
                for index, item in enumerate(chunk):
                    abnormal = float(row.get(aliases[index]) or 0)
                    total = float(row.get(f"{aliases[index]}_tot") or 0)
                    if abnormal:
                        merged_ab[item["key"]][day] = abnormal
                    if total:
                        merged_tot[item["key"]][day] = total
        return {
            key: (pd.Series(merged_ab[key], dtype=float), pd.Series(merged_tot[key], dtype=float))
            for key in merged_ab
        }

    @staticmethod
    def _pair_series_map(rows: list[dict[str, Any]]) -> dict[str, tuple[pd.Series, pd.Series]]:
        buckets: dict[str, dict[str, dict[str, float]]] = {}
        for row in rows:
            value = normalize_value(row.get("value"))
            day = pd.Timestamp(str(row["day"])).strftime("%Y-%m-%d")
            bucket = buckets.setdefault(value, {})
            bucket.setdefault("_ab", {})[day] = float(row.get("abnormal_order_count") or 0)
            bucket.setdefault("_tot", {})[day] = float(row.get("order_count") or 0)
        return {
            value: (pd.Series(series["_ab"], dtype=float), pd.Series(series["_tot"], dtype=float))
            for value, series in buckets.items()
        }

    def _parallel_fields(self, func: Callable[[str], Any], fields: Iterable[str]) -> dict[str, Any]:
        field_list = list(fields)
        output: dict[str, Any] = {}
        with ThreadPoolExecutor(max_workers=self.workers) as executor:
            futures = {executor.submit(func, field): field for field in field_list}
            for future in futures:
                field = futures[future]
                output[field] = future.result()
        return output

    # ------------------------------------------------------------------
    # 扫描编排
    # ------------------------------------------------------------------
    def _evaluate_values(
        self,
        metrics: FundMetrics,
        base_conditions: list[tuple[str, str]],
        field: str,
        value_map: dict[str, tuple[pd.Series, pd.Series]],
        *,
        source: str,
        forced: bool = False,
        rule_note: str = "",
        parent_path: str = "",
    ) -> list[dict[str, Any]]:
        dimension_order = {name: index for index, name in enumerate(self.dimensions)}
        records: list[dict[str, Any]] = []
        for value, (ab, tot) in value_map.items():
            conditions = [*base_conditions, (field, value)]
            conditions = sorted(conditions, key=lambda item: dimension_order.get(item[0], 99))
            records.append(
                metrics.record(
                    conditions,
                    ab,
                    tot,
                    source=source,
                    forced=forced,
                    rule_note=rule_note,
                    parent_path=parent_path,
                )
            )
        return records

    @staticmethod
    def _conditions(record: dict[str, Any]) -> list[tuple[str, str]]:
        return [(part["field"], part["value"]) for part in record["conditions"]]

    def run(self) -> dict[str, Any]:
        from datetime import datetime, timezone

        dates = self.resolve_dates()
        ab_total, tot_total = self.daily_totals()
        metrics = FundMetrics(self.config, dates, ab_total, tot_total)

        empty = pd.Series(dtype=float)

        # ================= Top-K 自动链路 =================
        single_groups = self._parallel_fields(self.grouped_field, self.dimensions)
        all_single: list[dict[str, Any]] = []
        for field in self.dimensions:
            all_single.extend(
                self._evaluate_values(metrics, [], field, single_groups.get(field, {}), source="Top-K")
            )
        all_single = metrics.dedupe(all_single)
        single_pool = [r for r in all_single if not r["is_suppressed"] and metrics.candidate_ok(r)]
        single_seed = metrics.mark_downstream(
            metrics.sort_records(single_pool)[: metrics.top_single],
            f"单维 Top{metrics.top_single} 进入二级组合",
        )
        topk_single_alerts = [r for r in all_single if metrics.is_alert(r)]

        pair_groups = self._parallel_fields(
            lambda field: self.grouped_for_condition_sets(
                [{"key": r["canonical_path"], "conditions": r["conditions"]} for r in single_seed], field
            ),
            self.dimensions,
        )
        all_pair: list[dict[str, Any]] = []
        for seed in single_seed:
            base_conditions = self._conditions(seed)
            occupied = {field for field, _ in base_conditions}
            for field in self.dimensions:
                if field in occupied:
                    continue
                all_pair.extend(
                    self._evaluate_values(
                        metrics,
                        base_conditions,
                        field,
                        pair_groups.get(field, {}).get(seed["canonical_path"], {}),
                        source="Top-K",
                        parent_path=seed["path"],
                    )
                )
        all_pair = metrics.dedupe(all_pair)
        pair_pool = [r for r in all_pair if not r["is_suppressed"] and metrics.candidate_ok(r)]
        pair_seed = metrics.mark_downstream(
            metrics.sort_records(pair_pool)[: metrics.top_pair],
            f"二级 Top{metrics.top_pair} 进入三级组合",
        )
        topk_pair_alerts = [r for r in all_pair if metrics.is_alert(r)]

        third_groups = self._parallel_fields(
            lambda field: self.grouped_for_condition_sets(
                [{"key": r["canonical_path"], "conditions": r["conditions"]} for r in pair_seed], field
            ),
            self.dimensions,
        )
        all_third: list[dict[str, Any]] = []
        for seed in pair_seed:
            base_conditions = self._conditions(seed)
            occupied = {field for field, _ in base_conditions}
            for field in self.dimensions:
                if field in occupied:
                    continue
                all_third.extend(
                    self._evaluate_values(
                        metrics,
                        base_conditions,
                        field,
                        third_groups.get(field, {}).get(seed["canonical_path"], {}),
                        source="Top-K",
                        parent_path=seed["path"],
                    )
                )
        all_third = metrics.dedupe(all_third)
        topk_third_alerts = [r for r in all_third if metrics.is_alert(r)]

        # ================= 专家规则链路 =================
        expert_forced_single = self.config.get("expert_forced_single", [])
        expert_single_records: list[dict[str, Any]] = []
        expert_single_conditions: list[list[tuple[str, str]]] = []
        for rule in expert_forced_single:
            field = rule.get("field")
            if field not in self.dimensions:
                continue
            values = rule.get("values") or ([rule.get("value")] if rule.get("value") else [])
            for raw in values:
                value = normalize_value(raw)
                series_pair = single_groups.get(field, {}).get(value)
                if series_pair is None:
                    continue
                conditions = [(field, value)]
                expert_single_conditions.append(conditions)
                expert_single_records.append(
                    metrics.record(
                        conditions,
                        series_pair[0],
                        series_pair[1],
                        source="专家",
                        forced=True,
                        rule_note="强制单维进入二级扫描",
                    )
                )

        topk_seed_canonicals = {seed["canonical_path"] for seed in single_seed}
        expert_only_seeds = [
            {"key": metrics.canonical_path(conditions), "conditions": [{"field": f, "value": v} for f, v in conditions]}
            for conditions in expert_single_conditions
            if metrics.canonical_path(conditions) not in topk_seed_canonicals
        ]
        expert_pair_groups = self._parallel_fields(
            lambda field: self.grouped_for_condition_sets(expert_only_seeds, field),
            self.dimensions,
        )
        expert_pair_records: list[dict[str, Any]] = []
        for seed_item in expert_only_seeds:
            base_conditions = [(part["field"], part["value"]) for part in seed_item["conditions"]]
            parent_path = metrics.display_path(base_conditions)
            occupied = {field for field, _ in base_conditions}
            for field in self.dimensions:
                if field in occupied:
                    continue
                expert_pair_records.extend(
                    self._evaluate_values(
                        metrics,
                        base_conditions,
                        field,
                        expert_pair_groups.get(field, {}).get(seed_item["key"], {}),
                        source="专家",
                        forced=True,
                        rule_note="强制单维种子下钻",
                        parent_path=parent_path,
                    )
                )
        expert_pair_records = metrics.dedupe(expert_pair_records)
        expert_pair_alerts = [r for r in expert_pair_records if metrics.is_alert(r)]

        # 强制双维：与强制单维组合，不受 Top5 限制、必须进入三级
        forced_pair_records: list[dict[str, Any]] = []
        forced_pair_sets = self.config.get("expert_forced_pair", [])
        if forced_pair_sets and expert_single_conditions:
            condition_sets: list[dict[str, Any]] = []
            seen_pair: set[str] = set()
            for rule in forced_pair_sets:
                field = rule.get("field")
                if field not in self.dimensions:
                    continue
                values = rule.get("values") or ([rule.get("value")] if rule.get("value") else [])
                for raw in values:
                    value = normalize_value(raw)
                    for seed_conditions in expert_single_conditions:
                        if any(f == field for f, _ in seed_conditions):
                            continue
                        conditions = [*seed_conditions, (field, value)]
                        canonical = metrics.canonical_path(conditions)
                        if canonical in seen_pair:
                            continue
                        seen_pair.add(canonical)
                        condition_sets.append(
                            {
                                "key": canonical,
                                "conditions": [{"field": f, "value": v} for f, v in conditions],
                            }
                        )
            exact_series = self.path_daily_batch(condition_sets)
            for item in condition_sets:
                ab, tot = exact_series.get(item["key"], (empty, empty))
                conditions = [(part["field"], part["value"]) for part in item["conditions"]]
                forced_pair_records.append(
                    metrics.record(
                        conditions,
                        ab,
                        tot,
                        source="专家",
                        forced=True,
                        rule_note="强制双维，不受Top5限制进入三级",
                        parent_path=metrics.display_path(conditions[:1]),
                    )
                )

        # ================= 第三层（Top5 + 强制双维 + 专家二级预警，一次条件聚合）=================
        third_seed_items: list[tuple[list[tuple[str, str]], str]] = [
            (self._conditions(seed), "Top-K") for seed in pair_seed
        ]
        third_seed_items += [(self._conditions(r), "专家") for r in forced_pair_records]
        third_seed_items += [(self._conditions(r), "专家") for r in expert_pair_alerts]
        seen_third: set[str] = set()
        third_condition_sets: list[dict[str, Any]] = []
        third_chain: dict[str, str] = {}
        for conditions, chain in third_seed_items:
            canonical = metrics.canonical_path(conditions)
            if canonical in seen_third:
                continue
            seen_third.add(canonical)
            third_chain[canonical] = chain
            third_condition_sets.append(
                {"key": canonical, "conditions": [{"field": f, "value": v} for f, v in conditions]}
            )
        third_groups = self._parallel_fields(
            lambda field: self.grouped_for_condition_sets(third_condition_sets, field),
            self.dimensions,
        )
        all_third_ext: list[dict[str, Any]] = []
        for item in third_condition_sets:
            base_conditions = [(part["field"], part["value"]) for part in item["conditions"]]
            chain = third_chain[item["key"]]
            parent_path = metrics.display_path(base_conditions[:2])
            occupied = {field for field, _ in base_conditions}
            for field in self.dimensions:
                if field in occupied:
                    continue
                all_third_ext.extend(
                    self._evaluate_values(
                        metrics,
                        base_conditions,
                        field,
                        third_groups.get(field, {}).get(item["key"], {}),
                        source=chain,
                        forced=chain == "专家",
                        rule_note="强制双维/专家二级路径下钻" if chain == "专家" else "",
                        parent_path=parent_path,
                    )
                )
        all_third_ext = metrics.dedupe(all_third_ext)
        topk_third_alerts = metrics.dedupe(
            [*topk_third_alerts, *[r for r in all_third_ext if metrics.is_alert(r) and "Top-K" in r["source"]]]
        )
        expert_third_alerts = [
            r for r in all_third_ext if metrics.is_alert(r) and "专家" in r["source"]
        ]
        third_pool = [
            r
            for r in metrics.dedupe([*all_third, *all_third_ext])
            if not r["is_suppressed"] and metrics.candidate_ok(r)
        ]

        # ================= 合并与去重 =================
        expert_single_alerts = [r for r in expert_single_records if metrics.is_alert(r)]
        merged_alerts = self._merge_alerts(
            metrics,
            [
                topk_single_alerts,
                topk_pair_alerts,
                topk_third_alerts,
                expert_single_alerts,
                expert_pair_alerts,
                expert_third_alerts,
            ],
        )

        internal_top = {
            "single": self._internal_top(metrics, single_pool),
            "pair": self._internal_top(metrics, pair_pool),
            "third": self._internal_top(metrics, third_pool),
        }
        internal_public = {
            key: (self._public_internal(item) if item else None) for key, item in internal_top.items()
        }
        review_items = self._review_items(
            metrics, [single_pool, pair_pool, third_pool, expert_single_records]
        )

        window_overview = [
            metrics.window_metrics(spec, ab_total, tot_total) for spec in metrics.window_specs
        ]
        daily_trend = [
            {
                "date": day,
                "abnormal_order_count": numeric(ab_total.get(day, 0.0)),
                "order_count": numeric(tot_total.get(day, 0.0)),
                "abnormal_rate": numeric(ab_total.get(day, 0.0) / tot_total[day], 8) if tot_total.get(day, 0.0) > 0 else 0.0,
            }
            for day in dates
        ]

        summary = {
            "date_start": dates[0],
            "date_end": dates[-1],
            "date_count": len(dates),
            "total_order_count": numeric(float(tot_total.sum())),
            "abnormal_order_count": numeric(float(ab_total.sum())),
            "overall_abnormal_rate": numeric(
                float(ab_total.sum()) / float(tot_total.sum()) if float(tot_total.sum()) > 0 else 0.0, 8
            ),
            "single_candidate_count": len(single_pool),
            "single_alert_count": len(topk_single_alerts),
            "pair_candidate_count": len(pair_pool),
            "pair_alert_count": len(topk_pair_alerts),
            "third_candidate_count": len(third_pool),
            "third_alert_count": len(topk_third_alerts),
            "expert_single_count": len(expert_single_records),
            "expert_pair_alert_count": len(expert_pair_alerts),
            "expert_third_alert_count": len(expert_third_alerts),
            "merged_alert_count": len(merged_alerts),
            "level1_count": sum(1 for r in merged_alerts if r["level"] == 1),
            "level2_count": sum(1 for r in merged_alerts if r["level"] == 2),
            "level3_count": sum(1 for r in merged_alerts if r["level"] == 3),
            "new_anomaly_alert_count": sum(
                1 for r in merged_alerts if r["windows"][r["primary_window"]]["is_new_anomaly"]
            ),
        }

        highlight = merged_alerts[0] if merged_alerts else (
            expert_single_records[0] if expert_single_records else None
        )

        payload = {
            "meta": {
                "version": metrics.version,
                "scheme_name": self.config.get("scheme_name", ""),
                "source": "MaxCompute",
                "table": self.table,
                "partition": self.partition,
                "offset_days": self.offset,
                "table_date_min": self._table_date_min,
                "table_date_max": self._table_date_max,
                "date_start": dates[0],
                "date_end": dates[-1],
                "date_count": len(dates),
                "dimension_count": len(self.dimensions),
                "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                "candidate_min_observation_count": int(metrics.candidate_min),
                "top_k": {"single_limit": metrics.top_single, "pair_limit": metrics.top_pair},
            },
            "summary": summary,
            "daily_trend": daily_trend,
            "window_overview": window_overview,
            "highlight": highlight,
            "merged_alerts": merged_alerts,
            "top_k": {
                "single_downstream": single_seed,
                "pair_downstream": pair_seed,
                "third_alerts": topk_third_alerts,
                "counts": {
                    "single_scanned": len(all_single),
                    "single_pool": len(single_pool),
                    "single_alerts": len(topk_single_alerts),
                    "pair_scanned": len(all_pair),
                    "pair_pool": len(pair_pool),
                    "pair_alerts": len(topk_pair_alerts),
                    "third_scanned": len(all_third) + len(all_third_ext),
                    "third_alerts": len(topk_third_alerts),
                },
                "internal_top": internal_public,
            },
            "expert": {
                "single": expert_single_records,
                "pair": expert_pair_alerts,
                "third": expert_third_alerts,
                "counts": {
                    "single": len(expert_single_records),
                    "pair_alerts": len(expert_pair_alerts),
                    "third_alerts": len(expert_third_alerts),
                },
            },
            "review_items": review_items,
            "conclusions": metrics.conclusions(summary, window_overview, merged_alerts, internal_public),
            "rules": {
                "thresholds": [
                    {
                        "level": t["level"],
                        "label": t["label"],
                        "min_observation_count": t["min_observation_count"],
                        "min_growth_factor": t["min_growth_factor"],
                        "min_rate_lift_factor": t["min_rate_lift_factor"],
                        "min_z_score": t["min_z_score"],
                    }
                    for t in metrics.thresholds
                ],
                "windows": [
                    {
                        "key": spec["key"],
                        "label": spec["label"],
                        "purpose": spec["purpose"],
                        "color": spec["color"],
                        "observation_days": spec["observation_days"],
                        "baseline_days": spec["baseline_days"],
                        "observation_start": spec["observation_start"],
                        "observation_end": spec["observation_end"],
                        "baseline_start": spec["baseline_start"],
                        "baseline_end": spec["baseline_end"],
                    }
                    for spec in metrics.window_specs
                ],
                "suppression_rules": list(self.config.get("suppression_rules", [])),
                "expert_forced_single": list(self.config.get("expert_forced_single", [])),
                "expert_forced_pair": list(self.config.get("expert_forced_pair", [])),
                "expert_forced_third": list(self.config.get("expert_forced_third", [])),
                "field_labels": dict(metrics.field_labels),
                "candidate_min_observation_count": int(metrics.candidate_min),
            },
            "config_summary": metrics.config_summary(),
            "field_dictionary": self._field_dictionary(metrics, single_groups),
        }
        return payload

    # ------------------------------------------------------------------
    # 合并 / 内部候选 / 复核清单 / 字段字典
    # ------------------------------------------------------------------
    @staticmethod
    def _merge_alerts(metrics: FundMetrics, groups: Sequence[Sequence[dict[str, Any]]]) -> list[dict[str, Any]]:
        merged: dict[str, dict[str, Any]] = {}
        for group in groups:
            for record in group:
                key = record["canonical_path"]
                current = merged.get(key)
                if current is None:
                    merged[key] = copy.deepcopy(record)
                    continue
                winner = metrics.sort_records([current, record])[0]
                source_set = {current["source"], record["source"]}
                winner["source"] = "Top-K + 专家规则" if len(source_set) > 1 else next(iter(source_set))
                winner["is_expert_forced"] = bool(current["is_expert_forced"] or record["is_expert_forced"])
                winner["rule_note"] = "；".join(dict.fromkeys(filter(None, [current["rule_note"], record["rule_note"]])))
                merged[key] = winner
        return metrics.sort_records(merged.values())

    @staticmethod
    def _internal_top(metrics: FundMetrics, pool: Sequence[dict[str, Any]]) -> dict[str, Any] | None:
        """内部最高候选（Level0）复核信息；正式预警不进入该表。"""
        candidates = [r for r in pool if int(r["level"]) == 0 and not r["is_suppressed"]]
        if not candidates:
            return None
        record = metrics.sort_records(candidates)[0]
        return {"record": record, "reason": metrics.no_alert_reason(record)}

    @staticmethod
    def _public_internal(item: dict[str, Any] | None) -> dict[str, Any] | None:
        if not item:
            return None
        record = item["record"]
        window = record["windows"][record["primary_window"]]
        return {
            "id": record["id"],
            "layer": record["layer"],
            "path": record["path"],
            "primary_window_label": window["label"],
            "level_label": record["level_label"],
            "observation_abnormal_count": window["observation_abnormal_count"],
            "growth_factor": window["growth_display"],
            "rate_lift_factor": window["rate_lift_display"],
            "z_score": window["z_score"],
            "reason": item["reason"],
        }

    @staticmethod
    def _review_items(
        metrics: FundMetrics, pools: Sequence[Sequence[dict[str, Any]]]
    ) -> list[dict[str, Any]]:
        """人工复核清单：无基准 / 新增异常的 Level0 路径（方案 5.1 与 P3 复核优先级）。"""
        selected: dict[str, dict[str, Any]] = {}
        for pool in pools:
            for record in pool:
                if int(record["level"]) != 0 or record["is_suppressed"]:
                    continue
                window = record["windows"][record["primary_window"]]
                if not (window["no_baseline"] or window["is_new_anomaly"]):
                    continue
                canonical = record["canonical_path"]
                existing = selected.get(canonical)
                if existing is None or metrics.sort_records([existing, record])[0] is record:
                    selected[canonical] = record
        return metrics.sort_records(selected.values())[:50]

    def _field_dictionary(
        self, metrics: FundMetrics, single_groups: dict[str, dict[str, tuple[pd.Series, pd.Series]]]
    ) -> list[dict[str, Any]]:
        output: list[dict[str, Any]] = []
        for field in self.dimensions:
            values = single_groups.get(field, {})
            suppression = "是" if any(rule["field"] == field for rule in metrics.suppression_rules) else "否"
            forced = next(
                (rule for rule in self.config.get("expert_forced_single", []) if rule.get("field") == field), None
            )
            output.append(
                {
                    "field": field,
                    "label": metrics.field_labels.get(field, field),
                    "unique_value_count": len(values),
                    "null_replaced_rows": "",
                    "suppression": suppression,
                    "forced_single": forced.get("label", "是") if forced else "否",
                    "forced_pair": "是" if any(rule.get("field") == field for rule in self.config.get("expert_forced_pair", [])) else "否",
                    "forced_third": "是" if any(rule.get("field") == field for rule in self.config.get("expert_forced_third", [])) else "否",
                }
            )
        return output
