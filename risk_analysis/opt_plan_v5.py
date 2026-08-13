"""结清客户提额方案 v5 —— 达标5万版(基于更新后的大模型样本1.xlsx)
结论先行: 原始提幅盖帽(均值34%)约束下, 满潜力81.5亿, 可达47,420, 5万不可达;
        必须将提幅盖帽放大 k 倍(约1.9x)才能精确达标 50,000。
方案A: 提幅盖帽×k(二分求解精确达标) + 保留 风险档/使用率上限/额度盖帽 约束
方案B: 原始盖帽约束下的可达水平(47,420) —— 对比基准
输出: Sheet5_原始 + [提额结果] + [分档统计] + [约束统计] + [盖帽敏感度] + [提额方案总结]
"""
import warnings; warnings.filterwarnings("ignore")
import pandas as pd, numpy as np, os
from openpyxl import load_workbook
from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
from openpyxl.utils import get_column_letter
from openpyxl.formatting.rule import ColorScaleRule

SRC = "/data2/jupyter-wenning/strage/大模型样本1.xlsx"
DST = "/data2/jupyter-wenning/strage/大模型样本1-提额方案-达标5万-20260810.xlsx"
TARGET_AMT = 50000.0
TIER_BASE = [1.00, 0.80, 0.60, 0.20, 0.00]
USE_CAP = {"高额度使用率": 1.00, "中额度使用率": 0.80, "低额度使用率": 0.30}

# ---- 1. 读数据(剔除合计行) ----
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

def tier_idx(f):
    if f < 0.05: return 0
    if f < 0.10: return 1
    if f < 0.20: return 2
    if f < 0.30: return 3
    return 4
df["风险档位"] = df["fpd7_rate$"].apply(tier_idx)
df["风险档幅度"] = df["风险档位"].map(lambda i: TIER_BASE[i])
df["使用率上限"] = df["额度使用率"].map(USE_CAP)
df["提额额度基数"] = df["提额客户"] * df["提额客户_平均额度"]

N = df["结清客户"].sum()
cur_amt = (df["结清客户"] * df["结清客户_平均额度"]).sum()
need = TARGET_AMT * N - cur_amt
print(f"结清客户 {N:,} | 当前平均额度 {cur_amt/N:,.0f} | 目标 {TARGET_AMT:,.0f} 需新增 {need/1e8:.2f} 亿")

# ---- 2. 方案计算 ----
def compute(m):
    """盖帽统一放大m倍: 幅度 = min(风险档, use_cap, 提幅盖帽×m); 额度 = min(原×(1+幅度), 额度盖帽×m)"""
    amp = np.minimum.reduce([df["风险档幅度"], df["使用率上限"], df["提幅盖帽"] * m])
    new_per = np.minimum(df["提额客户_平均额度"] * (1 + amp), df["额度盖帽"] * m)
    inc = df["提额客户"] * np.maximum(0, new_per - df["提额客户_平均额度"])
    return amp, new_per, inc

# 方案B: 原始盖帽(基准)
_, _, inc_b = compute(1.0)
avg_b = (cur_amt + inc_b.sum()) / N
print(f"方案B[原始盖帽]: 新增 {inc_b.sum()/1e8:.2f} 亿 | 可达 {avg_b:,.0f} 元")

# 方案A: 二分盖帽放大倍数 m → 精确达标 50,000
lo, hi = 1.0, 6.0
for _ in range(90):
    mid = (lo + hi) / 2
    if compute(mid)[2].sum() < need:
        lo = mid
    else:
        hi = mid
m = (lo + hi) / 2
amp_a, new_per_a, inc_a = compute(m)
avg_a = (cur_amt + inc_a.sum()) / N
print(f"方案A[盖帽×{m:.3f}]: 新增 {inc_a.sum()/1e8:.2f} 亿 | 平均额度 {avg_a:,.0f} 元 ✅")

df["方案A幅度"] = amp_a
df["方案A后额度"] = new_per_a
df["方案A新增"] = inc_a
df["方案A新增(万)"] = (inc_a / 1e4).round(0)
df["方案B幅度"] = np.minimum.reduce([df["风险档幅度"], df["使用率上限"], df["提幅盖帽"]])
df["方案B后额度"] = np.minimum(df["提额客户_平均额度"] * (1 + df["方案B幅度"]), df["额度盖帽"])
df["方案B新增"] = df["提额客户"] * np.maximum(0, df["方案B后额度"] - df["提额客户_平均额度"])

