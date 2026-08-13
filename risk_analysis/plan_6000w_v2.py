"""每日新增 6000 万提额方案引擎 v2
网格扫描: 覆盖阈值(风险比) × 分层提额比率 × 渗透率
约束: 日均新增 >= 6000 万, 且 加权新增逾期率 <= 8%(质量红线)
输出: 达标组合表 + 推荐方案 + 方案明细
"""
import warnings; warnings.filterwarnings("ignore")
import pandas as pd, numpy as np, os

OUT_DIR = "/data2/jupyter-wenning/strage"
XL = os.path.join(OUT_DIR, "短账龄客户-模型效果与提额策略分析-20260807_2343.xlsx")
SPAN_DAYS = 105
TARGET_DAILY = 6000      # 万/天
MAX_NEW_DD = 0.08        # 新增借款加权逾期率红线

# 分层边界(风险比)
TIER_CAPS = [0.25, 0.50]          # 前两档固定, 第三档 = 覆盖阈值
# 比率方案: [Tier1, Tier2, Tier3]
RATIO_PLANS = {
    "S1_温和":   [0.50, 0.30, 0.15],
    "S2_进取":   [0.60, 0.40, 0.20],
    "S3_积极":   [0.70, 0.50, 0.25],
    "S4_优选":   [0.80, 0.40, 0.15],
}
COVERS = [0.50, 0.65, 0.80]
PENS = [0.50, 0.55, 0.60, 0.65, 0.70, 0.75, 0.80]

# ---- 数据 ----
s2 = pd.read_excel(XL, sheet_name="最优分箱")
s2 = s2[(s2["loan_week_begin"] == "全部") & (s2["是否最优模型"] == "最优模型")].copy()
s2["bin借款金额"] = s2["结清借款金额"]
s2["bin逾期率"] = s2["fpd7_dd"]
lift = s2["fpd7_dd_lift"]

def calc_daily(cover, ratios, pen):
    """给定覆盖阈值/比率方案/渗透率 → (日均新增万, 加权新增逾期率, 覆盖客户数)"""
    mask = lift < cover
    sub = s2[mask].copy()
    r = sub["fpd7_dd_lift"]
    ratio = np.select(
        [r < TIER_CAPS[0], r < TIER_CAPS[1], r < cover],
        ratios, default=0.0)
    sub["新增"] = sub["bin借款金额"] * ratio * pen
    amt = sub["bin借款金额"].sum()
    new_dd = (sub["bin借款金额"] * sub["bin逾期率"]).sum() / amt if amt > 0 else np.nan
    return sub["新增"].sum() / SPAN_DAYS / 1e4, new_dd, int(sub["cnt"].sum())

# ---- 网格扫描 ----
results = []
for cover in COVERS:
    for pname, ratios in RATIO_PLANS.items():
        for pen in PENS:
            daily, new_dd, cust = calc_daily(cover, ratios, pen)
            results.append({
                "覆盖阈值": cover, "比率方案": pname,
                "Tier比率": f"{int(ratios[0]*100)}/{int(ratios[1]*100)}/{int(ratios[2]*100)}",
                "渗透率": pen, "日均新增(万)": round(daily, 0),
                "月均新增(万)": round(daily * 30, 0), "规模增幅%": round(daily / 47630 * 100, 2),
                "新增逾期率%": round(new_dd * 100, 2) if new_dd == new_dd else np.nan,
                "覆盖客户数": cust, "达标": daily >= TARGET_DAILY and new_dd <= MAX_NEW_DD,
            })
res = pd.DataFrame(results)
hit = res[res["达标"]].sort_values(["新增逾期率%", "日均新增(万)"], ascending=[True, False])
print(f"===== 达标组合(日均≥{TARGET_DAILY}万 且 新增逾期率≤{MAX_NEW_DD*100:.0f}%) 共 {len(hit)} 个 =====")
print(hit.head(12).to_string(index=False))

# ---- 推荐方案(按 新增逾期率 最低且日均最高) ----
if not hit.empty:
    best = hit.iloc[0]
    print(f"\n===== 推荐方案 =====")
    print(best.to_string())
    cover, pname, pen = best["覆盖阈值"], best["比率方案"], best["渗透率"]
    ratios = RATIO_PLANS[pname]
    daily, new_dd, cust = calc_daily(cover, ratios, pen)

    # 推荐方案明细
    mask = s2["fpd7_dd_lift"] < cover
    sub = s2[mask].copy()
    r = sub["fpd7_dd_lift"]
    sub["层"] = np.select([r < TIER_CAPS[0], r < TIER_CAPS[1], r < cover],
                          ["Tier1_超低风险", "Tier2_低风险", "Tier3_中低风险"], default="不提额")
    sub["提额比率"] = np.select([r < TIER_CAPS[0], r < TIER_CAPS[1], r < cover], ratios, default=0.0)
    sub["日均新增(万)"] = sub["bin借款金额"] * sub["提额比率"] * pen / SPAN_DAYS / 1e4
    out = sub[["loan_ser_node", "flag_customer", "loan_cnt_detal_group", "credit_use_type",
               "模型", "bin区间", "层", "提额比率", "cnt", "bin借款金额",
               "bin逾期率", "fpd7_dd_lift", "日均新增(万)"]].sort_values(
        ["层", "日均新增(万)"], ascending=[True, False])
    out_path = os.path.join(OUT_DIR, "提额6000万方案-推荐配置-20260807.xlsx")
    with pd.ExcelWriter(out_path, engine="openpyxl") as w:
        best.to_frame().T.to_excel(w, sheet_name="推荐配置", index=False)
        out.to_excel(w, sheet_name="方案明细", index=False)
    print(f"\n✅ 推荐方案明细已保存: {out_path} ({len(out):,} 行)")
else:
    print("\n⚠️ 无达标组合, 需提高比率或降低质量红线")
