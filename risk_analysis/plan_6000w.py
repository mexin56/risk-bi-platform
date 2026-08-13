"""每日新增额度 6000 万方案设计
基于 Sheet2(最优分箱, 全部时间, 最优模型行), 对每个客群的所有 bin 按风险比分档提额:
  Tier1: 风险比 < 0.25  → 提额 +50%
  Tier2: 0.25 <= 风险比 < 0.5 → +30%
  Tier3: 0.5  <= 风险比 < 0.8 → +15%
  Tier4: 风险比 >= 0.8 或 无数据 → 不提额
扫描渗透率, 找到达标 6000万/天 的推荐配置
"""
import warnings; warnings.filterwarnings("ignore")
import pandas as pd, numpy as np, os

OUT_DIR = "/data2/jupyter-wenning/strage"
XL = os.path.join(OUT_DIR, "短账龄客户-模型效果与提额策略分析-20260807_2343.xlsx")
SPAN_DAYS = 105                      # 数据跨度(2026-04-27 ~ 08-10)
TARGET_DAILY = 6000                  # 目标: 日均新增 6000 万

# 分层提额规则(风险比 = bin fpd7_dd / 客群 fpd7_dd)
TIERS = [
    ("Tier1_超低风险",  0.25, 0.50),
    ("Tier2_低风险",    0.50, 0.30),
    ("Tier3_中低风险",  0.80, 0.15),
]

# ---- 1. 数据: Sheet2 全部时间 + 最优模型行 ----
s2 = pd.read_excel(XL, sheet_name="最优分箱")
s2 = s2[(s2["loan_week_begin"] == "全部") & (s2["是否最优模型"] == "最优模型")].copy()
print(f"最优模型 bin 行数: {len(s2):,}")

def tier_ratio(r):
    if pd.isna(r):
        return 0.0
    for _, cap, ratio in TIERS:
        if r < cap:
            return ratio
    return 0.0

s2["提额比率"] = s2["fpd7_dd_lift"].apply(tier_ratio)
s2["bin借款金额"] = s2["结清借款金额"]
s2["新增借款100%"] = s2["bin借款金额"] * s2["提额比率"]
s2["bin逾期率"] = s2["fpd7_dd"]

# ---- 2. 分层总览 ----
print("\n================ 分层提额方案总览(100% 渗透) ================")
for name, cap, ratio in TIERS:
    sub = s2[s2["fpd7_dd_lift"] < cap] if name == TIERS[0][0] else \
          s2[(s2["fpd7_dd_lift"] >= TIERS[TIERS.index((name, cap, ratio))-1][1]) & (s2["fpd7_dd_lift"] < cap)]
    # 更稳妥: 直接按比率分组
    sub = s2[s2["提额比率"] == ratio]
    new_amt = sub["新增借款100%"].sum()
    new_dd = (sub["bin借款金额"] * sub["bin逾期率"]).sum() / sub["bin借款金额"].sum() if sub["bin借款金额"].sum() > 0 else np.nan
    print(f"  {name:<14} 提额+{ratio*100:.0f}% | bin数 {len(sub):>5,} | 客户数 {sub['cnt'].sum():>8,} | "
          f"当前借款 {sub['bin借款金额'].sum()/1e4:>9,.0f} 万 | 新增 {new_amt/1e4:>8,.0f} 万 | 新增逾期率 {new_dd*100:.2f}%")

tot_new = s2["新增借款100%"].sum()
tot_dd_new = (s2["bin借款金额"] * s2["bin逾期率"]).sum() / s2["bin借款金额"].sum()
print(f"  合计: 新增潜力 {tot_new/1e4:,.0f} 万 (日均 {tot_new/SPAN_DAYS/1e4:,.0f} 万) | 覆盖客户 {s2['cnt'].sum():,} | 加权新增逾期率 {tot_dd_new*100:.2f}%")

# ---- 3. 渗透率扫描 ----
print("\n================ 渗透率敏感性(达标判定) ================")
print(f"目标: 日均新增 {TARGET_DAILY:,} 万")
for pen in [0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 1.0]:
    daily = tot_new * pen / SPAN_DAYS / 1e4
    flag = "✅ 达标" if daily >= TARGET_DAILY else ""
    print(f"  渗透率 {pen*100:.0f}%: 日均新增 {daily:,.0f} 万 | 月均 {daily*30:,.0f} 万 {flag}")

# ---- 4. 达标配置: 按风险比阈值扩展覆盖 ----
print("\n================ 达标配置扫描(固定渗透率 50%) ================")
for cap_r in [0.25, 0.5, 0.8, 1.0]:
    sub = s2[s2["fpd7_dd_lift"] < cap_r]
    new = sub["bin借款金额"].sum() * 0.5 / SPAN_DAYS / 1e4 * 1.0  # 简化: 全部按+50%? 不, 用实际比率
    new = (sub["bin借款金额"] * sub["提额比率"]).sum() * 0.5 / SPAN_DAYS / 1e4
    print(f"  覆盖风险比<{cap_r}: 日均新增 {new:,.0f} 万 {'✅' if new >= TARGET_DAILY else ''}")

# ---- 5. 输出方案 Excel ----
out = s2[["loan_ser_node", "flag_customer", "loan_cnt_detal_group", "credit_use_type",
          "模型", "bin区间", "cnt", "bin借款金额", "fpd7_dd", "fpd7_dd_lift",
          "提额比率", "新增借款100%"]].copy()
out["层"] = out["提额比率"].map({0.5: "Tier1_超低风险", 0.3: "Tier2_低风险", 0.15: "Tier3_中低风险", 0.0: "不提额"})
out = out.sort_values(["层", "新增借款100%"], ascending=[True, False])

out_path = os.path.join(OUT_DIR, "提额6000万方案明细-20260807.xlsx")
with pd.ExcelWriter(out_path, engine="openpyxl") as w:
    out.to_excel(w, sheet_name="方案明细", index=False)
print(f"\n✅ 方案明细已保存: {out_path} ({len(out):,} 行)")
