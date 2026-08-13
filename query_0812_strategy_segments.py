from __future__ import annotations

import json
from pathlib import Path

from probe_flexi_cash_strategy import get_odps, query

TABLE = "pb_biz_credit.flexi_cash_jq_result_v1"
OUTPUT = Path("risk_analysis/strategy_segments_0812.json")


def main() -> None:
    odps = get_odps()
    queries = {
        "by_score_and_te_flag": f"""
          SELECT jq_mix_score_bin, te_flag, COUNT(1) AS cnt,
            SUM(CAST(jq_credit_quota AS DOUBLE)) AS before_sum_cent,
            SUM(CAST(cash_quota_amount_now_after AS DOUBLE)) AS after_sum_cent,
            SUM(CASE WHEN CAST(cash_remark1 AS DOUBLE)>0 THEN 1 ELSE 0 END) AS positive_rate_cnt,
            AVG(CAST(cash_remark1 AS DOUBLE)) AS avg_configured_rate
          FROM {TABLE}
          WHERE jq_date='2026-08-12' AND str_type='new'
            AND CAST(jq_credit_quota AS DOUBLE)>=0 AND CAST(cash_quota_amount_now_after AS DOUBLE)>=0
          GROUP BY jq_mix_score_bin,te_flag
          ORDER BY jq_mix_score_bin,te_flag
        """,
        "by_customer_stage_and_te_flag": f"""
          SELECT cashloan_cid_mob_type, te_flag, COUNT(1) AS cnt,
            SUM(CAST(jq_credit_quota AS DOUBLE)) AS before_sum_cent,
            SUM(CAST(cash_quota_amount_now_after AS DOUBLE)) AS after_sum_cent,
            SUM(CASE WHEN CAST(cash_remark1 AS DOUBLE)>0 THEN 1 ELSE 0 END) AS positive_rate_cnt
          FROM {TABLE}
          WHERE jq_date='2026-08-12' AND str_type='new'
            AND CAST(jq_credit_quota AS DOUBLE)>=0 AND CAST(cash_quota_amount_now_after AS DOUBLE)>=0
          GROUP BY cashloan_cid_mob_type,te_flag
          ORDER BY cashloan_cid_mob_type,te_flag
        """,
        "te0_positive_config_by_score": f"""
          SELECT jq_mix_score_bin, COUNT(1) AS cnt,
            SUM(CAST(jq_credit_quota AS DOUBLE)) AS before_sum_cent,
            AVG(CAST(cash_remark1 AS DOUBLE)) AS avg_configured_rate
          FROM {TABLE}
          WHERE jq_date='2026-08-12' AND str_type='new' AND te_flag=0
            AND CAST(jq_credit_quota AS DOUBLE)>=0 AND CAST(cash_quota_amount_now_after AS DOUBLE)>=0
            AND CAST(cash_remark1 AS DOUBLE)>0
          GROUP BY jq_mix_score_bin
          ORDER BY jq_mix_score_bin
        """,
        "rate_and_te_flag": f"""
          SELECT cash_remark1, te_flag, COUNT(1) AS cnt,
            SUM(CAST(jq_credit_quota AS DOUBLE)) AS before_sum_cent,
            SUM(CAST(cash_quota_amount_now_after AS DOUBLE)) AS after_sum_cent
          FROM {TABLE}
          WHERE jq_date='2026-08-12' AND str_type='new'
            AND CAST(jq_credit_quota AS DOUBLE)>=0 AND CAST(cash_quota_amount_now_after AS DOUBLE)>=0
          GROUP BY cash_remark1,te_flag
          ORDER BY te_flag,cash_remark1
        """,
    }
    out = {name: query(odps, sql) for name, sql in queries.items()}
    OUTPUT.write_text(json.dumps(out, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    print(f"Wrote {OUTPUT}")


if __name__ == "__main__":
    main()
