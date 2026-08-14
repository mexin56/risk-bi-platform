# -*- coding: utf-8 -*-
"""按 315 格策略表逐行拆解 20260813 结清交易数据 + 新旧策略对比"""
import pandas as pd, warnings
warnings.filterwarnings("ignore")
from openpyxl import load_workbook
from openpyxl.styles import Font, PatternFill, Alignment
from openpyxl.utils import get_column_letter
from probe_flexi_cash_strategy import get_odps, query
from analyze_deployed_coefficient import lookup_key, normalized_code

# 1. 读策略表(315 格)
POL = pd.read_excel(r"C:/Users/PP-2026070302/Desktop/策略表和字典.xlsx", sheet_name="Sheet1")
POL.columns = ["jq_customer_flag","defq_use_rate_level","separate_installment_loan_cnt","jq_mix_score_bin","目标提幅"]
POL["key"] = POL.apply(lambda r: (str(r["jq_customer_flag"]).strip(), str(r["defq_use_rate_level"]).strip(), int(float(r["separate_installment_loan_cnt"])), str(r["jq_mix_score_bin"]).strip()), axis=1)
policy = dict(zip(POL["key"], POL["目标提幅"]))

# 2. 拉线上 8/13 全量(new + old)
sql = """
SELECT str_type, jq_customer_flag, defq_use_rate_level, separate_installment_loan_cnt,
       jq_mix_score_bin, cash_remark1, te_flag,
       COUNT(1) AS cnt,
       SUM(CAST(jq_credit_quota AS DOUBLE)) AS before_sum,
       SUM(CAST(cash_quota_amount_now_after AS DOUBLE)) AS after_sum,
       SUM(CAST(loan_amount AS DOUBLE)) AS loan_sum,
       SUM(CAST(loan_prin AS DOUBLE)) AS next_prin_sum,
       SUM(CASE WHEN CAST(next_loan_flag AS BIGINT)=1 THEN 1 ELSE 0 END) AS next_loan_cnt,
       SUM(CASE WHEN CAST(next_curday_flag AS BIGINT)=1 THEN 1 ELSE 0 END) AS t0_cnt,
       SUM(CASE WHEN CAST(cash_quota_amount_now_after AS DOUBLE) > CAST(jq_credit_quota AS DOUBLE) THEN 1 ELSE 0 END) AS actual_raise,
       SUM(CASE WHEN CAST(cash_quota_amount_now_after AS DOUBLE) = CAST(jq_credit_quota AS DOUBLE) THEN 1 ELSE 0 END) AS actual_unchanged
FROM pb_biz_credit.flexi_cash_jq_result_v1
WHERE jq_date='2026-08-13'
  AND CAST(jq_credit_quota AS DOUBLE) >= 0 AND CAST(cash_quota_amount_now_after AS DOUBLE) >= 0
GROUP BY str_type, jq_customer_flag, defq_use_rate_level, separate_installment_loan_cnt,
         jq_mix_score_bin, cash_remark1, te_flag
"""
odps = get_odps()
rows = query(odps, sql)
df = pd.DataFrame(rows)
for c in ["cnt","before_sum","after_sum","loan_sum","next_prin_sum","next_loan_cnt","t0_cnt","actual_raise","actual_unchanged"]:
    df[c] = pd.to_numeric(df[c], errors="coerce").fillna(0)
df["key"] = df.apply(lambda r: lookup_key(str(r["jq_customer_flag"]), str(r["defq_use_rate_level"]), int(r["separate_installment_loan_cnt"]), str(r["jq_mix_score_bin"])), axis=1)
# 验证 key 与策略表匹配
matched = df["key"].isin(policy.keys()).sum()
print(f"线上行 key 匹配策略表: {matched}/{len(df)}")

