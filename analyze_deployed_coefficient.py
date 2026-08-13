from __future__ import annotations

"""Validate cash_remark1 in the 2026-08-12 new-strategy batch.

The comparison uses the production-like 315-cell lookup workbook found next to
the supplied data dictionary. All output is aggregate by policy cell.
"""

import json
from collections import Counter, defaultdict
import csv
from pathlib import Path
from typing import Any

from openpyxl import load_workbook

from probe_flexi_cash_strategy import get_odps, query

TABLE = "pb_biz_credit.flexi_cash_jq_result_v1"
COEFFICIENT_FILE = Path("C:/Users/PP-2026070302/Desktop") / "\u63d0\u989d\u7cfb\u657020260812.xlsx"
OUTPUT = Path("risk_analysis/deployed_coefficient_check_0812.json")
CSV_OUTPUT = Path("risk_analysis/online_strategy_cell_comparison_20260812.csv")

CUSTOMER_MAP = {
    "HAVE_SINGLE_LOAN": "\u6709\u5355\u671f\u501f\u6b3e",
    "HAVE_SINGLE_NOLOAN": "\u65e0\u5355\u671f\u501f\u6b3e",
    "NO_SINGLE": "\u65e0\u5355\u671f",
}
USE_RATE_MAP = {"1": "\u9ad8\u989d\u5ea6\u4f7f\u7528\u7387", "2": "\u4e2d\u989d\u5ea6\u4f7f\u7528\u7387", "3": "\u4f4e\u989d\u5ea6\u4f7f\u7528\u7387"}
SCORE_MAP = {"5": "A", "4": "B", "3": "C", "2": "D", "1": "E"}


def normalized_code(value: Any) -> str:
    text = "" if value is None else str(value).strip()
    if text.endswith(".0"):
        text = text[:-2]
    return text


def number(value: Any) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def lookup_key(customer: Any, use_rate: Any, loan_count: Any, score: Any) -> tuple[str, str, int, str] | None:
    customer_name = CUSTOMER_MAP.get(normalized_code(customer))
    use_rate_name = USE_RATE_MAP.get(normalized_code(use_rate))
    score_name = SCORE_MAP.get(normalized_code(score))
    try:
        # The terminal strategy-table cell "7" means loan-count >= 7.
        # Values 1–6 retain their own cells; all larger values map to 7.
        count = min(max(1, int(float(loan_count))), 7)
    except (TypeError, ValueError):
        return None
    if not customer_name or not use_rate_name or not score_name:
        return None
    return customer_name, use_rate_name, count, score_name


def policy_lookup() -> dict[tuple[str, str, int, str], float]:
    workbook = load_workbook(COEFFICIENT_FILE, data_only=True, read_only=True)
    ws = workbook[workbook.sheetnames[0]]
    result: dict[tuple[str, str, int, str], float] = {}
    for row in ws.iter_rows(min_row=2, values_only=True):
        if not any(item is not None for item in row):
            continue
        result[(str(row[0]).strip(), str(row[1]).strip(), int(float(row[2])), str(row[3]).strip())] = float(row[4])
    return result


