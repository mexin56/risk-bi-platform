# -*- coding: utf-8 -*-
import pandas as pd, numpy as np, itertools
p = "/data2/jupyter-wenning/strage/PDL提额系数20260814.xlsx"
df = pd.read_excel(p, sheet_name=0)
cols, seen = [], {}
for c in df.columns:
    s = str(c).strip(); seen[s] = seen.get(s, 0) + 1
    cols.append(s if seen[s] == 1 else f"{s}_数值")
df.columns = cols
df = df[df["flag_customer"] != "总计"].reset_index(drop=True)
N = df["结清客户"].sum()
cur = (df["结清客户"]*df["平均额度"]).sum()
need = 50000*N - cur
cur_fpd7 = (df["结清客户"]*df["平均额度"]*df["fpd7_rate$"]).sum()/cur
ok = df["评级"].isin(["A","B","C"]) | ((df["评级"]=="D") & (df["fpd7_rate$"] < cur_fpd7))
RISK_COEF = [(0.02,1.0),(0.04,0.95),(0.06,0.9),(0.08,0.85),(0.10,0.8),(0.15,0.7),(0.20,0.6),(0.25,0.5),(0.30,0.4),(np.inf,0.3)]
def rc(f):
    for cap, c in RISK_COEF:
        if f < cap:
            return c
    return 0.3
df["风险系数"] = df["fpd7_rate$"].apply(rc)
df["ok"] = ok

def eval_combo(ub):
    base = np.minimum(df["use_rate_group"].map(ub) * df["风险系数"], 3.0)
    def inc_of(k=1.0):
        amp = np.where(df["ok"], base*k, 0.0)
        np_ = np.minimum(df["提额客户_平均额度"]*(1+amp), df["额度盖帽"])
        return df["提额客户"]*np.maximum(0, np_-df["提额客户_平均额度"])
    raw = inc_of(1.0).sum()
    if raw < need:
        return None
    lo, hi = 0.2, 1.0
    for _ in range(80):
        mid=(lo+hi)/2
        if inc_of(mid).sum() > need: hi = mid
        else: lo = mid
    k=(lo+hi)/2
    inc = inc_of(k)
    by_use = {}
    for u in ["高额度使用率","中额度使用率","低额度使用率"]:
        m2 = df["use_rate_group"]==u
        amp_u = np.where(df["ok"]&m2, base*k, 0.0)
        np_u = np.minimum(df["提额客户_平均额度"]*(1+amp_u), df["额度盖帽"])
        by_use[u] = (df["提额客户"]*np.maximum(0, np_u-df["提额客户_平均额度"])).sum()/1e8
    max_amp = float(np.max(np.where(df["ok"], base*k, 0.0)))
    return k, inc.sum()/1e8, max_amp, by_use

results = []
for H, M, L in itertools.product([240, 260, 280, 300],[200, 220, 240, 260],[60, 70, 80, 90]):
    ub = {"高额度使用率":H/100,"中额度使用率":M/100,"低额度使用率":L/100}
    r = eval_combo(ub)
    if r:
        results.append({"H":H,"M":M,"L":L,"k":r[0],"amt":r[1],"mx":r[2],"by":r[3]})

print(f"需新增 {need/1e8:.2f} 亿 | 达标组合 {len(results)} 个")
print("按[低使用率贡献↑, 最大提幅↑, 中使用率贡献↓]排序(前15):")
results.sort(key=lambda x: (x["by"]["低额度使用率"], x["mx"], -x["by"]["中额度使用率"]))
for r in results[:15]:
    print(f"  高{r['H']}%/中{r['M']}%/低{r['L']}%: k={r['k']:.3f} | 最大提幅{r['mx']*100:.0f}% | "
          f"贡献 高{r['by']['高额度使用率']:.2f}/中{r['by']['中额度使用率']:.2f}/低{r['by']['低额度使用率']:.2f}亿")
