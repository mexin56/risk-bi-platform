"""业务环节模型效果监控的口径转换与展示数据组装。"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from datetime import datetime, timedelta, timezone
from typing import Any


MODEL_SCORES: tuple[tuple[str, str], ...] = (
    ("ng_cashjq_utilization_high_v1_score", "额度使用率高V1"),
    ("ng_cashjq_loancnt_1_4_v1_score", "借款次数1-4V1"),
    ("ng_cashjq_loancnt_1plus_v1_score", "借款次数1+V1"),
    ("ng_mcr0001_score", "MCR0001"),
    ("ng_mcr0002_score", "MCR0002"),
    ("ng_mcr0003_score", "MCR0003"),
    ("ng_mcr0004_01_score", "MCR0004"),
    ("ng_mcr0005_01_score", "MCR0005"),
    ("lgb_jy_model_level1_20250211_score", "LGB授信L1"),
    ("lgb_jy_model_level2_20250211_score", "LGB授信L2"),
    ("lgb_jy_model_level3_20250211_score", "LGB授信L3"),
    ("lgb_loandays_14_model_20250312_score", "LGB贷天数14"),
    ("older_op_v1_score", "OP V1"),
    ("op_v2_score", "OP V2"),
    ("ng_long_mob_defq_jy_score_v1", "长周期DEFQ V1"),
    ("ng_long_mob_defq_jy_score_v2", "长周期DEFQ V2"),
    ("ng_short_mob_defq_jy_score_v1", "短周期DEFQ V1"),
    ("pal_jy_pd15_ft293_v5_score", "PAL PD15 V5"),
    ("jy_lgb_model_high_rate_pd15_score", "高费率PD15"),
    ("jy_lgb_model_low_rate_pd15_score", "低费率PD15"),
    ("jy_lgb_model_low_rate_pd3_score", "低费率PD3"),
    ("ng_cashloan_txn_bcard_v1_fpd7_score", "B卡FPD7"),
    ("ng_cashloan_txn_bcard_v1_mob3_score", "B卡MOB3"),
    ("jy_newer_v1_score", "新客V1"),
)

CASH_SER_CALL_NODE_OPTIONS: tuple[str, ...] = (
    "INSTANT_LOAN",
    "INSTALLMENT_LOAN",
    "PALMPAY_LOAN",
)

TARGET_FIELDS: dict[str, tuple[str, str]] = {
    "fpd1": ("fpd1_base", "fpd1_bad"),
    "fpd7": ("fpd7_base", "fpd7_bad"),
    "fpd10": ("fpd10_base", "fpd10_bad"),
    "fpd15": ("fpd15_base", "fpd15_bad"),
    "fpd30": ("fpd30_base", "fpd30_bad"),
    "term3": ("term3_base", "term3_bad"),
}


def _number(value: Any, default: float = 0.0) -> float:
    if value is None or value == "":
        return default
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _count(value: Any) -> int:
    return int(round(_number(value)))


def safe_ratio(numerator: Any, denominator: Any) -> float | None:
    denominator_value = _number(denominator)
    if denominator_value <= 0:
        return None
    return _number(numerator) / denominator_value


def _metric(
    *,
    key: str,
    stage: str,
    label: str,
    numerator: Any,
    denominator: Any,
    observation: str,
) -> dict[str, Any]:
    return {
        "key": key,
        "stage": stage,
        "label": label,
        "numerator": _count(numerator),
        "denominator": _count(denominator),
        "rate": safe_ratio(numerator, denominator),
        "observation": observation,
    }


def build_stage_metrics(overview: Mapping[str, Any]) -> list[dict[str, Any]]:
    """把不同分母的阶段结果拆成可审计的指标卡，避免伪造单一漏斗。"""
    return [
        _metric(
            key="approval_pass_rate",
            stage="申请/授信",
            label="审批通过率",
            numerator=overview.get("approval_pass_cnt"),
            denominator=overview.get("approval_labeled_cnt"),
            observation="审批结果非空样本",
        ),
        _metric(
            key="loan_success_rate",
            stage="放款",
            label="放款成功率",
            numerator=overview.get("loan_success_cnt"),
            denominator=overview.get("loan_labeled_cnt"),
            observation="放款成功字段非空样本",
        ),
        _metric(
            key="fpd7_rate",
            stage="贷后",
            label="FPD7坏账率",
            numerator=overview.get("fpd7_bad"),
            denominator=overview.get("fpd7_base"),
            observation="FPD7成熟观察样本",
        ),
        _metric(
            key="fpd30_rate",
            stage="贷后",
            label="FPD30坏账率",
            numerator=overview.get("fpd30_bad"),
            denominator=overview.get("fpd30_base"),
            observation="FPD30成熟观察样本",
        ),
        _metric(
            key="term3_rate",
            stage="贷后",
            label="TERM3坏账率",
            numerator=overview.get("term3_bad"),
            denominator=overview.get("term3_base"),
            observation="TERM3成熟观察样本",
        ),
    ]


def _performance_metrics(row: Mapping[str, Any]) -> dict[str, Any]:
    fpd7_base = _count(row.get("fpd7_base"))
    fpd30_base = _count(row.get("fpd30_base"))
    return {
        "applications": _count(row.get("applications")),
        "approved": _count(row.get("approved")),
        "loan_success": _count(row.get("loan_success")),
        "fpd7_base": fpd7_base,
        "fpd7_bad": _count(row.get("fpd7_bad")),
        "fpd7_rate": safe_ratio(row.get("fpd7_bad"), fpd7_base),
        "fpd30_base": fpd30_base,
        "fpd30_bad": _count(row.get("fpd30_bad")),
        "fpd30_rate": safe_ratio(row.get("fpd30_bad"), fpd30_base),
        "approval_rate": safe_ratio(row.get("approved"), row.get("applications")),
        "loan_success_rate": safe_ratio(row.get("loan_success"), row.get("applications")),
    }


def build_business_type_metrics(rows: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    for row in rows:
        item = {"business_type": str(row.get("business_type") or "未知")}
        item.update(_performance_metrics(row))
        result.append(item)
    return sorted(result, key=lambda item: item["applications"], reverse=True)


def build_daily_trend(rows: Sequence[Mapping[str, Any]], maturity_ratio: float = 0.5) -> list[dict[str, Any]]:
    """按 event_date 输出趋势，并把成熟观察不足的坏账率置空。"""
    result: list[dict[str, Any]] = []
    for row in rows:
        item = {"day": str(row.get("day") or "")}
        item.update(_performance_metrics(row))
        loan_success = item["loan_success"]
        fpd7_ratio = safe_ratio(item["fpd7_base"], loan_success)
        fpd30_ratio = safe_ratio(item["fpd30_base"], loan_success)
        item["fpd7_observation_ratio"] = fpd7_ratio
        item["fpd30_observation_ratio"] = fpd30_ratio
        item["fpd7_rate_raw"] = item["fpd7_rate"]
        item["fpd30_rate_raw"] = item["fpd30_rate"]
        item["maturity_warning"] = bool(
            (fpd7_ratio is not None and fpd7_ratio < maturity_ratio)
            or (fpd30_ratio is not None and fpd30_ratio < maturity_ratio)
        )
        if fpd7_ratio is None or fpd7_ratio < maturity_ratio:
            item["fpd7_rate"] = None
        if fpd30_ratio is None or fpd30_ratio < maturity_ratio:
            item["fpd30_rate"] = None
        result.append(item)
    return sorted(result, key=lambda item: item["day"])


def build_score_band_metrics(rows: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    for row in rows:
        item = {"band": str(row.get("band") or "未知")}
        item["band_order"] = _count(row.get("band_order"))
        item["samples"] = _count(row.get("samples"))
        item["fpd7_base"] = _count(row.get("fpd7_base"))
        item["fpd7_bad"] = _count(row.get("fpd7_bad"))
        item["fpd7_rate"] = safe_ratio(item["fpd7_bad"], item["fpd7_base"])
        item["fpd30_base"] = _count(row.get("fpd30_base"))
        item["fpd30_bad"] = _count(row.get("fpd30_bad"))
        item["fpd30_rate"] = safe_ratio(item["fpd30_bad"], item["fpd30_base"])
        result.append(item)
    return sorted(result, key=lambda item: item["band_order"])


def _bucket_effect(rows: Sequence[Mapping[str, Any]], base_field: str, bad_field: str) -> tuple[float | None, float | None, int, int, int]:
    bucket_totals: dict[float, list[int]] = {}
    for row in rows:
        base = _count(row.get(base_field))
        bad = max(0, min(_count(row.get(bad_field)), base))
        score_bin = _number(row.get("score_bin"))
        totals = bucket_totals.setdefault(score_bin, [0, 0])
        totals[0] += bad
        totals[1] += base - bad
    buckets = [
        (score_bin, totals[0], totals[1])
        for score_bin, totals in bucket_totals.items()
    ]
    buckets.sort(key=lambda item: item[0])
    mature_count = sum(item[1] + item[2] for item in buckets)
    bad_count = sum(item[1] for item in buckets)
    good_count = sum(item[2] for item in buckets)
    if bad_count <= 0 or good_count <= 0:
        return None, None, mature_count, bad_count, good_count

    cumulative_good = 0
    auc_numerator = 0.0
    cumulative_bad = 0
    ks = 0.0
    for _score_bin, bad, good in buckets:
        auc_numerator += bad * cumulative_good + 0.5 * bad * good
        cumulative_good += good
        cumulative_bad += bad
        ks = max(
            ks,
            abs(cumulative_bad / bad_count - cumulative_good / good_count),
        )
    auc = auc_numerator / (bad_count * good_count)
    return round(max(auc, 1 - auc), 6), round(ks, 6), mature_count, bad_count, good_count


def build_model_effect_trend(
    rows: Sequence[Mapping[str, Any]],
    daily_rows: Sequence[Mapping[str, Any]],
    target: str = "fpd7",
    maturity_ratio: float = 0.5,
    min_mature_count: int = 1000,
) -> list[dict[str, Any]]:
    """从日期×模型×分数桶聚合结果计算方向无关的近似 AUC/KS。"""
    if target not in TARGET_FIELDS:
        raise ValueError(f"unsupported target: {target}")
    base_field, bad_field = TARGET_FIELDS[target]
    grouped: dict[tuple[str, str, str], list[Mapping[str, Any]]] = {}
    for row in rows:
        day = str(row.get("day") or "")
        alias = str(row.get("alias") or "未知")
        model = str(row.get("model") or "")
        if day and model:
            grouped.setdefault((day, alias, model), []).append(row)
    daily = {
        (str(row.get("day") or ""), str(row.get("alias") or "未知")): row
        for row in daily_rows
        if row.get("day")
    }
    daily_by_day = {
        str(row.get("day") or ""): row
        for row in daily_rows
        if row.get("day")
    }
    result: list[dict[str, Any]] = []
    for (day, alias, model), bucket_rows in grouped.items():
        auc, ks, mature_count, bad_count, good_count = _bucket_effect(
            bucket_rows,
            base_field,
            bad_field,
        )
        score_valid_count = sum(_count(row.get("score_valid_cnt")) for row in bucket_rows)
        daily_row = daily.get((day, alias), daily_by_day.get(day, {}))
        applications = _count(daily_row.get("applications"))
        loan_success = _count(daily_row.get("loan_success"))
        observation_ratio = safe_ratio(mature_count, loan_success)
        warning = (
            mature_count < min_mature_count
            or observation_ratio is None
            or observation_ratio < maturity_ratio
        )
        if warning:
            auc = None
            ks = None
        result.append(
            {
                "day": day,
                "alias": alias,
                "model": model,
                "target": target,
                "auc": auc,
                "ks": ks,
                "mature_count": mature_count,
                "bad_count": bad_count,
                "good_count": good_count,
                "score_valid_count": score_valid_count,
                "score_coverage": safe_ratio(score_valid_count, applications),
                "maturity_ratio": observation_ratio,
                "maturity_warning": warning,
            }
        )
    return sorted(result, key=lambda item: (item["day"], item["model"]))


def _week_bounds(day: Any) -> tuple[str, str] | None:
    day_text = str(day or "")[:10]
    try:
        parsed = datetime.strptime(day_text, "%Y-%m-%d").date()
    except ValueError:
        return None
    week_start = parsed - timedelta(days=parsed.weekday())
    week_end = week_start + timedelta(days=6)
    return week_start.isoformat(), week_end.isoformat()


def build_model_effect_weekly(
    rows: Sequence[Mapping[str, Any]],
    alias_daily_rows: Sequence[Mapping[str, Any]] = (),
    target: str = "fpd7",
    maturity_ratio: float = 0.5,
    min_mature_count: int = 100,
) -> list[dict[str, Any]]:
    """按 alias 和自然周汇总 score 分桶后重新计算模型效果。"""
    if target not in TARGET_FIELDS:
        raise ValueError(f"unsupported target: {target}")
    base_field, bad_field = TARGET_FIELDS[target]
    grouped: dict[tuple[str, str, str], list[Mapping[str, Any]]] = {}
    for row in rows:
        bounds = _week_bounds(row.get("day"))
        model = str(row.get("model") or "")
        alias = str(row.get("alias") or "未知")
        if bounds and model:
            grouped.setdefault((bounds[0], alias, model), []).append(row)

    has_target_population = any(
        base_field in row and bad_field in row
        for row in alias_daily_rows
    )
    weekly_daily: dict[tuple[str, str], dict[str, int]] = {}
    for row in alias_daily_rows:
        bounds = _week_bounds(row.get("day"))
        alias = str(row.get("alias") or "未知")
        if not bounds:
            continue
        key = (bounds[0], alias)
        item = weekly_daily.setdefault(
            key,
            {"applications": 0, "loan_success": 0, base_field: 0, bad_field: 0},
        )
        item["applications"] += _count(row.get("applications"))
        item["loan_success"] += _count(row.get("loan_success"))
        if has_target_population:
            item[base_field] += _count(row.get(base_field))
            item[bad_field] += _count(row.get(bad_field))

    result: list[dict[str, Any]] = []
    for (week_start, alias, model), bucket_rows in grouped.items():
        auc, ks, effect_mature_count, bad_count, good_count = _bucket_effect(
            bucket_rows,
            base_field,
            bad_field,
        )
        score_valid_count = sum(_count(row.get("score_valid_cnt")) for row in bucket_rows)
        daily_row = weekly_daily.get((week_start, alias), {})
        applications = _count(daily_row.get("applications"))
        loan_success = _count(daily_row.get("loan_success"))
        population_mature_count = (
            _count(daily_row.get(base_field))
            if has_target_population
            else effect_mature_count
        )
        population_bad_count = (
            _count(daily_row.get(bad_field))
            if has_target_population
            else bad_count
        )
        observation_ratio = safe_ratio(population_mature_count, loan_success)
        sample_count_warning = population_mature_count < min_mature_count
        warning = (
            effect_mature_count < min_mature_count
            or sample_count_warning
        )
        display_count: int | None = None if sample_count_warning else population_mature_count
        display_badrate: float | None = None if sample_count_warning else safe_ratio(population_bad_count, population_mature_count)
        if warning:
            auc = None
            ks = None
        result.append(
            {
                "week_start": week_start,
                "week_end": (datetime.strptime(week_start, "%Y-%m-%d").date() + timedelta(days=6)).isoformat(),
                "alias": alias,
                "model": model,
                "target": target,
                "count": display_count,
                "badrate": display_badrate,
                "auc": auc,
                "ks": ks,
                "mature_count": effect_mature_count,
                "bad_count": bad_count,
                "good_count": good_count,
                "score_valid_count": score_valid_count,
                "score_coverage": safe_ratio(score_valid_count, applications),
                "maturity_ratio": observation_ratio,
                "maturity_warning": warning,
            }
        )
    return sorted(result, key=lambda item: (item["week_start"], item["alias"], item["model"]))


def build_latest_model_effect(rows: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    """取每个模型和目标的最新可用日期；若尚无可用日则保留最新的警告行。"""
    grouped: dict[tuple[str, str, str], list[Mapping[str, Any]]] = {}
    for row in rows:
        model = str(row.get("model") or "")
        alias = str(row.get("alias") or "未知")
        target = str(row.get("target") or "")
        if model and target:
            grouped.setdefault((target, alias, model), []).append(row)
    result: list[dict[str, Any]] = []
    for (target, alias, model), items in grouped.items():
        usable = [item for item in items if item.get("auc") is not None and item.get("ks") is not None]
        latest = max(usable or items, key=lambda item: str(item.get("day") or ""))
        item = dict(latest)
        item["status"] = "可用" if not item.get("maturity_warning") and item.get("auc") is not None else "成熟度不足"
        result.append(item)
    return sorted(result, key=lambda item: (item["target"], item["model"]))


def build_model_coverage(overview: Mapping[str, Any], total: Any) -> list[dict[str, Any]]:
    total_count = _count(total)
    result: list[dict[str, Any]] = []
    for field, label in MODEL_SCORES:
        nonempty = _count(overview.get(f"{field}_nonempty"))
        sentinel = _count(overview.get(f"{field}_sentinel"))
        valid = max(nonempty - sentinel, 0)
        result.append(
            {
                "field": field,
                "model": label,
                "nonempty": nonempty,
                "sentinel": sentinel,
                "valid": valid,
                "coverage": safe_ratio(valid, total_count),
            }
        )
    return sorted(result, key=lambda item: item["coverage"] or 0, reverse=True)


def build_monitoring_payload(
    *,
    overview: Mapping[str, Any],
    business_rows: Sequence[Mapping[str, Any]],
    daily_rows: Sequence[Mapping[str, Any]],
    score_band_rows: Sequence[Mapping[str, Any]],
    model_effect_rows: Sequence[Mapping[str, Any]] = (),
    alias_daily_rows: Sequence[Mapping[str, Any]] = (),
    flag_mob_type_options: Sequence[str] = (),
    flag_product_options: Sequence[str] = (),
    cash_ser_call_node_options: Sequence[str] = (),
    selected_flag_mob_type: str = "",
    selected_flag_product: str = "",
    selected_cash_ser_call_node: str = "",
    partition: str,
    table_name: str,
) -> dict[str, Any]:
    generated_at = datetime.now(timezone.utc).isoformat()
    stage_metrics = build_stage_metrics(overview)
    total = _count(overview.get("row_count"))
    model_effect_trend = [
        effect
        for target in TARGET_FIELDS
        for effect in build_model_effect_trend(model_effect_rows, daily_rows, target=target)
    ]
    model_effect_weekly = [
        effect
        for target in TARGET_FIELDS
        for effect in build_model_effect_weekly(
            model_effect_rows,
            alias_daily_rows or daily_rows,
            target=target,
        )
    ]
    return {
        "meta": {
            "source_table": table_name,
            "partition": partition,
            "generated_at": generated_at,
            "date_field": "event_date",
            "maturity_rule": "趋势要求成熟观察覆盖率不少于放款成功数50%；周度模型效果按模型分对应目标到期样本数不少于100",
            "filters": {
                "flag_mob_type": selected_flag_mob_type,
                "flag_product": selected_flag_product,
                "cash_ser_call_node": selected_cash_ser_call_node,
            },
            "notes": [
                "模型分数字段为STRING；-1按未命中处理。",
                "业务环节指标保留各自分母，不将不同人群拼成单一转化漏斗。",
            ],
        },
        "summary": {
            "row_count": total,
            "business_cnt": _count(overview.get("business_cnt")),
            "cid_cnt": _count(overview.get("cid_cnt")),
            "min_create_time": str(overview.get("min_create_time") or ""),
            "max_create_time": str(overview.get("max_create_time") or ""),
            "min_event_date": str(overview.get("min_event_date") or ""),
            "max_event_date": str(overview.get("max_event_date") or ""),
            "min_loan_date": str(overview.get("min_loan_date") or ""),
            "max_loan_date": str(overview.get("max_loan_date") or ""),
        },
        "stage_metrics": stage_metrics,
        "business_type_metrics": build_business_type_metrics(business_rows),
        "daily_trend": build_daily_trend(daily_rows),
        "score_bands": build_score_band_metrics(score_band_rows),
        "model_coverage": build_model_coverage(overview, total),
        "model_effect_trend": model_effect_trend,
        "model_effect_weekly": model_effect_weekly,
        "model_effect_aliases": sorted(
            {
                str(row.get("alias") or "未知")
                for row in alias_daily_rows
            }
            | {row["alias"] for row in model_effect_weekly}
        ),
        "model_effect_mob_types": sorted(
            set(flag_mob_type_options)
            or {str(row.get("flag_mob_type") or "未知") for row in alias_daily_rows}
        ),
        "model_effect_products": sorted(
            set(flag_product_options)
            or {str(row.get("flag_product") or "未知") for row in alias_daily_rows}
        ),
        "model_effect_cash_ser_call_nodes": sorted(
            set(cash_ser_call_node_options) or set(CASH_SER_CALL_NODE_OPTIONS)
        ),
        "latest_model_effect": build_latest_model_effect(model_effect_trend),
    }
