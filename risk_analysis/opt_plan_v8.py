"""结清客户提额方案 v8 —— 以表格提幅盖帽为唯一幅度约束(200%上限真实生效)
规则: 幅度 = 提幅盖帽×k(无风险分档/无使用率约束); 额度 = min(原×(1+幅度), 额度盖帽)
方案A: 提幅盖帽×k(二分精确达标5万); 方案B: 原始盖帽约束内最优
输出: Sheet5_原始 + [提额结果] + [分档统计] + [约束统计] + [约束归因] + [约束对比验证] + [提额方案总结]
"""
import warnings; warnings.filterwarnings("ignore")
import pandas as pd, numpy as np, os
from openpyxl import load_workbook
from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
from openpyxl.utils import get_column_letter
from openpyxl.formatting.rule import ColorScaleRule

SRC = "/data2/jupyter-wenning/strage/大模型样本2.xlsx"
DST = "/data2/jupyter-wenning/strage/大模型样本2-提额方案-盖帽版-20260810.xlsx"
TARGET_AMT = 50000.0

# ---- 1. 读数据 ----
df = pd.read_excel(SRC, sheet_name="Sheet5")
cols, seen = [], {}
for c in df.columns:
    s = str(c).strip()
    seen[s] = seen.get(s, 0) + 1
    cols.append(s if seen[s] == 1 else f"{s}_数值")
df.columns = cols
df = df[~((df["flag_customer"] == "total") | (df["额度使用率"] == "total") |
          (df["借款次数"] == "total") | (df["score_level"] == "total"))].reset_index(drop=True)
assert (df["结清客户"] - df["提额客户"] - df["未提额客户"]).abs().max() <= 200

N = df["结清客户"].sum()
cur_amt = (df["结清客户"] * df["结清客户_平均额度"]).sum()
need = TARGET_AMT * N - cur_amt
print(f"结清客户 {N:,} | 当前平均额度 {cur_amt/N:,.0f} | 目标需新增 {need/1e8:.2f} 亿")

# ---- 2. 计算 ----
def compute(X, Q=1.0):
    """幅度 = 提幅盖帽×X; 额度 = min(原×(1+幅度), 额度盖帽×Q)"""
    amp = df["提幅盖帽"] * X
    new_per = np.minimum(df["提额客户_平均额度"] * (1 + amp), df["额度盖帽"] * Q)
    inc = df["提额客户"] * np.maximum(0, new_per - df["提额客户_平均额度"])
    return amp, new_per, inc

# 方案B: 原始盖帽
_, _, inc_b = compute(1.0)
avg_b = (cur_amt + inc_b.sum()) / N
print(f"方案B[原始盖帽]: 新增 {inc_b.sum()/1e8:.2f} 亿 | 可达 {avg_b:,.0f} 元")

# 方案A: 二分盖帽×k → 精确达标
lo, hi = 1.0, 10.0
for _ in range(90):
    mid = (lo + hi) / 2
    if compute(mid)[2].sum() < need:
        lo = mid
    else:
        hi = mid
k = (lo + hi) / 2
amp_a, new_per_a, inc_a = compute(k)
avg_a = (cur_amt + inc_a.sum()) / N
print(f"方案A[提幅盖帽×{k:.2f}]: 新增 {inc_a.sum()/1e8:.2f} 亿 | 平均额度 {avg_a:,.0f} ✅")

df["方案A幅度"] = amp_a
df["方案A后额度"] = new_per_a
df["方案A新增"] = inc_a
df["方案A新增(万)"] = (inc_a / 1e4).round(0)
df["方案B幅度"] = df["提幅盖帽"]
df["方案B后额度"] = np.minimum(df["提额客户_平均额度"] * (1 + df["方案B幅度"]), df["额度盖帽"])
df["方案B新增"] = df["提额客户"] * np.maximum(0, df["方案B后额度"] - df["提额客户_平均额度"])

# ---- 3. 决策依据 ----
def reason(r):
    capped = r["方案A后额度"] >= r["额度盖帽"] - 1e-6 and r["提额客户_平均额度"] * (1 + r["方案A幅度"]) > r["额度盖帽"] + 1e-6
    if r["方案A新增"] <= 0:
        return (f"额度盖帽{r['额度盖帽']:,.0f}元 ≤ 原额度{r['提额客户_平均额度']:,.0f}元, 无法提额")
    return (f"score_level={r['score_level']}, 提幅盖帽{r['提幅盖帽']*100:.0f}%×{k:.2f}→提额+{r['方案A幅度']*100:.0f}%, "
            f"提额后额度{r['方案A后额度']:,.0f}元" + ("(触额度盖帽)" if capped else ""))