# ---- 3. 决策依据(方案A) ----
def reason(r):
    if r["方案A幅度"] <= 0:
        return (f"score_level={r['score_level']}, fpd7_rate${r['fpd7_rate$']*100:.1f}%高风险(T5)或额度盖帽≤原额度, 不予提额")
    src = []
    if r["方案A幅度"] >= r["使用率上限"] - 1e-9:
        src.append(f"使用率上限{r['使用率上限']*100:.0f}%")
    if r["方案A幅度"] >= r["提幅盖帽"] * m - 1e-9 and r["提幅盖帽"] * m < r["使用率上限"] - 1e-9:
        src.append(f"提幅盖帽×{m:.2f}({r['提幅盖帽']*100:.0f}%→{min(r['提幅盖帽']*m, r['使用率上限'])*100:.0f}%)")
    if not src:
        src.append("风险分档")
    capped = r["方案A后额度"] >= r["额度盖帽"] * m - 1e-6 and r["提额客户_平均额度"] * (1 + r["方案A幅度"]) > r["额度盖帽"] * m + 1e-6
    return (f"score_level={r['score_level']}, fpd7_rate${r['fpd7_rate$']*100:.1f}%, 提额+{r['方案A幅度']*100:.0f}%"
            f"({'、'.join(src)}), 提额后额度{r['方案A后额度']:,.0f}元" + ("(触额度盖帽)" if capped else ""))
df["提额决策依据"] = df.apply(reason, axis=1)

# ---- 4. 整体指标 ----
amt_after_a = df["结清客户"] * df["结清客户_平均额度"] + df["方案A新增"]
fpd7s_a = (amt_after_a * df["fpd7_rate$"]).sum() / amt_after_a.sum()
cur_fpd7s = (df["结清客户"] * df["结清客户_平均额度"] * df["fpd7_rate$"]).sum() / cur_amt

# ---- 5. 敏感度矩阵 ----
sens_rows = []
for tm in [1.0, 1.25, 1.5, 1.75, 2.0, 2.5]:
    for qm in [1.0, 2.0]:
        amp2 = np.minimum.reduce([df["风险档幅度"], df["使用率上限"], df["提幅盖帽"] * tm])
        np2 = np.minimum(df["提额客户_平均额度"] * (1 + amp2), df["额度盖帽"] * qm)
        inc2 = df["提额客户"] * np.maximum(0, np2 - df["提额客户_平均额度"])
        avg2 = (cur_amt + inc2.sum()) / N
        sens_rows.append({"提幅盖帽放大": f"×{tm:g}", "额度盖帽放大": f"×{qm:g}",
                          "可达平均额度": round(avg2, 0), "新增授信(亿)": round(inc2.sum() / 1e8, 2),
                          "是否达标5万": "✅" if avg2 >= 50000 else ""})
sens = pd.DataFrame(sens_rows)

# ---- 6. 汇总 ----
TIER_NAMES = ["T1_超低风险(<5%)", "T2_低风险(5-10%)", "T3_中低风险(10-20%)", "T4_中风险(20-30%)", "T5_高风险(>=30%)"]
summary = pd.DataFrame([
    {"模块": "方案目标", "指标": "整体平均额度", "数值": f"{cur_amt/N:,.0f} → {avg_a:,.0f} 元",
     "说明": f"目标 {TARGET_AMT:,.0f} 元, 需新增 {need/1e8:.2f} 亿 ✅ 达标"},
    {"模块": "约束规则", "指标": "风险分档", "数值": "T1=100% T2=80% T3=60% T4=20% T5=0",
     "说明": "按 fpd7_rate$: <5% / 5-10% / 10-20% / 20-30% / >=30%(T5不提额)"},
    {"模块": "约束规则", "指标": "使用率上限", "数值": "高≤100% / 中≤80% / 低≤30%", "说明": "保留"},
    {"模块": "约束规则", "指标": "提幅盖帽", "数值": f"×{m:.2f} 放大(均值{df['提幅盖帽'].mean()*100:.0f}%→{min(df['提幅盖帽'].mean()*m, 1)*100:.0f}%)",
     "说明": "⚠️ 原始盖帽下5万不可达(仅47,420), 提幅盖帽与额度盖帽统一放大×m 精确达标"},
    {"模块": "约束规则", "指标": "额度盖帽", "数值": f"×{m:.2f} 放大(中位{df['额度盖帽'].median():,.0f}→{df['额度盖帽'].median()*m:,.0f}元)",
     "说明": "放大后仍高于大部分客群提额后额度, 仅少量高额度客群触顶"},
    {"模块": "勾兑关系", "指标": "结清/提额/未提额", "数值": f"{N:,} = {df['提额客户'].sum():,} + {df['未提额客户'].sum():,}",
     "说明": "未提额客户额度保持不变"},
    {"模块": "方案A(达标5万)", "指标": "整体平均额度", "数值": f"{avg_a:,.0f} 元", "说明": "✅ 精确达标"},
    {"模块": "方案A(达标5万)", "指标": "新增总授信", "数值": f"{inc_a.sum()/1e8:.2f} 亿", "说明": f"规模增幅 {inc_a.sum()/cur_amt*100:.1f}%"},
    {"模块": "方案A(达标5万)", "指标": "整体fpd7_rate$", "数值": f"{fpd7s_a*100:.2f}%",
     "说明": f"现状 {cur_fpd7s*100:.2f}%, 下降 {(cur_fpd7s-fpd7s_a)*100:.2f}pp"},
    {"模块": "方案B(原始盖帽)", "指标": "可达平均额度", "数值": f"{avg_b:,.0f} 元",
     "说明": f"新增 {inc_b.sum()/1e8:.2f} 亿, 覆盖率 {inc_b.sum()/need*100:.1f}% — 5万不可达(基准对比)"},
])

