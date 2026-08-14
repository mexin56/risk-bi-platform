# -*- coding: utf-8 -*-
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

# 10档差异化: (边界, 放大系数, 档名)
TIERS = [
    (0.02, 5.0, "T1_<2%"), (0.04, 4.0, "T2_2-4%"), (0.06, 3.0, "T3_4-6%"),
    (0.08, 2.5, "T4_6-8%"), (0.10, 2.0, "T5_8-10%"), (0.15, 1.5, "T6_10-15%"),
    (0.20, 1.2, "T7_15-20%"), (0.25, 1.0, "T8_20-25%"), (0.30, 0.7, "T9_25-30%"),
    (np.inf, 0.5, "T10_>=30%"),
]
def mf(f):
    for cap, m, _ in TIERS:
        if f < cap:
            return m
    return 0.5
def tf(f):
    for cap, _, n in TIERS:
        if f < cap:
            return n
    return "T10_>=30%"
df["m"] = df["fpd7_rate$"].apply(mf)
df["档"] = df["fpd7_rate$"].apply(tf)
cap_amp = np.minimum(80000/df["平均额度"], 500000/df["平均额度"]-1).clip(lower=0)
df["cap_amp"] = cap_amp

def inc_of(k=1.0):
    amp = np.where(ok, cap_amp*df["m"]*k, 0.0)
    np_ = df["提额客户_平均额度"]*(1+amp)
    return df["提额客户"]*np.maximum(0, np_-df["提额客户_平均额度"])

raw = inc_of(1.0)
print(f"需新增 {need/1e8:.2f} 亿")
print(f"10档差异化不缩放: {raw.sum()/1e8:.2f} 亿 | 平均 {(cur+raw.sum())/N:,.0f}")
k = 1.0
if raw.sum() >= need:
    lo, hi = 0.2, 1.0
    for _ in range(80):
        mid=(lo+hi)/2
        if inc_of(mid).sum() > need: hi = mid
        else: lo = mid
    k=(lo+hi)/2
    inc=inc_of(k)
    print(f"差异化×{k:.3f}: {inc.sum()/1e8:.2f} 亿 | 平均 {(cur+inc.sum())/N:,.0f} ✅")

amp = np.where(ok, cap_amp*df["m"]*k, 0.0)
df["amp"] = amp
order = [t[2] for t in TIERS]
g = df[ok].groupby("档").apply(lambda x: pd.Series({
    "放大系数": x["m"].iloc[0],
    "客群数": len(x),
    "提额客户数": int(x["提额客户"].sum()),
    "提幅上限幅度%": round((x["提额客户"]*x["cap_amp"]).sum()/x["提额客户"].sum()*100, 0),
    "方案A幅度%": round((x["提额客户"]*x["amp"]).sum()/x["提额客户"].sum()*100, 0),
    "方案A新增(万)": round((x["提额客户"]*np.maximum(0, x["提额客户_平均额度"]*(1+x["amp"])-x["提额客户_平均额度"])).sum()/1e4, 0),
    "fpd7_rate$加权%": round((x["结清客户"]*x["平均额度"]*x["fpd7_rate$"]).sum()/(x["结清客户"]*x["平均额度"]).sum()*100, 2),
}), include_groups=False).reset_index()
g["档"] = pd.Categorical(g["档"], categories=order, ordered=True)
print(g.sort_values("档").to_string(index=False))
