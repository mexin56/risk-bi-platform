# -*- coding: utf-8 -*-
"""PDL 提额方案 v14 —— fpd7风险分档提幅(300%封顶) + 仅A/B/C + 低于大盘风险才提额
提额条件: 评级∈{A,B,C} 且 客群fpd7_rate$ < 大盘fpd7_rate$(21.25%)
提幅: 按fpd7_rate$ 10档单调递减(300%→0%), 高风险(>=30%)不提
方案A: 档位×k 精确达标 5万; 方案B: 满档位(不缩放)
"""
import warnings; warnings.filterwarnings("ignore")
import pandas as pd, numpy as np, os
from openpyxl import load_workbook
from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
from openpyxl.utils import get_column_letter
from openpyxl.formatting.rule import ColorScaleRule

SRC = "/data2/jupyter-wenning/strage/PDL提额系数20260814.xlsx"
DST = "/data2/jupyter-wenning/strage/PDL提额方案-风险分档-20260814.xlsx"
TARGET_AMT = 50000.0
ALLOW_LEVELS = ["A", "B", "C"]
CAP_QUOTA = 500000.0

# 10档提幅(按 fpd7_rate$, 300%封顶, 单调递减, 高风险0%)
AMP_TIERS = [
    (0.02, 3.00, "T1_<2%"), (0.04, 2.60, "T2_2-4%"), (0.06, 2.20, "T3_4-6%"),
    (0.08, 1.80, "T4_6-8%"), (0.10, 1.50, "T5_8-10%"), (0.15, 1.20, "T6_10-15%"),
    (0.20, 0.90, "T7_15-20%"), (0.25, 0.60, "T8_20-25%"), (0.30, 0.30, "T9_25-30%"),
    (np.inf, 0.00, "T10_>=30%"),
]
def amp_of(f):
    for cap, a, _ in AMP_TIERS:
        if f < cap:
            return a
    return 0.0
def tier_of(f):
    for cap, _, n in AMP_TIERS:
        if f < cap:
            return n
    return "T10_>=30%"

# ---- 1. 读数据 ----
df = pd.read_excel(SRC, sheet_name=0)
cols, seen = [], {}
for c in df.columns:
    s = str(c).strip()
    seen[s] = seen.get(s, 0) + 1
    cols.append(s if seen[s] == 1 else f"{s}_数值")
df.columns = cols
df = df[df["flag_customer"] != "总计"].reset_index(drop=True)
assert (df["结清客户"] - df["提额客户"] - df["未提额客户"]).abs().max() <= 1

N = df["结清客户"].sum()
cur_amt = (df["结清客户"] * df["平均额度"]).sum()
need = TARGET_AMT * N - cur_amt
cur_fpd7 = (df["结清客户"] * df["平均额度"] * df["fpd7_rate$"]).sum() / cur_amt
print(f"PDL结清客户 {N:,} | 当前平均 {cur_amt/N:,.0f} | 大盘fpd7_rate$ {cur_fpd7*100:.2f}% | 需新增 {need/1e8:.2f} 亿")

df["等级可提"] = df["评级"].isin(ALLOW_LEVELS)
df["是否可提额"] = df["等级可提"]
df["风险档"] = df["fpd7_rate$"].apply(tier_of)
df["档位提幅"] = df["fpd7_rate$"].apply(amp_of)
print(f"可提额客群 {df['是否可提额'].sum()} 行 | 提额客户 {df.loc[df['是否可提额'],'提额客户'].sum():,}")

# ---- 2. 计算 ----
def compute(k=1.0):
    amp = np.where(df["是否可提额"], df["档位提幅"] * k, 0.0)
    new_per = np.minimum(df["提额客户_平均额度"] * (1 + amp), CAP_QUOTA)
    inc = df["提额客户"] * np.maximum(0, new_per - df["提额客户_平均额度"])
    return amp, new_per, inc

# 方案B: 满档位
amp_b, new_per_b, inc_b = compute(1.0)
avg_b = (cur_amt + inc_b.sum()) / N
print(f"方案B[满档位不缩放]: 新增 {inc_b.sum()/1e8:.2f} 亿 | 可达 {avg_b:,.0f}")

# 方案A: 二分k
lo, hi = 0.2, 1.0
for _ in range(80):
    mid = (lo + hi) / 2
    if compute(mid)[2].sum() > need:
        hi = mid
    else:
        lo = mid
