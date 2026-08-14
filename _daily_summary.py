# -*- coding: utf-8 -*-
"""按结清日期汇总统计(8/8-8/13), 输出 daily_summary_0813.json"""
import json
from probe_flexi_cash_strategy import get_odps, query

odps = get_odps()
sql = """
SELECT jq_date,
  COUNT(1) AS cnt,
  SUM(CAST(jq_credit_quota AS DOUBLE)) AS before_sum,
  SUM(CAST(cash_quota_amount_now_after AS DOUBLE)) AS after_sum,
  SUM(CAST(loan_amount AS DOUBLE)) AS loan_sum,
  SUM(CASE WHEN CAST(te_flag AS BIGINT)=1 THEN 1 ELSE 0 END) AS raised_cnt,
  SUM(CASE WHEN CAST(te_flag AS BIGINT)=1 THEN CAST(jq_credit_quota AS DOUBLE) ELSE 0 END) AS r_before_sum,
  SUM(CASE WHEN CAST(te_flag AS BIGINT)=1 THEN CAST(cash_quota_amount_now_after AS DOUBLE) ELSE 0 END) AS r_after_sum,
  SUM(CASE WHEN CAST(next_loan_flag AS BIGINT)=1 THEN 1 ELSE 0 END) AS next_cnt,
  SUM(CAST(loan_prin AS DOUBLE)) AS next_prin_sum,
  SUM(CASE WHEN CAST(loan_prin AS DOUBLE) > 0 THEN 1 ELSE 0 END) AS next_prin_cnt,
  AVG(CAST(loan_period_days AS DOUBLE)) AS avg_days,
  AVG(CAST(interest_fee_daily AS DOUBLE)) AS avg_fee,
  SUM(CAST(fpd1_fm_dd AS DOUBLE)) AS fpd1_den_dd, SUM(CAST(fpd1_fz_dd AS DOUBLE)) AS fpd1_num_dd,
  SUM(CAST(fpd1_fm_bj AS DOUBLE)) AS fpd1_den_bj, SUM(CAST(fpd1_fz_bj AS DOUBLE)) AS fpd1_num_bj,
  SUM(CAST(fpd7_fm_dd AS DOUBLE)) AS fpd7_den_dd, SUM(CAST(fpd7_fz_dd AS DOUBLE)) AS fpd7_num_dd,
  SUM(CAST(fpd7_fm_bj AS DOUBLE)) AS fpd7_den_bj, SUM(CAST(fpd7_fz_bj AS DOUBLE)) AS fpd7_num_bj
FROM pb_biz_credit.flexi_cash_jq_result_v1
WHERE jq_date >= '2026-08-08'
  AND CAST(jq_credit_quota AS DOUBLE) >= 0 AND CAST(cash_quota_amount_now_after AS DOUBLE) >= 0
GROUP BY jq_date ORDER BY jq_date
"""
rows = query(odps, sql)
out = {}
for r in rows:
    n = int(r["cnt"]); rc = int(r["raised_cnt"])
    def sd(x, y):
        return x / y if y else None
    out[r["jq_date"]] = {
        "结清客户": n,
        "结清平均额度": round(sd(r["before_sum"], n) / 100, 0),
        "结清平均额度后": round(sd(r["after_sum"], n) / 100, 0),
        "件均": round(sd(r["loan_sum"], n) / 100, 0),
        "额度使用率": round(sd(r["loan_sum"], r["before_sum"]), 4),
        "提额客户": rc,
        "提额客户_平均额度": round(sd(r["r_before_sum"], rc) / 100, 0),
        "提额客户_提额后平均": round(sd(r["r_after_sum"], rc) / 100, 0),
        "发起下一笔订单": int(r["next_prin_cnt"]),  # 与件均同源: loan_prin>0 人数
        "发起下一笔件均": round(sd(r["next_prin_sum"], r["next_prin_cnt"]), 0),  # 仅已发起客户(未发起NULL不计入)
        "平均借款天数": round(r["avg_days"], 1),
        "下一笔日息": round(r["avg_fee"], 2),
        "fpd1_fm_dd": int(r["fpd1_den_dd"]),
        "fpd7_fm_dd": int(r["fpd7_den_dd"]),
        "fpd1_rate$": round(sd(r["fpd1_num_bj"], r["fpd1_den_bj"]), 4),
        "fpd1_rate": round(sd(r["fpd1_num_dd"], r["fpd1_den_dd"]), 4),
        "fpd7_rate$": round(sd(r["fpd7_num_bj"], r["fpd7_den_bj"]), 4),
        "fpd7_rate": round(sd(r["fpd7_num_dd"], r["fpd7_den_dd"]), 4),
    }
json.dump(out, open("risk_analysis/daily_summary_0813.json", "w", encoding="utf-8"), ensure_ascii=False, indent=1)
for d, v in out.items():
    print(d, v)
