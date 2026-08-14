# -*- coding: utf-8 -*-
"""按 风险等级×策略类型×是否提额 统计 8/13 结清提额效果"""
import json
from probe_flexi_cash_strategy import get_odps, query

odps = get_odps()
sql = """
SELECT str_type, jq_mix_score_bin, te_flag,
  COUNT(1) AS cnt,
  SUM(CAST(jq_credit_quota AS DOUBLE)) AS before_sum,
  SUM(CAST(cash_quota_amount_now_after AS DOUBLE)) AS after_sum,
  SUM(CAST(loan_amount AS DOUBLE)) AS loan_sum,
  SUM(CAST(loan_prin AS DOUBLE)) AS next_prin_sum,
  SUM(CASE WHEN CAST(next_loan_flag AS BIGINT)=1 THEN 1 ELSE 0 END) AS next_cnt,
  SUM(CAST(fpd7_fz_dd AS DOUBLE)) AS fpd7_num,
  SUM(CAST(fpd7_fm_dd AS DOUBLE)) AS fpd7_den,
  SUM(CAST(fpd1_fz_dd AS DOUBLE)) AS fpd1_num,
  SUM(CAST(fpd1_fm_dd AS DOUBLE)) AS fpd1_den
FROM pb_biz_credit.flexi_cash_jq_result_v1
WHERE jq_date='2026-08-13'
  AND CAST(jq_credit_quota AS DOUBLE) >= 0 AND CAST(cash_quota_amount_now_after AS DOUBLE) >= 0
GROUP BY str_type, jq_mix_score_bin, te_flag
"""
rows = query(odps, sql)
SCORE = {"5.0": "A", "4.0": "B", "3.0": "C", "2.0": "D", "1.0": "E", "5": "A", "4": "B", "3": "C", "2": "D", "1": "E"}
TE = {"1": "提额客户", "0": "未提额客户", "2": "降额客户"}
out = {}
for r in rows:
    n = int(r["cnt"])
    if n == 0: continue
    score = SCORE.get(str(r["jq_mix_score_bin"]), str(r["jq_mix_score_bin"]))
    key = (str(r["str_type"]), score, TE.get(str(r["te_flag"]), str(r["te_flag"])))
    before = r["before_sum"]/n/100
    after = r["after_sum"]/n/100
    loan = r["loan_sum"]/n/100
    next_cnt = int(r["next_cnt"])
    next_prin = r["next_prin_sum"]/max(next_cnt, 1)   # 元, 仅已发起下一笔客户均值(未发起为NULL不计入)
    out[key] = {
        "客户数": n,
        "提额前平均额度(元)": round(before, 0),
        "提额后平均额度(元)": round(after, 0),
        "额度提升率": round(after/before - 1, 4) if before else None,
        "提额前额度使用率": round(loan/before, 4) if before else None,
        "提额前借款金额(元)": round(loan, 0),
        "提额后借款金额(元)": round(next_prin, 0),
        "提额后额度使用率": round(r["next_prin_sum"]/(r["after_sum"]/100), 4) if r["after_sum"] else None,  # 总额口径: 下一笔总借款/提额后总授信
        "下一笔发起率": round(int(r["next_cnt"])/n, 4),
        "fpd7": round(r["fpd7_num"]/r["fpd7_den"], 4) if r["fpd7_den"] else None,
        "fpd7样本": int(r["fpd7_den"]),
        "fpd1": round(r["fpd1_num"]/r["fpd1_den"], 4) if r["fpd1_den"] else None,
        "fpd1样本": int(r["fpd1_den"]),
    }
json.dump({str(k): v for k, v in out.items()}, open("risk_analysis/effect_framework_0813.json", "w", encoding="utf-8"), ensure_ascii=False, indent=1)
for k, v in sorted(out.items()):
    print(k, v)