df["提额决策依据"] = df.apply(reason, axis=1)

# ---- 4. 约束归因 ----
def _inc(amp_, q=None):
    np_ = np.minimum(df["提额客户_平均额度"] * (1 + amp_), q) if q is not None else df["提额客户_平均额度"] * (1 + amp_)
    return df["提额客户"] * np.maximum(0, np_ - df["提额客户_平均额度"])
v1 = _inc(np.full(len(df), 1.0)).sum()
v2 = _inc(df["提幅盖帽"]).sum()
v3 = inc_b.sum()
attr_rows = []
for name, v in [("完全放开(全部+100%)", v1), ("+提幅盖帽(表格)", v2), ("+额度盖帽(表格)", v3)]:
    attr_rows.append({"约束叠加": name, "新增授信(亿)": round(v / 1e8, 2),
                      "本步削减(亿)": "" if not attr_rows else round((attr_rows[-1]["新增授信(亿)"] - v / 1e8), 2)})
attr_df = pd.DataFrame(attr_rows)

# ---- 5. 对比验证(有/无风险分档) ----
TIER_BASE = [1.00, 0.80, 0.60, 0.20, 0.00]
def tier_idx(f):
    if f < 0.05: return 0
    if f < 0.10: return 1
    if f < 0.20: return 2
    if f < 0.30: return 3
    return 4
df["风险档位"] = df["fpd7_rate$"].apply(tier_idx)

def _inc_old(with_tier):
    amp = df["提幅盖帽"]
    if with_tier:
        amp = np.minimum(df["风险档位"].map(lambda i: TIER_BASE[i]), amp)
    np_ = np.minimum(df["提额客户_平均额度"] * (1 + amp), df["额度盖帽"])
    return df["提额客户"] * np.maximum(0, np_ - df["提额客户_平均额度"])

cmp_rows = [
    {"场景": "v7版: 有风险分档(T1~T5)", "新增授信(亿)": round(_inc_old(True).sum() / 1e8, 2),
     "平均额度": round((cur_amt + _inc_old(True).sum()) / N, 0), "说明": "上一版约束内最优"},
    {"场景": "本版: 无风险分档(仅表格盖帽)", "新增授信(亿)": round(_inc_old(False).sum() / 1e8, 2),
     "平均额度": round((cur_amt + _inc_old(False).sum()) / N, 0), "说明": "去掉风险分档, 200%上限客群可提200%"},
    {"场景": "去掉风险分档的贡献(亿)", "新增授信(亿)": round((_inc_old(False).sum() - _inc_old(True).sum()) / 1e8, 2),
     "平均额度": np.nan, "说明": "T5高风险客群(盖帽10-16%)与T4部分客群受益"},
    {"场景": "提幅盖帽=200%的客群数", "新增授信(亿)": int((df["提幅盖帽"] == 2.0).sum()), "平均额度": np.nan,
     "说明": "A级×高使用率×借款1-3次, 本版可提200%×k"},
]
cmp_df = pd.DataFrame(cmp_rows)

# ---- 6. 整体指标 ----
amt_after = df["结清客户"] * df["结清客户_平均额度"] + df["方案A新增"]
fpd7s_a = (amt_after * df["fpd7_rate$"]).sum() / amt_after.sum()
cur_fpd7s = (df["结清客户"] * df["结清客户_平均额度"] * df["fpd7_rate$"]).sum() / cur_amt
amt_after_b = df["结清客户"] * df["结清客户_平均额度"] + df["方案B新增"]
fpd7s_b = (amt_after_b * df["fpd7_rate$"]).sum() / amt_after_b.sum()