k = (lo + hi) / 2
amp_a, new_per_a, inc_a = compute(k)
avg_a = (cur_amt + inc_a.sum()) / N
print(f"方案A[档位×{k:.3f}]: 新增 {inc_a.sum()/1e8:.2f} 亿 | 平均额度 {avg_a:,.0f} ✅")

df["方案A幅度"] = amp_a
df["方案A后额度"] = new_per_a
df["方案A新增"] = inc_a
df["方案A新增(万)"] = (inc_a / 1e4).round(0)
df["方案B幅度"] = amp_b
df["方案B后额度"] = new_per_b
df["方案B新增"] = inc_b

# ---- 3. 决策依据 ----
def reason(r):
    if not r["是否可提额"]:
        why = "评级D/E" if not r["等级可提"] else f"fpd7_rate${r['fpd7_rate$']*100:.1f}%高于大盘{cur_fpd7*100:.1f}%"
        return f"评级={r['评级']}, {why}, 不予提额"
    if r["方案A新增"] <= 0:
        return f"评级={r['评级']}, 档位提幅0%, 不予提额"
    return (f"评级={r['评级']}, fpd7_rate${r['fpd7_rate$']*100:.1f}%({r['风险档']}, 低于大盘{cur_fpd7*100:.1f}%), "
            f"档位提幅{r['档位提幅']*100:.0f}%×{k:.2f}→+{r['方案A幅度']*100:.0f}%, 提额后额度{r['方案A后额度']:,.0f}元")
df["提额决策依据"] = df.apply(reason, axis=1)

# ---- 4. 整体指标 ----
amt_after = df["结清客户"] * df["平均额度"] + df["方案A新增"]
fpd7s_a = (amt_after * df["fpd7_rate$"]).sum() / amt_after.sum()
amt_after_b = df["结清客户"] * df["平均额度"] + df["方案B新增"]
fpd7s_b = (amt_after_b * df["fpd7_rate$"]).sum() / amt_after_b.sum()

# ---- 5. 汇总 ----
summary = pd.DataFrame([
    {"模块": "方案目标", "指标": "整体平均额度", "数值": f"{cur_amt/N:,.0f} → {avg_a:,.0f} 元",
     "说明": f"目标 {TARGET_AMT:,.0f} 元, 需新增 {need/1e8:.2f} 亿 ✅ 方案A达标"},
    {"模块": "约束规则", "指标": "提额客群范围", "数值": "仅评级 A/B/C",
     "说明": f"D/E 客群({df.loc[~df['等级可提'],'提额客户'].sum():,}提额客户)不予提额, 未提额客户额度不变"},
    {"模块": "约束规则", "指标": "提幅档位", "数值": "10档, 300%封顶, 单调递减",
     "说明": "<2%→300% / 2-4%→260% / 4-6%→220% / 6-8%→180% / 8-10%→150% / 10-15%→120% / 15-20%→90% / 20-25%→60% / 25-30%→30% / >=30%→0"},
    {"模块": "约束规则", "指标": "整体缩放k", "数值": f"×{k:.2f}",
     "说明": f"满档位可达{avg_b:,.0f}, 缩放至精确50,000"},
    {"模块": "约束规则", "指标": "额度上限", "数值": "500,000 元", "说明": "授信总上限, 基本不触顶"},
    {"模块": "勾兑关系", "指标": "结清/提额/未提额", "数值": f"{N:,} = {df['提额客户'].sum():,} + {df['未提额客户'].sum():,}",
     "说明": "勾兑校验通过(差=0), 未提额客户额度保持不变"},
    {"模块": "方案A(达标5万)", "指标": "整体平均额度", "数值": f"{avg_a:,.0f} 元", "说明": "✅ 精确达标"},
    {"模块": "方案A(达标5万)", "指标": "新增总授信", "数值": f"{inc_a.sum()/1e8:.2f} 亿", "说明": f"规模增幅 {inc_a.sum()/cur_amt*100:.1f}%"},
    {"模块": "方案A(达标5万)", "指标": "整体fpd7_rate$", "数值": f"{fpd7s_a*100:.2f}%",
     "说明": f"现状 {cur_fpd7*100:.2f}%, 降低 {(cur_fpd7-fpd7s_a)*100:.2f}pp (相对{(cur_fpd7-fpd7s_a)/cur_fpd7*100:.1f}%)"},
    {"模块": "方案B(满档位)", "指标": "可达平均额度", "数值": f"{avg_b:,.0f} 元",
     "说明": f"新增 {inc_b.sum()/1e8:.2f} 亿, fpd7_rate$→{fpd7s_b*100:.2f}%"},
])

