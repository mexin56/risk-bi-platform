"""提额策略影响预估: 规模扩大多少 / 风险降低多少
口径:
- 现状基线: 全量客户(剔除 -1 标签后), 分群2客群级 借款金额/件均/逾期率(fpd7_dd)
- 提额增量: Sheet4 中每个客群的最优模型最优bin, 新增借款 = bin件均 × bin样本数 × 提额比率 × 渗透率
- 组合风险: 加权逾期率 = Σ(借款金额×fpd7_dd)/Σ借款金额, 对比提额前后
"""
import warnings; warnings.filterwarnings("ignore")
import pandas as pd, numpy as np, time, os

OUT_DIR = "/data2/jupyter-wenning/strage"
XL = os.path.join(OUT_DIR, "短账龄客户-模型效果与提额策略分析-20260807_2343.xlsx")
CSV = "/data2/jupyter-wenning/strage/ng_pdl_ins_cashjq_analysic.csv"
KEYS2 = ["loan_ser_node", "flag_customer", "loan_cnt_detal_group", "credit_use_type"]
PENETRATION = [0.3, 0.5, 1.0]   # 渗透率敏感性: 提额后实际支用比例(保守/中性/乐观)

# ---- 1. 提额建议(Sheet4) ----
s4 = pd.read_excel(XL, sheet_name="提额建议")
print(f"Sheet4 提额客群: {len(s4)} 个")

# ---- 2. 现状基线(全量客户, 分群2客群级) ----
t0 = time.time()
df = pd.read_csv(CSV, low_memory=False, usecols=KEYS2 + ["curr_loan_prin", "fpd7_fz_dd", "fpd7_fm_dd", "loan_week_begin", "flag"])
df = df[df["flag"].astype(str) != "-1"]
df = df[df["credit_use_type"].astype(str) != "-1"]
print(f"全量样本: {len(df):,} ({time.time()-t0:.0f}s)")

# 数据时间跨度(loan_week_begin 为每周起点, 覆盖到该周结束)
wk_min, wk_max = pd.to_datetime(df["loan_week_begin"]).min(), pd.to_datetime(df["loan_week_begin"]).max()
SPAN_DAYS = (wk_max - wk_min).days + 7
print(f"数据时间范围: {wk_min.date()} ~ {(wk_max + pd.Timedelta(days=7)).date()}  (共 {SPAN_DAYS} 天 / 约 {SPAN_DAYS/30:.1f} 个月)")

g = df.groupby(KEYS2, observed=True, sort=False)
base = pd.DataFrame({
    "客群样本数全量": g.size(),
    "客群借款金额全量": g["curr_loan_prin"].sum(),
    "客群fpd7_dd全量": g["fpd7_fz_dd"].sum() / g["fpd7_fm_dd"].sum(),
}).reset_index()
base["客群件均全量"] = base["客群借款金额全量"] / base["客群样本数全量"]

# ---- 3. 合并: 每个提额客群的 bin 增量 ----
m = s4.merge(base, on=KEYS2, how="left")
m["bin借款金额"] = m["bin件均"] * m["bin样本数"]          # bin 内借款金额
m["bin新增借款"] = m["bin借款金额"] * m["建议提额比率"]   # 100% 渗透下的新增

# ---- 4. 全局汇总 ----
tot_amt   = base["客群借款金额全量"].sum()                 # 现状总借款金额
tot_dd    = (base["客群借款金额全量"] * base["客群fpd7_dd全量"]).sum() / tot_amt   # 现状加权逾期率
tot_cnt   = base["客群样本数全量"].sum()
up_cnt    = m["bin样本数"].sum()                          # 可提额客户数
up_amt    = m["bin新增借款"].sum()                        # 新增借款(100%渗透)
up_dd     = (m["bin借款金额"] * m["bin_fpd7_dd"]).sum() / m["bin借款金额"].sum()  # 新增借款的逾期率

