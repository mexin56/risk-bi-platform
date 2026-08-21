"""Server-side MaxCompute aggregation runner for the credit-attribution monitor.

Only aggregate daily slices are transferred through PyODPS Tunnel.  The source table
is never downloaded wholesale to the browser or local disk.
"""

from __future__ import annotations

import concurrent.futures
import copy
import hashlib
import math
import os
import re
from collections import defaultdict
from datetime import datetime, timezone
from typing import Any, Callable, Iterable

import numpy as np
import pandas as pd

SAFE_FIELD = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


def normalize_value(value: Any) -> str:
    if value is None:
        return "none"
    if isinstance(value, float) and math.isnan(value):
        return "none"
    text = str(value).strip()
    return text if text else "none"


def numeric(value: Any, digits: int = 4) -> int | float:
    if value is None:
        return 0
    raw = float(value)
    if math.isnan(raw):
        return 0
    if math.isinf(raw):
        raw = 999.0 if raw > 0 else -999.0
    raw = round(raw, digits)
    return int(raw) if raw.is_integer() else raw


class AttributionMetrics:
    """Pure v2.2 metric / ranking logic independent of the data transport."""

    def __init__(self, config: dict[str, Any], partition: str, daily_total: pd.Series):
        self.config = config
        self.partition = partition
        self.dimensions = list(config["dimensions"])
        self.count_field = config["count_field"]
        self.thresholds = sorted(config["thresholds"], key=lambda item: item["level"])
        self.window_config = list(config["windows"])
        self.level_labels = {0: "Level0 无预警", **{item["level"]: item["label"] for item in self.thresholds}}
        self.level_colors = {0: "slate", 1: "yellow", 2: "orange", 3: "red"}
        self.daily_total = daily_total.sort_index().astype(float)
        self.days = list(self.daily_total.index)
        if len(self.days) < 2:
            raise RuntimeError("可用统计日期不足 2 天，无法建立观察期与基准期。")
        self.window_specs = self._build_window_specs()
        self.suppression_rules = [
            {**rule, "value": normalize_value(rule["value"])} for rule in config.get("suppression_rules", [])
        ]

    def _build_window_specs(self) -> list[dict[str, Any]]:
        specs: list[dict[str, Any]] = []
        for item in self.window_config:
            observation_days = int(item["observation_days"])
            observation = self.days[-observation_days:]
            baseline = self.days[:-observation_days]
            specs.append(
                {
                    **item,
                    "observation": observation,
                    "baseline": baseline,
                    "baseline_days": len(baseline),
                    "observation_start": observation[0].isoformat(),
                    "observation_end": observation[-1].isoformat(),
                    "baseline_start": baseline[0].isoformat() if baseline else None,
                    "baseline_end": baseline[-1].isoformat() if baseline else None,
                }
            )
        return specs

    @staticmethod
    def _ratio(numerator: float, denominator: float) -> float:
        # 与 Excel 报告口径一致: 无基准(分母<=0)时按 0 参与等级判定与 Top-K 排序(而非 999 假高)
        if denominator <= 0:
            return 0.0
        return numerator / denominator

    def _level_for_metrics(self, observation_count: float, growth_factor: float, structure_lift_factor: float, z_score: float) -> int:
        for threshold in reversed(self.thresholds):
            if (
                observation_count >= threshold["min_observation_count"]
                and growth_factor >= threshold["min_growth_factor"]
                and structure_lift_factor >= threshold["min_structure_lift_factor"]
                and z_score >= threshold["min_z_score"]
            ):
                return int(threshold["level"])
        return 0

    def _window_metrics(self, counts: pd.Series, spec: dict[str, Any]) -> dict[str, Any]:
        counts = counts.reindex(self.days, fill_value=0.0).astype(float)
        baseline_dates = spec["baseline"]
        observation_dates = spec["observation"]
        baseline_count = float(counts.reindex(baseline_dates, fill_value=0.0).sum())
        observation_count = float(counts.reindex(observation_dates, fill_value=0.0).sum())
        baseline_total = float(self.daily_total.reindex(baseline_dates, fill_value=0.0).sum())
        observation_total = float(self.daily_total.reindex(observation_dates, fill_value=0.0).sum())
        baseline_daily = baseline_count / max(len(baseline_dates), 1)
        observation_daily = observation_count / max(len(observation_dates), 1)
        baseline_share = self._ratio(baseline_count, baseline_total)
        observation_share = self._ratio(observation_count, observation_total)
        growth_factor = self._ratio(observation_daily, baseline_daily)
        structure_lift_factor = self._ratio(observation_share, baseline_share)
        expected_count = observation_total * baseline_share if baseline_total > 0 else 0.0
        excess_count = observation_count - expected_count
        z_score = self._ratio(excess_count, math.sqrt(expected_count)) if expected_count > 0 else 0.0
        level = self._level_for_metrics(observation_count, growth_factor, structure_lift_factor, z_score)
        return {
            "key": spec["key"],
            "label": spec["label"],
            "color": spec["color"],
            "purpose": spec["purpose"],
            "baseline_start": spec["baseline_start"],
            "baseline_end": spec["baseline_end"],
            "observation_start": spec["observation_start"],
            "observation_end": spec["observation_end"],
            "baseline_days": len(baseline_dates),
            "observation_days": len(observation_dates),
            "baseline_count": numeric(baseline_count),
            "observation_count": numeric(observation_count),
            "baseline_daily": numeric(baseline_daily),
            "observation_daily": numeric(observation_daily),
            "baseline_share": numeric(baseline_share, 8),
            "observation_share": numeric(observation_share, 8),
            "growth_factor": numeric(growth_factor),
            "structure_lift_factor": numeric(structure_lift_factor),
            "structure_change": numeric(observation_share - baseline_share, 8),
            "expected_count": numeric(expected_count),
            "excess_count": numeric(excess_count),
            "z_score": numeric(z_score),
            "level": level,
            "level_label": self.level_labels[level],
            "severity": self.level_colors[level],
        }

    @staticmethod
    def canonical_path(conditions: Iterable[tuple[str, str]]) -> str:
        return " / ".join(sorted(f"{field}={value}" for field, value in conditions))

    @staticmethod
    def display_path(conditions: Iterable[tuple[str, str]]) -> str:
        # 与最新版 Excel 报告口径一致: 路径按下钻条件顺序展示(register_software 在前)
        return " / ".join(f"{field}={value}" for field, value in conditions)

    def suppression_reasons(self, conditions: Iterable[tuple[str, str]]) -> list[str]:
        lookup = dict(conditions)
        return [rule["reason"] for rule in self.suppression_rules if lookup.get(rule["field"]) == rule["value"]]

    def record(
        self,
        conditions: list[tuple[str, str]],
        counts: pd.Series,
        *,
        source: str,
        forced: bool = False,
        rule_note: str = "",
        drilldown_rule: str = "",
        enters_next_level: bool = False,
    ) -> dict[str, Any]:
        metrics = [self._window_metrics(counts, spec) for spec in self.window_specs]
        # 主窗口选择: 与 Excel 报告口径一致 —— 排除“无基准”(基准日均=0)的窗口后再按
        # (等级, min(增长,结构提升), z) 竞争; 全部无基准时退化为全窗口竞争
        eligible_metrics = [item for item in metrics if float(item["baseline_daily"]) > 0]
        primary = max(
            eligible_metrics or metrics,
            key=lambda item: (
                item["level"],
                min(float(item["growth_factor"]), float(item["structure_lift_factor"])),
                float(item["z_score"]),
                float(item["observation_count"]),
            ),
        )
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
        suppression_reasons = self.suppression_reasons(conditions)
        canonical = self.canonical_path(conditions)
        layer = {1: "单维", 2: "二级", 3: "三级"}.get(len(conditions), f"{len(conditions)}维")
        return {
            "id": hashlib.sha1(canonical.encode("utf-8")).hexdigest()[:12],
            "source": source,
            "layer": layer,
            "path": self.display_path(conditions),
            "canonical_path": canonical,
            "conditions": [
                {"field": field, "value": value, "label": self.config["field_labels"].get(field, field)}
                for field, value in conditions
            ],
            "level": level,
            "level_label": self.level_labels[level],
            "severity": self.level_colors[level],
            "anomaly_type": anomaly_type,
            "primary_window": primary["key"],
            "primary_window_label": primary["label"],
            "hit_windows": hits,
            "hit_window_count": len(hits),
            "observation_count": primary["observation_count"],
            "growth_factor": primary["growth_factor"],
            "structure_lift_factor": primary["structure_lift_factor"],
            "z_score": primary["z_score"],
            "excess_count": primary["excess_count"],
            "relative_strength": numeric(min(float(primary["growth_factor"]), float(primary["structure_lift_factor"]))),
            "is_expert_forced": forced,
            "rule_note": rule_note,
            "is_suppressed": bool(suppression_reasons),
            "suppression_reasons": suppression_reasons,
            "enters_next_level": enters_next_level,
            "drilldown_rule": drilldown_rule,
            "windows": {item["key"]: item for item in metrics},
        }

    @staticmethod
    def sort_records(records: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
        return sorted(
            records,
            key=lambda item: (
                -int(item["level"]),
                -int(item["hit_window_count"]),
                -float(item["relative_strength"]),
                -float(item["z_score"]),
                -float(item["observation_count"]),
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
    def mark_downstream(records: Iterable[dict[str, Any]], message: str) -> list[dict[str, Any]]:
        output: list[dict[str, Any]] = []
        for record in records:
            updated = copy.deepcopy(record)
            updated["enters_next_level"] = True
            updated["drilldown_rule"] = message
            output.append(updated)
        return output


class WarehouseAttributionRunner:
    """Runs all attribution aggregation in MaxCompute and transfers only result slices."""

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
        self.count_field = config["count_field"]
        self.workers = max(1, min(int(os.getenv("ATTRIBUTION_QUERY_WORKERS", "8")), 8))
        self._window_filter = ""  # 观察窗口裁剪子句, 由 _resolve_window() 初始化

    def _resolve_window(self) -> None:
        """定位最近日期并生成观察窗口裁剪子句, 避免每条SQL全分区扫描.

        归因分析只需要 lookback_days 窗口的数据; 实测同一聚合SQL加窗口裁剪后
        耗时从 72.5s 降至 7.4s (约 10x). offset>0 表示将窗口整体向前平移
        offset 天(回看历史区间). 首次调用后幂等, 供所有聚合查询复用.
        """
        if self._window_filter:
            return
        rows = self.query_rows(
            f"""
            SELECT MAX(TO_CHAR({self.date_field}, 'yyyy-MM-dd')) AS max_day
            FROM {self.table}
            WHERE pt = '{self._escape(self.partition)}'
            """
        )
        max_day = rows[0]["max_day"] if rows and rows[0].get("max_day") else None
        lookback = int(self.config.get("lookback_days", 15))
        if max_day is None:
            self._window_filter = ""
            return
        # 表内数据范围(供前端观察区间选项与无数据提示)
        self._table_date_max = max_day
        min_rows = self.query_rows(
            f"""
            SELECT MIN(TO_CHAR({self.date_field}, 'yyyy-MM-dd')) AS min_day
            FROM {self.table}
            WHERE pt = '{self._escape(self.partition)}'
            """
        )
        self._table_date_min = min_rows[0]["min_day"] if min_rows and min_rows[0].get("min_day") else max_day
        # 窗口终点 = 最近日期 - offset; 起点 = 终点 - (lookback + 2 天余量)
        end = pd.Timestamp(max_day) - pd.Timedelta(days=self.offset)
        start = end - pd.Timedelta(days=lookback + 2)
        # 注意: create_date 为 datetime, <= TO_DATE(end) 只含当天 00:00:00 会把最后一天截掉,
        # 必须用「小于次日」才能包含 end 当天全天
        end_exclusive = end + pd.Timedelta(days=1)
        self._window_filter = (
            f"AND {self.date_field} >= TO_DATE('{start:%Y-%m-%d}', 'yyyy-mm-dd') "
            f"AND {self.date_field} < TO_DATE('{end_exclusive:%Y-%m-%d}', 'yyyy-mm-dd') "
        )

    @staticmethod
    def _escape(value: str) -> str:
        return value.replace("'", "''")

    def _field(self, field: str) -> str:
        if field not in self.dimensions or not SAFE_FIELD.fullmatch(field):
            raise RuntimeError(f"不支持的归因字段：{field}")
        return field

    def _value_expr(self, field: str) -> str:
        field = self._field(field)
        return f"CASE WHEN {field} IS NULL OR TRIM(CAST({field} AS STRING)) = '' THEN 'none' ELSE TRIM(CAST({field} AS STRING)) END"

    def _condition_sql(self, field: str, value: str) -> str:
        expression = self._value_expr(field)
        return f"{expression} = '{self._escape(normalize_value(value))}'"

    @staticmethod
    def _parse_day(value: Any):
        return pd.Timestamp(str(value)).date()

    def _daily_info(self) -> tuple[pd.Series, pd.DataFrame]:
        self._resolve_window()
        approval_fields = [field for field in self.config.get("approval_fields", []) if SAFE_FIELD.fullmatch(field)]
        approval_sql = ", ".join(f"SUM({field}) AS {field}" for field in approval_fields)
        sql = f"""
            SELECT TO_CHAR({self.date_field}, 'yyyy-MM-dd') AS day,
                   SUM({self.count_field}) AS application_count,
                   COUNT(1) AS aggregate_row_count
                   {', ' + approval_sql if approval_sql else ''}
            FROM {self.table}
            WHERE pt = '{self._escape(self.partition)}'
              {self._window_filter}
            GROUP BY TO_CHAR({self.date_field}, 'yyyy-MM-dd')
            ORDER BY day
        """
        rows = self.query_rows(sql)
        if not rows:
            table_min = getattr(self, "_table_date_min", "?")
            table_max = getattr(self, "_table_date_max", "?")
            raise RuntimeError(
                f"该观察区间无可用数据(表数据范围 {table_min} ~ {table_max}, 当前窗口已超出范围, 请选择更靠前的区间)"
            )
        daily = pd.DataFrame(rows)
        daily["day"] = pd.to_datetime(daily["day"]).dt.date
        daily["application_count"] = pd.to_numeric(daily["application_count"], errors="coerce").fillna(0.0)
        daily = daily.sort_values("day")
        lookback = int(self.config.get("lookback_days", 15))
        daily = daily.tail(lookback).copy()
        return daily.set_index("day")["application_count"], daily

    @staticmethod
    def _series_map(rows: list[dict[str, Any]], value_key: str, count_key: str = "cnt") -> dict[str, pd.Series]:
        buckets: dict[str, dict[Any, float]] = defaultdict(dict)
        for row in rows:
            value = normalize_value(row.get(value_key))
            day = pd.Timestamp(str(row["day"])).date()
            amount = float(row.get(count_key) or 0)
            buckets[value][day] = buckets[value].get(day, 0.0) + amount
        return {value: pd.Series(day_counts, dtype=float) for value, day_counts in buckets.items()}

    def _grouped_field(self, field: str) -> dict[str, pd.Series]:
        self._resolve_window()
        expression = self._value_expr(field)
        sql = f"""
            SELECT {expression} AS value,
                   TO_CHAR({self.date_field}, 'yyyy-MM-dd') AS day,
                   SUM({self.count_field}) AS cnt
            FROM {self.table}
            WHERE pt = '{self._escape(self.partition)}'
              {self._window_filter}
            GROUP BY {expression}, TO_CHAR({self.date_field}, 'yyyy-MM-dd')
        """
        return self._series_map(self.query_rows(sql), "value")

    def _parallel_fields(self, func: Callable[[str], Any], fields: Iterable[str]) -> dict[str, Any]:
        field_list = list(fields)
        output: dict[str, Any] = {}
        with concurrent.futures.ThreadPoolExecutor(max_workers=self.workers) as executor:
            futures = {executor.submit(func, field): field for field in field_list}
            for future in concurrent.futures.as_completed(futures):
                field = futures[future]
                output[field] = future.result()
        return output

    def _grouped_for_condition_sets(
        self,
        condition_sets: list[dict[str, Any]],
        extension_field: str,
    ) -> dict[str, dict[str, pd.Series]]:
        """For each parent path return extension-value -> daily cnt.

        Conditional aggregations let one MaxCompute scan serve every selected parent
        path for the requested extension dimension.
        """

        extension_expr = self._value_expr(extension_field)
        aliases: list[str] = []
        expressions: list[str] = []
        where_conditions: list[str] = []
        for index, item in enumerate(condition_sets):
            conditions = [(part["field"], part["value"]) for part in item["conditions"]]
            condition = " AND ".join(self._condition_sql(field, value) for field, value in conditions)
            alias = f"seed_{index}"
            aliases.append(alias)
            expressions.append(f"SUM(CASE WHEN {condition} THEN {self.count_field} ELSE 0 END) AS {alias}")
            where_conditions.append(f"({condition})")
        if not expressions:
            return {}
        self._resolve_window()
        sql = f"""
            SELECT {extension_expr} AS value,
                   TO_CHAR({self.date_field}, 'yyyy-MM-dd') AS day,
                   {', '.join(expressions)}
            FROM {self.table}
            WHERE pt = '{self._escape(self.partition)}'
              {self._window_filter}
              AND ({' OR '.join(where_conditions)})
            GROUP BY {extension_expr}, TO_CHAR({self.date_field}, 'yyyy-MM-dd')
        """
        rows = self.query_rows(sql)
        buckets: dict[str, dict[str, dict[Any, float]]] = {
            item["key"]: defaultdict(dict) for item in condition_sets
        }
        for row in rows:
            value = normalize_value(row.get("value"))
            day = self._parse_day(row["day"])
            for index, item in enumerate(condition_sets):
                amount = float(row.get(aliases[index]) or 0)
                if amount:
                    value_map = buckets[item["key"]][value]
                    value_map[day] = value_map.get(day, 0.0) + amount
        return {
            parent_key: {value: pd.Series(day_counts, dtype=float) for value, day_counts in values.items()}
            for parent_key, values in buckets.items()
        }

    def _exact_daily(self, conditions: list[tuple[str, str]]) -> pd.Series:
        self._resolve_window()
        predicates = " AND ".join(self._condition_sql(field, value) for field, value in conditions)
        sql = f"""
            SELECT TO_CHAR({self.date_field}, 'yyyy-MM-dd') AS day,
                   SUM({self.count_field}) AS cnt
            FROM {self.table}
            WHERE pt = '{self._escape(self.partition)}' AND {predicates}
              {self._window_filter}
            GROUP BY TO_CHAR({self.date_field}, 'yyyy-MM-dd')
        """
        rows = self.query_rows(sql)
        return pd.Series({self._parse_day(row["day"]): float(row.get("cnt") or 0) for row in rows}, dtype=float)

    def path_trend(self, record: dict[str, Any], daily_context: list[dict[str, Any]]) -> dict[str, Any]:
        """Return the selected alert path's daily series for the current 15-day context.

        `record` comes from the server-side dashboard cache, rather than browser-supplied
        field values, so only configured dimensions can become SQL predicates.
        """
        if not daily_context:
            raise RuntimeError("当前归因任务缺少近 15 天日期上下文。")

        path_daily = self._exact_daily(self._conditions(record))
        daily: list[dict[str, Any]] = []
        for context in daily_context:
            day = self._parse_day(context["date"])
            application_count = float(path_daily.get(day, 0.0))
            total_application_count = float(context.get("application_count") or 0.0)
            daily.append(
                {
                    "date": day.isoformat(),
                    "application_count": numeric(application_count),
                    "total_application_count": numeric(total_application_count),
                    "application_share_pct": numeric(
                        application_count / total_application_count * 100 if total_application_count else 0.0
                    ),
                }
            )

        latest = daily[-1]
        previous = daily[-2] if len(daily) > 1 else None
        peak = max(daily, key=lambda item: float(item["application_count"]))
        primary_window = record["windows"].get(record["primary_window"], {})
        return {
            "record_id": record["id"],
            "path": record["path"],
            "source": record["source"],
            "level": record["level"],
            "level_label": record["level_label"],
            "severity": record["severity"],
            "primary_window": {
                "key": record["primary_window"],
                "label": primary_window.get("label", record["primary_window_label"]),
                "observation_start": primary_window.get("observation_start"),
                "observation_end": primary_window.get("observation_end"),
                "baseline_daily": primary_window.get("baseline_daily", 0),
            },
            "daily": daily,
            "summary": {
                "period_days": len(daily),
                "period_application_count": numeric(sum(float(item["application_count"]) for item in daily)),
                "latest_application_count": latest["application_count"],
                "previous_application_count": previous["application_count"] if previous else None,
                "latest_day_change_pct": numeric(
                    (float(latest["application_count"]) / float(previous["application_count"]) - 1) * 100
                    if previous and float(previous["application_count"]) > 0
                    else 0.0
                ),
                "peak_application_count": peak["application_count"],
                "peak_date": peak["date"],
                "latest_application_share_pct": latest["application_share_pct"],
            },
        }

    @staticmethod
    def _conditions(record: dict[str, Any]) -> list[tuple[str, str]]:
        return [(part["field"], part["value"]) for part in record["conditions"]]

    def _evaluate_values(
        self,
        metrics: AttributionMetrics,
        base_conditions: list[tuple[str, str]],
        field: str,
        daily_by_value: dict[str, pd.Series],
        *,
        source: str,
        forced: bool = False,
        rule_note: str = "",
        drilldown_rule: str = "",
        dimension_ordered: bool = False,
    ) -> list[dict[str, Any]]:
        def build(value: str) -> list[tuple[str, str]]:
            conditions = [*base_conditions, (field, value)]
            if dimension_ordered:
                # 与 Excel 报告口径一致: Top-K 路径按维度列表顺序排列字段
                order = {name: index for index, name in enumerate(self.dimensions)}
                conditions = sorted(conditions, key=lambda item: order.get(item[0], 99))
            return conditions

        return [
            metrics.record(
                build(value),
                daily,
                source=source,
                forced=forced,
                rule_note=rule_note,
                drilldown_rule=drilldown_rule,
            )
            for value, daily in daily_by_value.items()
        ]

    def _run_top_k(
        self,
        metrics: AttributionMetrics,
        single_groups: dict[str, dict[str, pd.Series]],
    ) -> tuple[dict[str, Any], list[dict[str, Any]], list[dict[str, Any]]]:
        all_single: list[dict[str, Any]] = []
        for field in self.dimensions:
            all_single.extend(self._evaluate_values(metrics, [], field, single_groups.get(field, {}), source="Top-K", dimension_ordered=True))
        all_single = metrics.dedupe(all_single)
        eligible_single = [
            record
            for record in all_single
            if not record["is_suppressed"]
            and (record["level"] > 0 or record["observation_count"] >= 30)  # v2.4: Level0 候选门槛=主排序窗口观察量≥30
        ]
        suppressed: list[dict[str, Any]] = [record for record in all_single if record["is_suppressed"] and record["level"] > 0]
        single_seed = metrics.mark_downstream(
            metrics.sort_records(eligible_single)[: int(self.config["top_k"]["single_limit"])],
            "单维 Top10 进入二级下钻",
        )

        single_condition_sets = [{"key": record["canonical_path"], "conditions": record["conditions"]} for record in single_seed]
        pair_groups = self._parallel_fields(
            lambda field: self._grouped_for_condition_sets(single_condition_sets, field), self.dimensions
        )
        all_pair: list[dict[str, Any]] = []
        for record in single_seed:
            base_conditions = self._conditions(record)
            occupied = {field for field, _ in base_conditions}
            for field in self.dimensions:
                if field in occupied:
                    continue
                value_map = pair_groups.get(field, {}).get(record["canonical_path"], {})
                all_pair.extend(self._evaluate_values(metrics, base_conditions, field, value_map, source="Top-K", dimension_ordered=True))
        all_pair = metrics.dedupe(all_pair)
        eligible_pair = [
            record
            for record in all_pair
            if not record["is_suppressed"]
            and (record["level"] > 0 or record["observation_count"] >= 30)  # v2.4: Level0 候选门槛
        ]
        suppressed.extend(record for record in all_pair if record["is_suppressed"] and record["level"] > 0)
        pair_seed = metrics.mark_downstream(
            metrics.sort_records(eligible_pair)[: int(self.config["top_k"]["pair_limit"])],
            "二级 Top5 进入三级下钻",
        )

        pair_condition_sets = [{"key": record["canonical_path"], "conditions": record["conditions"]} for record in pair_seed]
        third_groups = self._parallel_fields(
            lambda field: self._grouped_for_condition_sets(pair_condition_sets, field), self.dimensions
        )
        all_third: list[dict[str, Any]] = []
        for record in pair_seed:
            base_conditions = self._conditions(record)
            occupied = {field for field, _ in base_conditions}
            for field in self.dimensions:
                if field in occupied:
                    continue
                value_map = third_groups.get(field, {}).get(record["canonical_path"], {})
                all_third.extend(self._evaluate_values(metrics, base_conditions, field, value_map, source="Top-K", dimension_ordered=True))
        all_third = metrics.dedupe(all_third)
        eligible_third = [record for record in all_third if not record["is_suppressed"]]
        suppressed.extend(record for record in all_third if record["is_suppressed"] and record["level"] > 0)

        alerts = metrics.dedupe(
            [
                *[record for record in eligible_single if record["level"] > 0],
                *[record for record in eligible_pair if record["level"] > 0],
                *[record for record in eligible_third if record["level"] > 0],
            ]
        )
        return (
            {
                "single_downstream": single_seed,
                "pair_downstream": pair_seed,
                "third_alerts": [record for record in metrics.sort_records(eligible_third) if record["level"] > 0],
                "counts": {
                    "single_scanned": len(all_single),
                    "single_pool": len(eligible_single),  # v2.4 候选池(Level0观察量≥30后)
                    "pair_scanned": len(all_pair),
                    "pair_pool": len(eligible_pair),
                    "third_scanned": len(all_third),
                    "single_alerts": sum(1 for record in eligible_single if record["level"] > 0),
                    "pair_alerts": sum(1 for record in eligible_pair if record["level"] > 0),
                    "third_alerts": sum(1 for record in eligible_third if record["level"] > 0),
                },
            },
            alerts,
            metrics.dedupe(suppressed),
        )

    def _run_expert(
        self,
        metrics: AttributionMetrics,
        single_groups: dict[str, dict[str, pd.Series]],
    ) -> tuple[dict[str, Any], list[dict[str, Any]], list[dict[str, Any]]]:
        expert_path = self.config.get("expert_path", [])
        if len(expert_path) < 3:
            return ({"single": None, "pair": None, "third_alerts": [], "third_calculated": [], "counts": {}}, [], [])
        first, second, third = expert_path[:3]
        first_conditions = [(first["field"], normalize_value(first["value"]))]
        second_conditions = [*first_conditions, (second["field"], normalize_value(second["value"]))]
        single_daily = single_groups.get(first["field"], {}).get(first_conditions[0][1], pd.Series(dtype=float))
        single = metrics.record(
            first_conditions,
            single_daily,
            source="专家规则",
            forced=True,
            rule_note=first["label"],
            drilldown_rule="强制单维进入专家二级下钻",
            enters_next_level=True,
        )
        pair = metrics.record(
            second_conditions,
            self._exact_daily(second_conditions),
            source="专家规则",
            forced=True,
            rule_note=second["label"],
            drilldown_rule="强制双维进入专家三级下钻",
            enters_next_level=True,
        )
        condition_set = [{"key": "expert", "conditions": [{"field": f, "value": v} for f, v in second_conditions]}]
        third_group = self._grouped_for_condition_sets(condition_set, third["field"]).get("expert", {})
        third_calculated = metrics.dedupe(
            self._evaluate_values(
                metrics,
                second_conditions,
                third["field"],
                third_group,
                source="专家规则",
                forced=True,
                rule_note=third["label"],
                drilldown_rule="专家三级终止层",
            )
        )
        all_records = [single, pair, *third_calculated]
        suppressed = [record for record in all_records if record["is_suppressed"] and record["level"] > 0]
        eligible = [record for record in all_records if not record["is_suppressed"]]
        alerts = metrics.sort_records([record for record in eligible if record["level"] > 0])
        return (
            {
                "single": single,
                "pair": pair,
                "third_alerts": [record for record in third_calculated if not record["is_suppressed"] and record["level"] > 0],
                "third_calculated": [record for record in third_calculated if not record["is_suppressed"]],
                "counts": {"third_calculated": len(third_calculated), "alerts": len(alerts)},
            },
            alerts,
            metrics.dedupe(suppressed),
        )

    @staticmethod
    def _merge(metrics: AttributionMetrics, top_k_alerts: list[dict[str, Any]], expert_alerts: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """v2.4: 合并去重——同路径(字段=取值规范化)只保留一条, 来源合并为"Top-K + 专家规则".

        最终等级取该路径多窗口最高等级; 来源/专家强制标记/触发说明合并保留.
        """
        merged: dict[str, dict[str, Any]] = {}
        for record in [*top_k_alerts, *expert_alerts]:
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

    def run(self) -> dict[str, Any]:
        self._resolve_window()
        daily_total, daily_info = self._daily_info()
        metrics = AttributionMetrics(self.config, self.partition, daily_total)
        single_groups = self._parallel_fields(self._grouped_field, self.dimensions)
        top_k, top_k_alerts, top_k_suppressed = self._run_top_k(metrics, single_groups)
        expert, expert_alerts, expert_suppressed = self._run_expert(metrics, single_groups)
        merged_alerts = self._merge(metrics, top_k_alerts, expert_alerts)
        suppressed_alerts = metrics.dedupe([*top_k_suppressed, *expert_suppressed])
        highlight = merged_alerts[0] if merged_alerts else (expert["single"] or None)

        # Data for the trend chart; path-only aggregation keeps payload compact.
        expert_path = self.config.get("expert_path", [])
        expert_daily = pd.Series(dtype=float)
        if expert_path:
            first = expert_path[0]
            expert_daily = single_groups.get(first["field"], {}).get(normalize_value(first["value"]), pd.Series(dtype=float))
        focus_daily = self._exact_daily([(part["field"], part["value"]) for part in highlight["conditions"]]) if highlight else pd.Series(dtype=float)
        day_index = list(metrics.days)
        daily_info_indexed = daily_info.set_index("day")
        daily_trend = [
            {
                "date": day.isoformat(),
                "application_count": numeric(daily_total.get(day, 0.0)),
                "approval_count": numeric(daily_info_indexed.get("approval_cnt", pd.Series(dtype=float)).get(day, 0.0)),
                "expert_seed_count": numeric(expert_daily.get(day, 0.0)),
                "focus_path_count": numeric(focus_daily.get(day, 0.0)),
            }
            for day in day_index
        ]
        latest_day, previous_day = day_index[-1], day_index[-2]
        latest_total, previous_total = float(daily_total.get(latest_day, 0.0)), float(daily_total.get(previous_day, 0.0))
        current_approval = float(daily_info_indexed.get("approval_cnt", pd.Series(dtype=float)).get(latest_day, 0.0))

        windows = [
            {
                "key": spec["key"], "label": spec["label"], "purpose": spec["purpose"], "color": spec["color"],
                "observation_days": spec["observation_days"], "baseline_days": spec["baseline_days"],
                "observation_start": spec["observation_start"], "observation_end": spec["observation_end"],
                "baseline_start": spec["baseline_start"], "baseline_end": spec["baseline_end"],
            }
            for spec in metrics.window_specs
        ]
        return {
            "meta": {
                "source": "MaxCompute", "table": self.table, "partition": self.partition, "version": self.config["version"],
                "date_start": day_index[0].isoformat(), "date_end": day_index[-1].isoformat(), "date_count": len(day_index),
                "aggregate_row_count": int(pd.to_numeric(daily_info["aggregate_row_count"], errors="coerce").fillna(0).sum()),
                "dimension_count": len(self.dimensions), "generated_at": datetime.now(timezone.utc).isoformat(),
                "table_date_min": getattr(self, "_table_date_min", None),
                "table_date_max": getattr(self, "_table_date_max", None),
                "note": "cnt 为聚合统计权重；超额申请量仅用于业务影响说明，不参与预警等级或 Top-K 主排序。",
            },
            "summary": {
                "total_application_count": numeric(float(daily_total.sum())), "latest_application_count": numeric(latest_total),
                "previous_application_count": numeric(previous_total),
                "latest_day_change_pct": numeric((latest_total / previous_total - 1) * 100 if previous_total else 0.0),
                "latest_approval_rate": numeric(current_approval / latest_total * 100 if latest_total else 0.0),
                "approval_count": numeric(float(pd.to_numeric(daily_info.get("approval_cnt", pd.Series(dtype=float)), errors="coerce").fillna(0).sum())),
                "approval_jy0_count": numeric(float(pd.to_numeric(daily_info.get("approval_jy0_cnt", pd.Series(dtype=float)), errors="coerce").fillna(0).sum())),
                "merged_alert_count": len(merged_alerts), "level3_count": sum(1 for row in merged_alerts if row["level"] == 3),
                "level2_count": sum(1 for row in merged_alerts if row["level"] == 2),
                "level1_count": sum(1 for row in merged_alerts if row["level"] == 1),
                "expert_alert_count": len(expert_alerts), "suppressed_alert_count": len(suppressed_alerts),
                "highlight_path": highlight["path"] if highlight else None,
            },
            "daily_trend": daily_trend,
            "highlight": highlight,
            "merged_alerts": merged_alerts[:250], "merged_alert_total": len(merged_alerts),
            "top_k": top_k, "expert": expert,
            "suppressed_alerts": suppressed_alerts[:250], "suppressed_alert_total": len(suppressed_alerts),
            "rules": {
                "thresholds": metrics.thresholds, "windows": windows, "suppression_rules": metrics.suppression_rules,
                "expert_path": self.config.get("expert_path", []), "field_labels": self.config["field_labels"],
            },
        }
