from __future__ import annotations

"""Aggregate checks for post-limit calculation and cap behavior, 2026-08-12."""

import json
from pathlib import Path

from probe_flexi_cash_strategy import get_odps, query

TABLE = "pb_biz_credit.flexi_cash_jq_result_v1"
OUTPUT = Path("risk_analysis/limit_formula_variants_0812.json")


def main() -> None:
    odps = get_odps()
    sql = f"""
    WITH base AS (
      SELECT
        CAST(jq_credit_quota AS DOUBLE) AS before_limit,
        CAST(cash_quota_amount_now_after AS DOUBLE) AS after_limit,
        CAST(cash_remark1 AS DOUBLE) AS raise_rate,
        CAST(after_adjust_credit_limit AS DOUBLE) AS total_cap,
        CAST(credit_max_limit AS DOUBLE) AS increase_cap
      FROM {TABLE}
      WHERE jq_date = '2026-08-12' AND str_type = 'new' AND te_flag = 1
        AND CAST(jq_credit_quota AS DOUBLE) >= 0
        AND CAST(cash_quota_amount_now_after AS DOUBLE) >= 0
        AND CAST(cash_remark1 AS DOUBLE) >= 0
        AND CAST(after_adjust_credit_limit AS DOUBLE) >= 0
        AND CAST(credit_max_limit AS DOUBLE) >= 0
    ), calc AS (
      SELECT *,
        CEIL(before_limit * (1 + raise_rate) / 10000) * 10000 AS rate_target,
        before_limit + increase_cap AS increase_target
      FROM base
    ), expected AS (
      SELECT *,
        CASE WHEN rate_target <= total_cap AND rate_target <= increase_target THEN rate_target
             WHEN total_cap <= increase_target THEN total_cap ELSE increase_target END AS hard_cap_expected,
        CASE WHEN rate_target <= increase_target THEN rate_target ELSE increase_target END AS no_total_cap_expected,
        CASE WHEN before_limit >= total_cap THEN
               CASE WHEN rate_target <= increase_target THEN rate_target ELSE increase_target END
             WHEN rate_target <= total_cap AND rate_target <= increase_target THEN rate_target
             WHEN total_cap <= increase_target THEN total_cap ELSE increase_target END AS grandfather_cap_expected
      FROM calc
    )
    SELECT
      COUNT(1) AS eligible_cnt,
      SUM(CASE WHEN after_limit = hard_cap_expected THEN 1 ELSE 0 END) AS hard_cap_match_cnt,
      SUM(CASE WHEN after_limit = no_total_cap_expected THEN 1 ELSE 0 END) AS no_total_cap_match_cnt,
      SUM(CASE WHEN after_limit = grandfather_cap_expected THEN 1 ELSE 0 END) AS grandfather_cap_match_cnt,
      SUM(CASE WHEN after_limit = rate_target THEN 1 ELSE 0 END) AS pure_rate_match_cnt,
      SUM(CASE WHEN after_limit = increase_target THEN 1 ELSE 0 END) AS increase_cap_match_cnt,
      SUM(CASE WHEN after_limit = total_cap THEN 1 ELSE 0 END) AS total_cap_match_cnt,
      SUM(CASE WHEN before_limit >= total_cap THEN 1 ELSE 0 END) AS pre_at_or_above_total_cap_cnt,
      SUM(CASE WHEN after_limit > total_cap THEN 1 ELSE 0 END) AS after_above_total_cap_cnt,
      SUM(CASE WHEN after_limit > increase_target THEN 1 ELSE 0 END) AS after_above_increase_cap_cnt,
      SUM(CASE WHEN after_limit < before_limit THEN 1 ELSE 0 END) AS down_limit_cnt
    FROM expected
    """
    classes_sql = f"""
    WITH base AS (
      SELECT
        CAST(jq_credit_quota AS DOUBLE) AS before_limit,
        CAST(cash_quota_amount_now_after AS DOUBLE) AS after_limit,
        CAST(cash_remark1 AS DOUBLE) AS raise_rate,
        CAST(after_adjust_credit_limit AS DOUBLE) AS total_cap,
        CAST(credit_max_limit AS DOUBLE) AS increase_cap
      FROM {TABLE}
      WHERE jq_date = '2026-08-12' AND str_type = 'new' AND te_flag = 1
        AND CAST(jq_credit_quota AS DOUBLE) >= 0
        AND CAST(cash_quota_amount_now_after AS DOUBLE) >= 0
        AND CAST(cash_remark1 AS DOUBLE) >= 0
        AND CAST(after_adjust_credit_limit AS DOUBLE) >= 0
        AND CAST(credit_max_limit AS DOUBLE) >= 0
    ), calc AS (
      SELECT *, CEIL(before_limit * (1 + raise_rate) / 10000) * 10000 AS rate_target,
        before_limit + increase_cap AS increase_target
      FROM base
    ), expected AS (
      SELECT *,
        CASE WHEN rate_target <= total_cap AND rate_target <= increase_target THEN rate_target
             WHEN total_cap <= increase_target THEN total_cap ELSE increase_target END AS hard_cap_expected,
        CASE WHEN before_limit >= total_cap THEN
               CASE WHEN rate_target <= increase_target THEN rate_target ELSE increase_target END
             WHEN rate_target <= total_cap AND rate_target <= increase_target THEN rate_target
             WHEN total_cap <= increase_target THEN total_cap ELSE increase_target END AS grandfather_cap_expected
      FROM calc
    )
    SELECT
      CASE
        WHEN after_limit = hard_cap_expected THEN 'A_hard_cap_exact'
        WHEN after_limit = grandfather_cap_expected THEN 'B_cap_skipped_for_grandfathered'
        WHEN after_limit = rate_target THEN 'C_pure_rate_only'
        WHEN after_limit = increase_target THEN 'D_single_increase_cap_only'
        WHEN after_limit > total_cap THEN 'E_above_total_cap'
        WHEN after_limit > increase_target THEN 'F_above_single_increase_cap'
        WHEN after_limit > before_limit THEN 'G_other_raise_mismatch'
        ELSE 'H_other'
      END AS result_class,
      COUNT(1) AS cnt,
      AVG(before_limit) AS avg_before_limit,
      AVG(after_limit) AS avg_after_limit,
      AVG(after_limit - before_limit) AS avg_change,
      MIN(after_limit - hard_cap_expected) AS min_gap_vs_hard_cap,
      MAX(after_limit - hard_cap_expected) AS max_gap_vs_hard_cap
    FROM expected
    GROUP BY CASE
        WHEN after_limit = hard_cap_expected THEN 'A_hard_cap_exact'
        WHEN after_limit = grandfather_cap_expected THEN 'B_cap_skipped_for_grandfathered'
        WHEN after_limit = rate_target THEN 'C_pure_rate_only'
        WHEN after_limit = increase_target THEN 'D_single_increase_cap_only'
        WHEN after_limit > total_cap THEN 'E_above_total_cap'
        WHEN after_limit > increase_target THEN 'F_above_single_increase_cap'
        WHEN after_limit > before_limit THEN 'G_other_raise_mismatch'
        ELSE 'H_other'
    END
    ORDER BY cnt DESC
    """
    cap_cross_sql = f"""
    WITH base AS (
      SELECT
        CAST(jq_credit_quota AS DOUBLE) AS before_limit,
        CAST(cash_quota_amount_now_after AS DOUBLE) AS after_limit,
        CAST(cash_remark1 AS DOUBLE) AS raise_rate,
        CAST(after_adjust_credit_limit AS DOUBLE) AS total_cap,
        CAST(credit_max_limit AS DOUBLE) AS increase_cap
      FROM {TABLE}
      WHERE jq_date = '2026-08-12' AND str_type = 'new' AND te_flag = 1
        AND CAST(jq_credit_quota AS DOUBLE) >= 0
        AND CAST(cash_quota_amount_now_after AS DOUBLE) >= 0
        AND CAST(cash_remark1 AS DOUBLE) >= 0
        AND CAST(after_adjust_credit_limit AS DOUBLE) >= 0
        AND CAST(credit_max_limit AS DOUBLE) >= 0
    )
    SELECT
      CASE WHEN before_limit >= total_cap THEN 'pre>=total_cap' ELSE 'pre<total_cap' END AS total_cap_status,
      CASE WHEN after_limit > total_cap THEN 'after>total_cap' ELSE 'after<=total_cap' END AS after_total_status,
      CASE WHEN after_limit > before_limit + increase_cap THEN 'after>pre+single_cap' ELSE 'after<=pre+single_cap' END AS increase_cap_status,
      COUNT(1) AS cnt,
      AVG(before_limit) AS avg_before_limit,
      AVG(after_limit) AS avg_after_limit
    FROM base
    GROUP BY CASE WHEN before_limit >= total_cap THEN 'pre>=total_cap' ELSE 'pre<total_cap' END,
             CASE WHEN after_limit > total_cap THEN 'after>total_cap' ELSE 'after<=total_cap' END,
             CASE WHEN after_limit > before_limit + increase_cap THEN 'after>pre+single_cap' ELSE 'after<=pre+single_cap' END
    ORDER BY cnt DESC
    """
    out = {
        "summary": query(odps, sql),
        "classes": query(odps, classes_sql),
        "cap_cross": query(odps, cap_cross_sql),
    }
    OUTPUT.write_text(json.dumps(out, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    print(f"Wrote {OUTPUT}")


if __name__ == "__main__":
    main()