print("\n================ 现状基线 ================")
print(f"全量客户: {tot_cnt:,}")
print(f"总借款金额: {tot_amt/1e8:.2f} 亿")
print(f"日均借款金额: {tot_amt/SPAN_DAYS/1e4:.1f} 万/天  |  月均: {tot_amt/SPAN_DAYS*30/1e4:.1f} 万/月")
print(f"加权逾期率(fpd7_dd): {tot_dd*100:.2f}%")

print("\n================ 可提额客群(bin) ================")
print(f"可提额客户数: {up_cnt:,} (占比 {up_cnt/tot_cnt*100:.1f}%)")
print(f"可提额客户当前借款: {m['bin借款金额'].sum()/1e8:.2f} 亿")
print(f"新增借款潜力(100%渗透): {up_amt/1e8:.2f} 亿")
print(f"新增借款的逾期率: {up_dd*100:.2f}% (现状 {tot_dd*100:.2f}%)")

print("\n================ 渗透率敏感性(日/月规模) ================")
rows = []
for pen in PENETRATION:
    new_amt = up_amt * pen
    mix_dd = (tot_amt * tot_dd + new_amt * up_dd) / (tot_amt + new_amt)
    scale_up = new_amt / tot_amt * 100
    risk_drop_pp = (tot_dd - mix_dd) * 100
    risk_drop_pct = (tot_dd - mix_dd) / tot_dd * 100
    rows.append({
        "渗透率": f"{pen*100:.0f}%",
        "新增借款金额(万)": round(new_amt / 1e4, 1),
        "规模增幅": f"{scale_up:.2f}%",
        "新增日均(万/天)": round(new_amt / SPAN_DAYS / 1e4, 1),
        "新增月均(万/月)": round(new_amt / SPAN_DAYS * 30 / 1e4, 1),
        "提额后日均(万/天)": round((tot_amt + new_amt) / SPAN_DAYS / 1e4, 1),
        "提额后月均(万/月)": round((tot_amt + new_amt) / SPAN_DAYS * 30 / 1e4, 1),
        "提额后组合逾期率": f"{mix_dd*100:.2f}%",
        "风险降低(pp)": f"{risk_drop_pp:.2f}pp",
        "风险相对降幅": f"{risk_drop_pct:.1f}%",
    })
    print(f"  渗透率 {pen*100:.0f}%: 新增 {new_amt/1e8:.2f} 亿 (规模 +{scale_up:.2f}%) | "
          f"日均 {new_amt/SPAN_DAYS/1e4:.1f}万 / 月均 {new_amt/SPAN_DAYS*30/1e4:.1f}万 | "
          f"组合逾期率 {mix_dd*100:.2f}% (降 {risk_drop_pp:.2f}pp / {risk_drop_pct:.1f}%)")
sens = pd.DataFrame(rows)

# ---- 5. 分客群明细 + 输出 Excel ----
detail = m[KEYS2 + ["最优模型", "最优bin", "bin样本数", "bin件均", "客群件均",
                    "bin_fpd7_dd", "客群_fpd7_dd", "风险比", "建议提额比率",
                    "bin借款金额", "bin新增借款", "客群借款金额全量", "客群fpd7_dd全量"]].copy()
detail["件均提升"] = detail["客群件均"] * detail["建议提额比率"]
detail = detail.sort_values("bin新增借款", ascending=False)

summary = pd.DataFrame([{
    "指标": "现状总借款金额(亿)", "值": round(tot_amt / 1e8, 2),
    "指标": "现状加权逾期率", "值": f"{tot_dd*100:.2f}%",
}])

out_path = os.path.join(OUT_DIR, "提额影响评估-20260807.xlsx")
with pd.ExcelWriter(out_path, engine="openpyxl") as w:
    sens.to_excel(w, sheet_name="总体影响", index=False)
    detail.to_excel(w, sheet_name="分客群明细", index=False)
print(f"\n✅ 评估结果已保存: {out_path}")
print(f"   Sheet[总体影响]: 渗透率敏感性(含日/月口径)  |  Sheet[分客群明细]: {len(detail)} 个提额客群")
