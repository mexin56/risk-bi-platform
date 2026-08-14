# -*- coding: utf-8 -*-
"""PDL 方案测算: 提幅按 fpd7_rate$ 风险分档直接给定(封顶300%, 单调递减, 高风险不提)"""
import pandas as pd, numpy as np
p = "/data2/jupyter-wenning/strage/PDL提额系数20260814.xlsx"
df = pd.read_excel(p, sheet_name=0)
cols, seen = [], {}
for c in df.columns:
    s = str(c).strip(); seen[s] = seen.get(s, 0) + 1
    cols.append(s if seen[s] == 1 else f"{s}_数值")
df.columns = cols
df = df[df["flag_customer"] != "总计"].reset_index(drop=True)
ok = df["评级"].isin(["A","B","C"])
N = df["结清客户"].sum()
cur = (df["结清客户"]*df["平均额度"]).sum()
need = 50000*N - cur
print(f"结清客户 {N:,} | 当前平均 {cur/N:,.0f} | 目标5万需新增 {need/1e8:.2f} 亿")

# 方案V1: 10档直接给定提幅, 300%封顶, 单调递减, 高风险0%
TIERS = [
    (0.02, 3.00, "T1_<2%"), (0.04, 2.60, "T2_2-4%"), (0.06, 2.20, "T3_4-6%"),
    (0.08, 1.80, "T4_6-8%"), (0.10, 1.50, "T5_8-10%"), (0.15, 1.20, "T6_10-15%"),
    (0.20, 0.90, "T7_15-20%"), (0.25, 0.60, "T8_20-25%"), (0.30, 0.30, "T9_25-30%"),
    (np.inf, 0.00, "T10_>=30%"),
]
def amp_of(f):
    for cap, a, _ in TIERS:
        if f < cap:
            return a
    return 0.0
def tier_of(f):
    for cap, _, n in TIERS:
        if f < cap:
            return n
    return "T10_>=30%"

df["档"] = df["fpd7_rate$"].apply(tier_of)
df["基础提幅"] = df["fpd7_rate$"].apply(amp_of)

def inc_of(k=1.0):
    amp = np.where(ok, df["基础提幅"] * k, 0.0)
    np_ = np.minimum(df["提额客户_平均额度"] * (1 + amp), 500000)
    return df["提额客户"] * np.maximum(0, np_ - df["提额客户_平均额度"])

raw = inc_of(1.0)
print(f"\nV1档位潜力(不缩放): {raw.sum()/1e8:.2f} 亿 | 平均 {(cur+raw.sum())/N:,.0f}")
if raw.sum() >= need:
    lo, hi = 0.2, 1.0
    for _ in range(80):
        mid = (lo+hi)/2
        if inc_of(mid).sum() > need:
            hi = mid
        else:
            lo = mid
    k = (lo+hi)/2
    inc = inc_of(k)
    print(f"缩放×{k:.3f}: {inc.sum()/1e8:.2f} 亿 | 平均 {(cur+inc.sum())/N:,.0f} ✅")
else:
    k = 1.0
    print(f"❌ 潜力不足, 需上调档位 (缺口 {(need-raw.sum())/1e8:.2f} 亿)")

# 各档效果
df["amp"] = np.where(ok, df["基础提幅"] * k, 0.0)
order = [t[2] for t in TIERS]
g = df[ok].groupby("档").apply(lambda x: pd.Series({
    "客群数": len(x), "提额客户数": int(x["提额客户"].sum()),
    "提幅上限%": round(x["基础提幅"].iloc[0]*100, 0),
    "方案幅度%": round((x["提额客户"]*x["amp"]).sum()/x["提额客户"].sum()*100, 0),
    "新增(万)": round((x["提额客户"]*np.maximum(0, x["提额客户_平均额度"]*(1+x["amp"])-x["提额客户_平均额度"])).sum()/1e4, 0),
    "fpd7_rate$加权%": round((x["结清客户"]*x["平均额度"]*x["fpd7_rate$"]).sum()/(x["结清客户"]*x["平均额度"]).sum()*100, 2),
}), include_groups=False).reset_index()
g["档"] = pd.Categorical(g["档"], categories=order, ordered=True)
print("\n各档效果:")
print(g.sort_values("档").to_string(index=False))

# fpd7 变化
amt_after = df["结清客户"]*df["平均额度"] + inc
fpd7s = (amt_after*df["fpd7_rate$"]).sum()/amt_after.sum()
cur_fpd7s = (df["结清客户"]*df["平均额度"]*df["fpd7_rate$"]).sum()/cur
print(f"\n整体fpd7_rate$: {cur_fpd7s*100:.2f}% → {fpd7s*100:.2f}% (降 {(cur_fpd7s-fpd7s)*100:.2f}pp)")