# 3. 逐格聚合函数
def cell_table(sub):
    agg = {}
    for k, g in sub.groupby("key"):
        n = int(g["cnt"].sum()); nl = int(g["next_loan_cnt"].sum())
        r = g[g["te_flag"].astype(str) == "1"]
        nr = g[g["te_flag"].astype(str) == "0"]
        rn = int(r["cnt"].sum()) if len(r) else 0
        nrn = int(nr["cnt"].sum()) if len(nr) else 0
        r_before = r["before_sum"].sum() if len(r) else 0
        r_after = r["after_sum"].sum() if len(r) else 0
        # 系数一致: te_flag=1 且 cash_remark1 == 目标提幅
        cm = 0; ctotal = 0
        for _, row in r.iterrows():
            ctotal += int(row["cnt"])
            exp = policy.get(k)
            if exp is not None and row["cash_remark1"] is not None and abs(float(row["cash_remark1"]) - float(exp)) < 1e-9:
                cm += int(row["cnt"])
        agg[k] = dict(
            结清客户=n, 提额客户=rn, 未提额客户=nrn, 提额覆盖率=rn/n if n else None,
            提额客户提额前均额=r_before/rn/100 if rn else None, 提额客户提额后均额=r_after/rn/100 if rn else None,
            提额客户实际提幅=r_after/r_before-1 if r_before else None,
            系数一致客户=cm, 系数一致率=cm/ctotal if ctotal else None,
            下一笔发起率=nl/n if n else None, 全员人均下一笔金额=g["next_prin_sum"].sum()/n if n else None,
            平均放款=g["loan_sum"].sum()/n/100 if n else None,
            T0发起率=g["t0_cnt"].sum()/n if n else None,
            实际提额率=r["actual_raise"].sum()/rn if rn else None,
        )
    return agg

def build(agg, sheet_name, wb):
    ws = wb.create_sheet(sheet_name)
    headers = ["策略格"] + list(POL.columns[:4]) + ["目标提幅"] + [h for h in next(iter(agg.values())).keys()] if agg else []
    # 简化: 直接按策略表 315 行输出
    ws.append(["jq_customer_flag","defq_use_rate_level","借款次数","jq_mix_score_bin","目标提幅",
               "结清客户","提额客户","未提额客户","提额覆盖率","提额客户提额前均额(元)","提额客户提额后均额(元)","提额客户实际提幅",
               "系数一致客户","系数一致率","下一笔发起率","全员人均下一笔金额(元)","平均放款(元)","T0发起率","实际提额率"])
    for key, row in POL.iterrows():
        k = (str(row["jq_customer_flag"]).strip(), str(row["defq_use_rate_level"]).strip(), int(float(row["separate_installment_loan_cnt"])), str(row["jq_mix_score_bin"]).strip())
        a = agg.get(k)
        ws.append([k[0], k[1], k[2], k[3], float(row["目标提幅"])] + ([
            a["结清客户"], a["提额客户"], a["未提额客户"], a["提额覆盖率"], a["提额客户提额前均额"], a["提额客户提额后均额"], a["提额客户实际提幅"],
            a["系数一致客户"], a["系数一致率"], a["下一笔发起率"], a["全员人均下一笔金额"], a["平均放款"], a["T0发起率"], a["实际提额率"],
        ] if a else [None]*14))
    # 汇总行
    ws.append(["合计","","","",""] + [None]*14)
    navy = "1F4E78"
    for cell in ws[1]:
        cell.font = Font(bold=True, color="FFFFFF"); cell.fill = PatternFill("solid", fgColor=navy); cell.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
    ws.freeze_panes = "A2"
    for col in range(1, ws.max_column+1):
        ws.column_dimensions[get_column_letter(col)].width = 15
    ws.column_dimensions["A"].width = 16
    ws.column_dimensions["B"].width = 14
    return ws

wb = load_workbook(r"C:/Users/PP-2026070302/Desktop/策略表和字典.xlsx")
# 移除默认 sheet 保留策略表
new_df = df[df["str_type"] == "new"]
old_df = df[df["str_type"] == "old"]
agg_new = cell_table(new_df)
agg_old = cell_table(old_df)
if "Sheet1" in wb.sheetnames: wb.remove(wb["Sheet1"])
if "策略表和字典" in wb.sheetnames: wb.remove(wb["策略表和字典"])
build(agg_new, "新策略new_逐格", wb)
build(agg_old, "旧策略old_逐格", wb)
out = "risk_analysis/策略逐格分析_20260813.xlsx"
wb.save(out)
print("Wrote", out)
import json
json.dump({"new": {str(k): v for k, v in agg_new.items()}, "old": {str(k): v for k, v in agg_old.items()}},
          open("risk_analysis/cell_analysis_0813.json", "w", encoding="utf-8"), ensure_ascii=False, indent=1, default=str)
print("Wrote json")