def main() -> None:
    policy = policy_lookup()
    odps = get_odps()
    sql = f"""
        SELECT jq_customer_flag, defq_use_rate_level, separate_installment_loan_cnt,
               jq_mix_score_bin, cash_remark1, te_flag,
               COUNT(1) AS cnt,
               SUM(CASE WHEN CAST(cash_quota_amount_now_after AS DOUBLE) > CAST(jq_credit_quota AS DOUBLE) THEN 1 ELSE 0 END) AS actual_raise_cnt,
               SUM(CASE WHEN CAST(cash_quota_amount_now_after AS DOUBLE) = CAST(jq_credit_quota AS DOUBLE) THEN 1 ELSE 0 END) AS actual_unchanged_cnt,
               SUM(CASE WHEN CAST(cash_quota_amount_now_after AS DOUBLE) < CAST(jq_credit_quota AS DOUBLE) THEN 1 ELSE 0 END) AS actual_down_cnt
        FROM {TABLE}
        WHERE jq_date = '2026-08-12' AND str_type = 'new'
          AND CAST(jq_credit_quota AS DOUBLE) >= 0
          AND CAST(cash_quota_amount_now_after AS DOUBLE) >= 0
        GROUP BY jq_customer_flag, defq_use_rate_level, separate_installment_loan_cnt,
                 jq_mix_score_bin, cash_remark1, te_flag
    """
    groups = query(odps, sql)

    summary: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))
    mismatch: list[dict[str, Any]] = []
    no_lookup: list[dict[str, Any]] = []
    loan_count_behavior: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))
    cell_summary: dict[tuple[str, str, int, str], dict[str, Any]] = {}
    unresolved_key = ("未映射", "未映射", 0, "未映射")

    for row in groups:
        count = int(row["cnt"])
        actual_raise_cnt = int(row["actual_raise_cnt"] or 0)
        actual_unchanged_cnt = int(row["actual_unchanged_cnt"] or 0)
        actual_down_cnt = int(row["actual_down_cnt"] or 0)
        flag = str(row["te_flag"])
        summary["all"]["total"] += count
        summary["all"]["actual_raise_cnt"] += actual_raise_cnt
        summary["all"]["actual_unchanged_cnt"] += actual_unchanged_cnt
        summary["all"]["actual_down_cnt"] += actual_down_cnt
        summary[flag]["total"] += count
        summary[flag]["actual_raise_cnt"] += actual_raise_cnt
        summary[flag]["actual_unchanged_cnt"] += actual_unchanged_cnt
        summary[flag]["actual_down_cnt"] += actual_down_cnt
        source_count = normalized_code(row["separate_installment_loan_cnt"])
        lookup = lookup_key(
            row["jq_customer_flag"],
            row["defq_use_rate_level"],
            row["separate_installment_loan_cnt"],
            row["jq_mix_score_bin"],
        )
        if lookup is None or lookup not in policy:
            summary["all"]["no_lookup"] += count
            summary[flag]["no_lookup"] += count
            cell_key = unresolved_key
            cell = cell_summary.setdefault(
                cell_key,
                {
                    "policy_key": "未映射策略格",
                    "expected_cash_remark1": None,
                    "total_cnt": 0,
                    "coefficient_match_cnt": 0,
                    "coefficient_mismatch_cnt": 0,
                    "te_flag_0_cnt": 0,
                    "te_flag_1_cnt": 0,
                    "other_te_flag_cnt": 0,
                    "actual_raise_cnt": 0,
                    "actual_unchanged_cnt": 0,
                    "actual_down_cnt": 0,
                    "te_flag_vs_actual_consistent_cnt": 0,
                    "te_flag_vs_actual_inconsistent_cnt": 0,
                    "positive_config_no_raise_cnt": 0,
                    "zero_config_actual_raise_cnt": 0,
                    "configured_rate_distribution": {},
                    "lookup_status": "unsupported_or_missing_policy_cell",
                },
            )
            cell["total_cnt"] += count
            cell[f"te_flag_{flag}_cnt" if flag in {"0", "1"} else "other_te_flag_cnt"] += count
            cell["actual_raise_cnt"] += actual_raise_cnt
            cell["actual_unchanged_cnt"] += actual_unchanged_cnt
            cell["actual_down_cnt"] += actual_down_cnt
            if flag == "1":
                cell["te_flag_vs_actual_consistent_cnt"] += actual_raise_cnt
                cell["te_flag_vs_actual_inconsistent_cnt"] += actual_unchanged_cnt + actual_down_cnt
            elif flag == "0":
                cell["te_flag_vs_actual_consistent_cnt"] += actual_unchanged_cnt
                cell["te_flag_vs_actual_inconsistent_cnt"] += actual_raise_cnt + actual_down_cnt
            else:
                cell["te_flag_vs_actual_inconsistent_cnt"] += count
            actual = number(row["cash_remark1"])
            if actual is not None and actual > 0 and flag == "0":
                cell["positive_config_no_raise_cnt"] += count
            if (actual is None or abs(actual) < 1e-10) and actual_raise_cnt:
                cell["zero_config_actual_raise_cnt"] += actual_raise_cnt
            distribution = cell["configured_rate_distribution"]
            rate_key = "null" if actual is None else f"{actual:g}"
            distribution[rate_key] = distribution.get(rate_key, 0) + count
            no_lookup.append({**row, "reason": "unsupported_or_missing_policy_cell"})
            continue
        expected = policy[lookup]
        actual = number(row["cash_remark1"])
        is_match = actual is not None and abs(actual - expected) < 1e-10
        bucket = "coefficient_match" if is_match else "coefficient_mismatch"
        summary["all"][bucket] += count
        summary[flag][bucket] += count
        # The workbook's row labelled 7 is the terminal 7-and-above bucket.
        loan_bucket = "7 (including 7+)" if source_count not in {str(i) for i in range(1, 8)} else source_count
        loan_count_behavior[loan_bucket][bucket] += count

        cell = cell_summary.setdefault(
            lookup,
            {
                "policy_key": " | ".join(map(str, lookup)),
                "expected_cash_remark1": expected,
                "total_cnt": 0,
                "coefficient_match_cnt": 0,
                "coefficient_mismatch_cnt": 0,
                "te_flag_0_cnt": 0,
                "te_flag_1_cnt": 0,
                "other_te_flag_cnt": 0,
                "actual_raise_cnt": 0,
                "actual_unchanged_cnt": 0,
                "actual_down_cnt": 0,
                "te_flag_vs_actual_consistent_cnt": 0,
                "te_flag_vs_actual_inconsistent_cnt": 0,
                "positive_config_no_raise_cnt": 0,
                "zero_config_actual_raise_cnt": 0,
                "configured_rate_distribution": {},
            },
        )
        cell["total_cnt"] += count
        cell[bucket + "_cnt"] += count
        cell[f"te_flag_{flag}_cnt" if flag in {"0", "1"} else "other_te_flag_cnt"] += count
        cell["actual_raise_cnt"] += actual_raise_cnt
        cell["actual_unchanged_cnt"] += actual_unchanged_cnt
        cell["actual_down_cnt"] += actual_down_cnt
        if flag == "1":
            cell["te_flag_vs_actual_consistent_cnt"] += actual_raise_cnt
            cell["te_flag_vs_actual_inconsistent_cnt"] += actual_unchanged_cnt + actual_down_cnt
        elif flag == "0":
            cell["te_flag_vs_actual_consistent_cnt"] += actual_unchanged_cnt
            cell["te_flag_vs_actual_inconsistent_cnt"] += actual_raise_cnt + actual_down_cnt
        else:
            cell["te_flag_vs_actual_inconsistent_cnt"] += count
        if actual is not None and actual > 0 and flag == "0":
            cell["positive_config_no_raise_cnt"] += count
        if (actual is None or abs(actual) < 1e-10) and actual_raise_cnt:
            cell["zero_config_actual_raise_cnt"] += actual_raise_cnt
        distribution = cell["configured_rate_distribution"]
        rate_key = "null" if actual is None else f"{actual:g}"
        distribution[rate_key] = distribution.get(rate_key, 0) + count
        if not is_match:
            mismatch.append(
                {
                    **row,
                    "policy_key": " | ".join(map(str, lookup)),
                    "expected_cash_remark1": expected,
                    "actual_cash_remark1": actual,
                }
            )

    for item in mismatch:
        item["cnt"] = int(item["cnt"])
    mismatch.sort(key=lambda item: int(item["cnt"]), reverse=True)
    for item in no_lookup:
        item["cnt"] = int(item["cnt"])
    no_lookup.sort(key=lambda item: int(item["cnt"]), reverse=True)

    cells = []
    for cell in cell_summary.values():
        total = int(cell["total_cnt"])
        cell["coefficient_match_rate"] = cell["coefficient_match_cnt"] / total if total else None
        cell["te_flag_vs_actual_consistency_rate"] = (
            cell["te_flag_vs_actual_consistent_cnt"] / total if total else None
        )
        cell["coefficient_consistent"] = (
            cell.get("lookup_status") is None and cell["coefficient_mismatch_cnt"] == 0
        )
        cell["execution_consistent"] = cell["te_flag_vs_actual_inconsistent_cnt"] == 0
        cell["strategy_consistent"] = cell["coefficient_consistent"] and cell["execution_consistent"]
        cells.append(cell)
    observed_keys = set(cell_summary)
    for lookup, expected in policy.items():
        if lookup in observed_keys:
            continue
        cells.append(
            {
                "policy_key": " | ".join(map(str, lookup)),
                "expected_cash_remark1": expected,
                "total_cnt": 0,
                "coefficient_match_cnt": 0,
                "coefficient_mismatch_cnt": 0,
                "te_flag_0_cnt": 0,
                "te_flag_1_cnt": 0,
                "other_te_flag_cnt": 0,
                "actual_raise_cnt": 0,
                "actual_unchanged_cnt": 0,
                "actual_down_cnt": 0,
                "te_flag_vs_actual_consistent_cnt": 0,
                "te_flag_vs_actual_inconsistent_cnt": 0,
                "positive_config_no_raise_cnt": 0,
                "zero_config_actual_raise_cnt": 0,
                "configured_rate_distribution": {},
                "coefficient_match_rate": None,
                "te_flag_vs_actual_consistency_rate": None,
                "coefficient_consistent": None,
                "execution_consistent": None,
                "strategy_consistent": None,
                "observation_status": "no_customer_in_batch",
            }
        )
    cells.sort(key=lambda item: (-int(item["total_cnt"]), item["policy_key"]))

    export_columns = [
        "policy_key", "expected_cash_remark1", "total_cnt",
        "coefficient_match_cnt", "coefficient_mismatch_cnt", "coefficient_match_rate",
        "te_flag_1_cnt", "te_flag_0_cnt", "other_te_flag_cnt",
        "actual_raise_cnt", "actual_unchanged_cnt", "actual_down_cnt",
        "te_flag_vs_actual_consistency_rate", "positive_config_no_raise_cnt",
        "zero_config_actual_raise_cnt", "coefficient_consistent", "execution_consistent",
        "strategy_consistent", "configured_rate_distribution", "observation_status", "lookup_status",
    ]
    with CSV_OUTPUT.open("w", encoding="utf-8-sig", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=export_columns, extrasaction="ignore")
        writer.writeheader()
        for cell in cells:
            writer.writerow({
                **cell,
                "configured_rate_distribution": json.dumps(
                    cell["configured_rate_distribution"], ensure_ascii=False, sort_keys=True
                ),
            })

    out = {
        "population": "jq_date=2026-08-12 AND str_type=new AND valid before/after limits",
        "policy_cell_count": len(policy),
        "observed_policy_cell_count": sum(1 for item in cells if item["total_cnt"] > 0 and item["policy_key"] != "未映射策略格"),
        "unobserved_policy_cell_count": sum(1 for item in cells if item.get("observation_status") == "no_customer_in_batch"),
        "unmapped_group_count": 1 if unresolved_key in cell_summary else 0,
        "summary_by_te_flag": {key: dict(value) for key, value in summary.items()},
        "loan_count_behavior": {key: dict(value) for key, value in loan_count_behavior.items()},
        "policy_cell_compliance": cells,
        "top_coefficient_mismatches": mismatch[:100],
        "top_no_lookup_groups": no_lookup[:100],
        "online_configuration_comparison_csv": str(CSV_OUTPUT),
    }
    OUTPUT.write_text(json.dumps(out, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    print(f"Wrote {OUTPUT}")
    print(f"Wrote {CSV_OUTPUT}")


if __name__ == "__main__":
    main()