# ---- 7. 汇总 ----
summary = pd.DataFrame([
    {"模块": "方案目标", "指标": "整体平均额度", "数值": f"{cur_amt/N:,.0f} → {avg_a:,.0f} 元",
     "说明": f"目标 {TARGET_AMT:,.0f} 元, 需新增 {need/1e8:.2f} 亿 ✅ 方案A达标"},
    {"模块": "约束规则", "指标": "风险分档(T1~T5)", "数值": "已移除",
     "说明": "按需求去掉, 不再限制提幅上限"},
    {"模块": "约束规则", "指标": "额度使用率约束", "数值": "已移除", "说明": "按需求去掉"},
    {"模块": "约束规则", "指标": "提幅盖帽(唯一幅度约束)", "数值": f"方案A放大×{k:.2f}",
     "说明": f"表格均值{df['提幅盖帽'].mean()*100:.0f}%, 最大200%(3个A级客群), 方案A后均值{min(df['提幅盖帽'].mean()*k, 2)*100:.0f}%"},
    {"模块": "约束规则", "指标": "额度盖帽", "数值": "保持原值", "说明": f"中位{df['额度盖帽'].median():,.0f}元"},
    {"模块": "勾兑关系", "指标": "结清/提额/未提额", "数值": f"{N:,} = {df['提额客户'].sum():,} + {df['未提额客户'].sum():,}",
     "说明": "未提额客户额度保持不变"},
    {"模块": "方案A(达标5万)", "指标": "整体平均额度", "数值": f"{avg_a:,.0f} 元", "说明": "✅ 精确达标"},
    {"模块": "方案A(达标5万)", "指标": "新增总授信", "数值": f"{inc_a.sum()/1e8:.2f} 亿", "说明": f"规模增幅 {inc_a.sum()/cur_amt*100:.1f}%"},
    {"模块": "方案A(达标5万)", "指标": "整体fpd7_rate$", "数值": f"{fpd7s_a*100:.2f}%",
     "说明": f"现状 {cur_fpd7s*100:.2f}%, 降低 {(cur_fpd7s-fpd7s_a)*100:.2f}pp (相对{(cur_fpd7s-fpd7s_a)/cur_fpd7s*100:.1f}%)"},
    {"模块": "方案B(原始盖帽)", "指标": "可达平均额度", "数值": f"{avg_b:,.0f} 元",
     "说明": f"新增 {inc_b.sum()/1e8:.2f} 亿, fpd7_rate$→{fpd7s_b*100:.2f}%(降{(cur_fpd7s-fpd7s_b)*100:.2f}pp)"},
])

# ---- 8. 输出 Excel ----
wb = load_workbook(SRC)
wb.remove(wb["Sheet5"]) if "Sheet5" in wb.sheetnames else None
HDR_FILL = PatternFill("solid", fgColor="4E83FD")
HDR_FONT = Font(name="微软雅黑", size=10, bold=True, color="FFFFFF")
BODY_FONT = Font(name="微软雅黑", size=9)
THIN = Side(style="thin", color="D9E2F3")
BORDER = Border(left=THIN, right=THIN, top=THIN, bottom=THIN)

def style_sheet(ws, pct_cols=(), money_cols=(), int_cols=(), scale_cols=()):
    ncol = ws.max_column
    for c in range(1, ncol + 1):
        cell = ws.cell(row=1, column=c)
        cell.fill, cell.font = HDR_FILL, HDR_FONT
        cell.alignment = Alignment(horizontal="center", vertical="center")
        cell.border = BORDER
    ws.freeze_panes = "B2"
    ws.row_dimensions[1].height = 24
    hdrs = [str(ws.cell(row=1, column=c).value or "") for c in range(1, ncol + 1)]
    for c, h in enumerate(hdrs, 1):
        col = get_column_letter(c)
        ws.column_dimensions[col].width = max(10, min(36, len(h) * 2 + 4))
        if h in pct_cols:
            for r in range(2, ws.max_row + 1):
                ws.cell(row=r, column=c).number_format = "0.0%"
        elif h in money_cols:
            for r in range(2, ws.max_row + 1):
                ws.cell(row=r, column=c).number_format = "#,##0"
        elif h in int_cols:
            for r in range(2, ws.max_row + 1):
                ws.cell(row=r, column=c).number_format = "#,##0"
        if h in scale_cols and ws.max_row > 2:
            rng = f"{col}2:{col}{ws.max_row}"
            ws.conditional_formatting.add(rng, ColorScaleRule(
                start_type="min", start_color="63BE7B", mid_type="percentile", mid_value=50,
                mid_color="FFEB84", end_type="max", end_color="F8696B"))
    ws.auto_filter.ref = f"A1:{get_column_letter(ncol)}{ws.max_row}"

def write_df(ws, data):
    for c, col in enumerate(data.columns, 1):
        ws.cell(row=1, column=c, value=col)
    for r, (_, row) in enumerate(data.iterrows(), 2):
        for c, col in enumerate(data.columns, 1):
            ws.cell(row=r, column=c, value=row[col])

# 原始数据
wb_src = load_workbook(SRC)
ws5 = wb.create_sheet("Sheet5_原始")
for row in wb_src["Sheet5"].iter_rows():
    for cell in row:
        if cell.value is None and not cell.has_style:
            continue
        nc = ws5.cell(row=cell.row, column=cell.column, value=cell.value)
        if cell.has_style:
            nc._style = cell._style
wb_src.close()

# 提额结果
res = df[["flag_customer", "额度使用率", "借款次数", "score_level", "结清客户", "结清客户_平均额度",
          "结清客户_件均", "提额客户", "提额客户_平均额度", "未提额客户", "未提额_平均额度",
          "下笔额度使用", "fpd1_rate$", "fpd1_rate", "fpd7_rate$", "fpd7_rate",
          "提幅盖帽", "额度盖帽", "方案A幅度", "方案A后额度", "方案A新增(万)",
          "方案B幅度", "方案B后额度", "提额决策依据"]].copy()