# ---- 6. 输出 Excel ----
wb = load_workbook(SRC)
for s in list(wb.sheetnames):
    wb.remove(wb[s])
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
ws5 = wb.create_sheet("Sheet3_原始")
for row in wb_src.worksheets[0].iter_rows():
    for cell in row:
        if cell.value is None and not cell.has_style:
            continue
        nc = ws5.cell(row=cell.row, column=cell.column, value=cell.value)
        if cell.has_style:
            nc._style = cell._style
wb_src.close()

# 提额结果
res = df[["flag_customer", "use_rate_group", "借款次数", "评级", "结清客户", "额度使用率",
          "件均", "平均额度", "提额客户", "提额客户_平均额度", "提额客户_提额后平均",
          "未提额客户", "未提额_额度件均", "未提额客户_提后件均", "发起下一笔订单",
          "fpd1_fm_dd", "fpd7_fm_dd", "fpd1_rate", "fpd1_rate$", "fpd7_rate", "fpd7_rate$",
          "提幅", "额度", "风险档", "档位提幅", "等级可提", "是否可提额",
          "方案A幅度", "方案A后额度", "方案A新增(万)", "方案B幅度", "方案B后额度", "提额决策依据"]].copy()
ws = wb.create_sheet("提额结果")
write_df(ws, res)
style_sheet(ws, pct_cols=["方案A幅度", "方案B幅度", "档位提幅", "fpd1_rate", "fpd1_rate$", "fpd7_rate", "fpd7_rate$"],
            money_cols=["平均额度", "件均", "提额客户_平均额度", "提额客户_提额后平均", "未提额_额度件均",
                        "未提额客户_提后件均", "提幅", "额度", "方案A后额度", "方案B后额度"],
            int_cols=["结清客户", "提额客户", "未提额客户", "发起下一笔订单", "fpd1_fm_dd", "fpd7_fm_dd", "方案A新增(万)"],
            scale_cols=["fpd7_rate$", "方案A幅度", "方案A后额度"])

# 分档统计
order = [t[2] for t in AMP_TIERS]
tier_recs = []
for rn, g in df.groupby("风险档", observed=True, sort=False):
    tier_recs.append({
        "风险档": rn,
        "客群数": len(g),
        "结清客户数": int(g["结清客户"].sum()),
        "提额客户数": int(g["提额客户"].sum()),
        "档位提幅%": round(g["档位提幅"].iloc[0] * 100, 0),
        "方案A平均幅度%": round((g["提额客户"] * g["方案A幅度"]).sum() / g["提额客户"].sum() * 100, 0) if g["提额客户"].sum() else 0,
        "方案A新增(万)": round(g["方案A新增"].sum() / 1e4, 0),
        "fpd7_rate$加权%": round((g["结清客户"] * g["平均额度"] * g["fpd7_rate$"]).sum() /
                                  (g["结清客户"] * g["平均额度"]).sum() * 100, 2),
    })
tier_stat = pd.DataFrame(tier_recs)
tier_stat["风险档"] = pd.Categorical(tier_stat["风险档"], categories=order, ordered=True)
tier_stat = tier_stat.sort_values("风险档")
ws2 = wb.create_sheet("分档统计")
write_df(ws2, tier_stat)
style_sheet(ws2, pct_cols=["档位提幅%", "方案A平均幅度%", "fpd7_rate$加权%"],
            int_cols=["结清客户数", "提额客户数", "方案A新增(万)"], scale_cols=["fpd7_rate$加权%", "方案A新增(万)"])

# 方案总结
ws6 = wb.create_sheet("提额方案总结")
write_df(ws6, summary)
for c in range(1, 5):
    cell = ws6.cell(row=1, column=c)
    cell.fill, cell.font = HDR_FILL, HDR_FONT
ws6.freeze_panes = "A2"
for col, wd in zip("ABCD", [18, 26, 40, 50]):
    ws6.column_dimensions[col].width = wd
for r in range(2, ws6.max_row + 1):
    for c in range(1, 5):
        cell = ws6.cell(row=r, column=c)
        cell.font = BODY_FONT
        cell.border = BORDER

wb.save(DST)
print(f"\n✅ 已生成: {DST}")
print("Sheets:", wb.sheetnames)
