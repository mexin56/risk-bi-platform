from __future__ import annotations

"""Read-only SQL checks for the 2026-08-12 flexi-cash increase strategy.

No credentials are printed or persisted. The strategy formula is evaluated with
several rounding / cap variants so the deployed calculation can be inferred
from the batch result table.
"""

import json
from pathlib import Path

from probe_flexi_cash_strategy import get_odps, query

TABLE = "pb_biz_credit.flexi_cash_jq_result_v1"
OUTPUT = Path("risk_analysis/formula_tests_0812.json")


def main() -> None:
    odps = get_odps()
    # Amount columns are stored in the smallest currency unit. 10,000 = 100
    # currency units, the expected product rounding grain observed in samples.
    sql = f"""
    WITH base AS (
      SELECT
        jq_date, str_type, app_flow_flag, te_flag,
        CAST(jq_credit_quota AS DOUBLE) AS before_limit,
        CAST(cash_quota_amount_now_after AS DOUBLE) AS after_limit,
        CAST(cash_remark1 AS DOUBLE) AS raise_rate,
        CAST(after_adjust_credit_limit AS DOUBLE) AS total_cap,
        CAST(credit_max_limit AS DOUBLE) AS increase_cap
      FROM {TABLE}
      WHERE jq_date = '2026-08-12'
        AND str_type = 'new'
        AND te_flag = 1
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
        CASE
          WHEN rate_target <= total_cap AND rate_target <= increase_target THEN rate_target
          WHEN total_cap <= increase_target THEN total_cap
          ELSE increase_target
        END AS expected_limit
      FROM calc
    )
    SELECT
      COUNT(1) AS eligible_cnt,
      SUM(CASE WHEN after_limit = expected_limit THEN 1 ELSE 0 END) AS exact_match_cnt,
      SUM(CASE WHEN after_limit = expected_limit THEN 1.0 ELSE 0.0 END) / COUNT(1) AS exact_match_rate,
      SUM(CASE WHEN after_limit > before_limit THEN 1 ELSE 0 END) AS actual_raise_cnt,
      SUM(CASE WHEN after_limit < before_limit THEN 1 ELSE 0 END) AS actual_down_cnt,
      SUM(CASE WHEN rate_target <= total_cap AND rate_target <= increase_target THEN 1 ELSE 0 END) AS rate_bound_cnt,
      SUM(CASE WHEN total_cap < rate_target AND total_cap <= increase_target THEN 1 ELSE 0 END) AS total_cap_bound_cnt,
      SUM(CASE WHEN increase_target < rate_target AND increase_target < total_cap THEN 1 ELSE 0 END) AS increase_cap_bound_cnt,
      MIN(after_limit - expected_limit) AS min_gap,
      MAX(after_limit - expected_limit) AS max_gap,
      AVG(after_limit - expected_limit) AS avg_gap
    FROM expected
    """
    by_rate_sql = f"""
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
      SELECT *, CASE WHEN rate_target <= total_cap AND rate_target <= increase_target THEN rate_target
                      WHEN total_cap <= increase_target THEN total_cap ELSE increase_target END AS expected_limit
      FROM calc
    )
    SELECT raise_rate, COUNT(1) AS cnt,
           SUM(CASE WHEN after_limit = expected_limit THEN 1 ELSE 0 END) AS exact_match_cnt,
           AVG(before_limit) AS avg_before_limit,
           AVG(after_limit) AS avg_after_limit,
           AVG(after_limit - before_limit) AS avg_raise_amount,
           AVG((after_limit - before_limit) / before_limit) AS avg_actual_rate,
           SUM(CASE WHEN after_limit > before_limit THEN 1 ELSE 0 END) AS actual_raise_cnt,
           SUM(CASE WHEN after_limit = total_cap THEN 1 ELSE 0 END) AS actual_total_cap_bind_cnt,
           SUM(CASE WHEN after_limit = increase_target THEN 1 ELSE 0 END) AS actual_increase_cap_bind_cnt
    FROM expected
    GROUP BY raise_rate
    ORDER BY raise_rate
    """
    # Aggregate exception profiles only. Customer / contract identifiers are
    # intentionally not exported by the monitor artifact.
    exceptions_sql = f"""
    WITH base AS (
      SELECT cashloan_cid_mob_type, defq_use_rate_level, jq_customer_flag,
        separate_installment_loan_cnt, jq_mix_score_bin,
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
      SELECT *, CASE WHEN rate_target <= total_cap AND rate_target <= increase_target THEN rate_target
                      WHEN total_cap <= increase_target THEN total_cap ELSE increase_target END AS expected_limit
      FROM calc
    )
    SELECT cashloan_cid_mob_type, defq_use_rate_level, jq_customer_flag,
           separate_installment_loan_cnt, jq_mix_score_bin, raise_rate,
           COUNT(1) AS cnt,
           AVG(before_limit) AS avg_before_limit,
           AVG(after_limit) AS avg_after_limit,
           AVG(expected_limit) AS avg_expected_limit,
           AVG(after_limit - expected_limit) AS avg_gap,
           MIN(after_limit - expected_limit) AS min_gap,
           MAX(after_limit - expected_limit) AS max_gap
    FROM expected
    WHERE after_limit <> expected_limit
    GROUP BY cashloan_cid_mob_type, defq_use_rate_level, jq_customer_flag,
             separate_installment_loan_cnt, jq_mix_score_bin, raise_rate
    ORDER BY cnt DESC
    LIMIT 100
    """
    result = {
        "summary": query(odps, sql),
        "by_rate": query(odps, by_rate_sql),
        "exceptions": query(odps, exceptions_sql),
    }
    OUTPUT.write_text(json.dumps(result, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    print(f"Wrote {OUTPUT}")


if __name__ == "__main__":
    main()