ws = wb.create_sheet("提额结果")
write_df(ws, res)
style_sheet(ws, pct_cols=["方案A幅度", "方案B幅度", "fpd1_rate$", "fpd1_rate", "fpd7_rate$", "fpd7_rate", "提幅盖帽"],
            money_cols=["结清客户_平均额度", "结清客户_件均", "提额客户_平均额度", "未提额_平均额度",
                        "额度盖帽", "方案A后额度", "方案B后额度"],
            int_cols=["结清客户", "提额客户", "未提额客户", "方案A新增(万)"],
            scale_cols=["fpd7_rate$", "方案A幅度", "方案A后额度"])

# 分档统计(score_level)
tier_stat = df.groupby("score_level").apply(lambda g: pd.Series({
    "客群数": len(g), "结清客户数": int(g["结清客户"].sum()), "提额客户数": int(g["提额客户"].sum()),
    "平均提幅盖帽%": round((g["提额客户"] * g["提幅盖帽"]).sum() / g["提额客户"].sum() * 100, 1),
    "方案A平均幅度%": round((g["提额客户"] * g["方案A幅度"]).sum() / g["提额客户"].sum() * 100, 1),
    "方案A新增(万)": round(g["方案A新增"].sum() / 1e4, 0),
    "fpd7_rate$加权%": round((g["结清客户"] * g["结清客户_平均额度"] * g["fpd7_rate$"]).sum() /
                              (g["结清客户"] * g["结清客户_平均额度"]).sum() * 100, 2),
}), include_groups=False).reset_index()
tier_stat["score_level"] = pd.Categorical(tier_stat["score_level"], categories=["A", "B", "C", "D", "E"], ordered=True)
tier_stat = tier_stat.sort_values("score_level")
ws2 = wb.create_sheet("分档统计")
write_df(ws2, tier_stat)
style_sheet(ws2, pct_cols=["平均提幅盖帽%", "方案A平均幅度%", "fpd7_rate$加权%"],
            int_cols=["结清客户数", "提额客户数", "方案A新增(万)"], scale_cols=["fpd7_rate$加权%", "方案A新增(万)"])

# 约束统计(使用率维度)
use_recs = []
for u, g in df.groupby("额度使用率", observed=True, sort=False):
    use_recs.append({
        "额度使用率": u, "客群数": len(g), "提额客户数": int(g["提额客户"].sum()),
        "平均提幅盖帽%": round((g["提额客户"] * g["提幅盖帽"]).sum() / g["提额客户"].sum() * 100, 1),
        "方案A平均幅度%": round((g["提额客户"] * g["方案A幅度"]).sum() / g["提额客户"].sum() * 100, 1),
        "方案A新增(万)": round(g["方案A新增"].sum() / 1e4, 0),
    })
use_stat = pd.DataFrame(use_recs)
use_stat["额度使用率"] = pd.Categorical(use_stat["额度使用率"], categories=["高额度使用率", "中额度使用率", "低额度使用率"], ordered=True)
use_stat = use_stat.sort_values("额度使用率")
ws3 = wb.create_sheet("约束统计")
write_df(ws3, use_stat)
style_sheet(ws3, pct_cols=["平均提幅盖帽%", "方案A平均幅度%"], int_cols=["提额客户数", "方案A新增(万)"])

# 约束归因
ws4 = wb.create_sheet("约束归因")
write_df(ws4, attr_df)
style_sheet(ws4, int_cols=["新增授信(亿)", "本步削减(亿)"])

# 对比验证
ws7 = wb.create_sheet("约束对比验证")
write_df(ws7, cmp_df)
style_sheet(ws7, money_cols=["平均额度"], int_cols=["新增授信(亿)"])

# 方案总结
ws6 = wb.create_sheet("提额方案总结")
write_df(ws6, summary)
for c in range(1, 5):
    cell = ws6.cell(row=1, column=c)
    cell.fill, cell.font = HDR_FILL, HDR_FONT
ws6.freeze_panes = "A2"
for col, wd in zip("ABCD", [18, 26, 36, 50]):
    ws6.column_dimensions[col].width = wd
for r in range(2, ws6.max_row + 1):
    for c in range(1, 5):
        cell = ws6.cell(row=r, column=c)
        cell.font = BODY_FONT
        cell.border = BORDER

wb.save(DST)
print(f"\n✅ 已生成: {DST}")
print("Sheets:", wb.sheetnames)