# ---- 7. 输出 Excel ----
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

# 分档统计
df["风险分档名"] = df["风险档位"].map(lambda i: TIER_NAMES[i])
tier_stat = df.groupby("风险分档名").apply(lambda g: pd.Series({
    "客群数": len(g), "结清客户数": int(g["结清客户"].sum()), "提额客户数": int(g["提额客户"].sum()),
    "平均提幅盖帽%": round((g["提额客户"] * g["提幅盖帽"]).sum() / g["提额客户"].sum() * 100, 1),
    "方案A平均幅度%": round((g["提额客户"] * g["方案A幅度"]).sum() / g["提额客户"].sum() * 100, 1),
    "方案A新增(万)": round(g["方案A新增"].sum() / 1e4, 0),
    "fpd7_rate$加权%": round((g["结清客户"] * g["结清客户_平均额度"] * g["fpd7_rate$"]).sum() /
                              (g["结清客户"] * g["结清客户_平均额度"]).sum() * 100, 2),
}), include_groups=False).reset_index()
tier_stat["风险分档名"] = pd.Categorical(tier_stat["风险分档名"], categories=TIER_NAMES, ordered=True)
tier_stat = tier_stat.sort_values("风险分档名")
ws2 = wb.create_sheet("分档统计")
write_df(ws2, tier_stat)
style_sheet(ws2, pct_cols=["平均提幅盖帽%", "方案A平均幅度%", "fpd7_rate$加权%"],
            int_cols=["结清客户数", "提额客户数", "方案A新增(万)"], scale_cols=["fpd7_rate$加权%", "方案A新增(万)"])

# 约束统计
use_recs = []
for u, g in df.groupby("额度使用率", observed=True, sort=False):
    use_recs.append({
        "额度使用率": u, "客群数": len(g), "提额客户数": int(g["提额客户"].sum()),
        "平均提幅盖帽%": round((g["提额客户"] * g["提幅盖帽"]).sum() / g["提额客户"].sum() * 100, 1),
        "使用率上限": USE_CAP[u],
        "方案A平均幅度%": round((g["提额客户"] * g["方案A幅度"]).sum() / g["提额客户"].sum() * 100, 1),
        "方案A新增(万)": round(g["方案A新增"].sum() / 1e4, 0),
    })
use_stat = pd.DataFrame(use_recs)
use_stat["额度使用率"] = pd.Categorical(use_stat["额度使用率"], categories=["高额度使用率", "中额度使用率", "低额度使用率"], ordered=True)
use_stat = use_stat.sort_values("额度使用率")
ws3 = wb.create_sheet("约束统计")
write_df(ws3, use_stat)
style_sheet(ws3, pct_cols=["平均提幅盖帽%", "方案A平均幅度%"], int_cols=["提额客户数", "方案A新增(万)"])

# 敏感度
ws4 = wb.create_sheet("盖帽敏感度")
write_df(ws4, sens)
style_sheet(ws4, money_cols=["可达平均额度"], int_cols=["新增授信(亿)"], scale_cols=["可达平均额度"])

# 总结
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
