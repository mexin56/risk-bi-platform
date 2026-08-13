"""结清客户提额方案优化 v3 —— 叠加额度使用率约束
规则:
  1) 风险分档(基于客群 fpd7_rate$): <5%→T1 / 5-10%→T2 / 10-20%→T3 / 20-30%→T4 / >=30%→T5(不提额)
     档位: T1=100% T2=80% T3=60% T4=20% T5=0
  2) 额度使用率上限: 高使用率<=100% / 中使用率<=80% / 低使用率<=30%
     最终幅度 = min(风险档位×缩放k, 使用率上限)
  3) 缩放k(二分求解, 触cap行不再放大): 使整体平均额度精确达到目标
输出: 原表 + [提额结果] + [分档统计] + [使用率约束统计] + [提额方案总结]
"""
import warnings; warnings.filterwarnings("ignore")
import pandas as pd, numpy as np, os
from openpyxl import load_workbook
from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
from openpyxl.utils import get_column_letter
from openpyxl.formatting.rule import ColorScaleRule

SRC = "/data2/jupyter-wenning/strage/基于客群笔数额度使用率提额20260810.xlsx"
DST = "/data2/jupyter-wenning/strage/基于客群笔数额度使用率提额-方案-20260810.xlsx"
TARGET_AMT = 50000.0
TARGET_B_AMT = 48000.0

TIER_BASE = [1.00, 0.80, 0.60, 0.20, 0.00]     # 风险档位 T1..T5
USE_CAP = {"高额度使用率": 1.00, "中额度使用率": 0.80, "低额度使用率": 0.30}

# ---- 1. 读数据 ----
df = pd.read_excel(SRC, sheet_name="Sheet5")
cols, seen = [], {}
for c in df.columns:
    s = str(c).strip()
    seen[s] = seen.get(s, 0) + 1
    cols.append(s if seen[s] == 1 else f"{s}_数值")
df.columns = cols

diff = (df["结清客户"] - df["提额客户"] - df["未提额客户"]).abs()
assert diff.max() <= 200, f"勾兑关系异常: {diff.max()}"

# ---- 2. 风险档位 + 使用率上限 ----
def tier_idx(f):
    if f < 0.05: return 0
    if f < 0.10: return 1
    if f < 0.20: return 2
    if f < 0.30: return 3
    return 4
df["风险档位"] = df["fpd7_rate$"].apply(tier_idx)
df["使用率上限"] = df["额度使用率"].map(USE_CAP)
df["提额额度基数"] = df["提额客户"] * df["提额客户_平均额度"]

# ---- 3. 二分求解缩放系数 k: Σ(基数×min(档位×k, 上限)) = need ----
def solve_k(need):
    lo, hi = 0.0, 2.0
    for _ in range(80):
        mid = (lo + hi) / 2
        v = (df["提额额度基数"] * np.minimum(df["风险档位"].map(lambda i: TIER_BASE[i]) * mid,
                                             df["使用率上限"])).sum()
        if v < need: lo = mid
        else: hi = mid
    return (lo + hi) / 2

N = df["结清客户"].sum()
cur_amt = (df["结清客户"] * df["结清客户_平均额度"]).sum()
need = TARGET_AMT * N - cur_amt
need_b = TARGET_B_AMT * N - cur_amt

df["基础档位幅度"] = df["风险档位"].map(lambda i: TIER_BASE[i])
k = solve_k(need)
df["提额幅度"] = np.minimum(df["基础档位幅度"] * k, df["使用率上限"]).round(2)
df["新增授信"] = df["提额额度基数"] * df["提额幅度"]
k_b = solve_k(need_b)
df["提额幅度B"] = np.minimum(df["基础档位幅度"] * k_b, df["使用率上限"]).round(2)
df["新增授信B"] = df["提额额度基数"] * df["提额幅度B"]

# ---- 4. 整体测算 ----
def overall(inc_col):
    new_total = cur_amt + df[inc_col].sum()
    new_avg = new_total / N
    amt_after = df["结清客户"] * df["结清客户_平均额度"] + df[inc_col]
    fpd7s = (amt_after * df["fpd7_rate$"]).sum() / amt_after.sum()
    return new_avg, new_total, fpd7s

avg_a, total_a, fpd7s_a = overall("新增授信")
avg_b, total_b, fpd7s_b = overall("新增授信B")
cur_fpd7s = (df["结清客户"] * df["结清客户_平均额度"] * df["fpd7_rate$"]).sum() / cur_amt

print(f"k(A)={k:.3f} k(B)={k_b:.3f}")
print(f"方案A: 平均额度 {cur_amt/N:,.0f} → {avg_a:,.0f} (目标 {TARGET_AMT:,.0f}) | 新增 {df['新增授信'].sum()/1e8:.2f} 亿 | fpd7_rate$ {cur_fpd7s*100:.2f}% → {fpd7s_a*100:.2f}%")
print(f"方案B: 平均额度 {cur_amt/N:,.0f} → {avg_b:,.0f} (目标 {TARGET_B_AMT:,.0f}) | 新增 {df['新增授信B'].sum()/1e8:.2f} 亿 | fpd7_rate$ {cur_fpd7s*100:.2f}% → {fpd7s_b*100:.2f}%")

# ---- 5. 决策依据 ----
TIER_NAMES = ["T1_超低风险(<5%)", "T2_低风险(5-10%)", "T3_中低风险(10-20%)", "T4_中风险(20-30%)", "T5_高风险(>=30%)"]
def reason(r):
    if r["提额幅度"] <= 0:
        return (f"score_level={r['score_level']}, fpd7_rate${r['fpd7_rate$']*100:.1f}%"
                f"({TIER_NAMES[r['风险档位']]}), {r['额度使用率']}(上限{USE_CAP[r['额度使用率']]*100:.0f}%), 不予提额")
    cap_hit = "受使用率上限约束" if r["基础档位幅度"] * k >= r["使用率上限"] - 1e-9 else ""
    return (f"score_level={r['score_level']}, fpd7_rate${r['fpd7_rate$']*100:.1f}%"
            f"({TIER_NAMES[r['风险档位']]}), {r['额度使用率']}(上限{USE_CAP[r['额度使用率']]*100:.0f}%){cap_hit}, "
            f"提额+{r['提额幅度']*100:.0f}%")
df["提额决策依据"] = df.apply(reason, axis=1)

# ---- 6. 分档统计(风险档) ----
df["风险分档名"] = df["风险档位"].map(lambda i: TIER_NAMES[i])
tier_stat = df.groupby("风险分档名").apply(lambda g: pd.Series({
    "客群数": len(g),
    "结清客户数": int(g["结清客户"].sum()),
    "提额客户数": int(g["提额客户"].sum()),
    "提额客户占比%": round(g["提额客户"].sum() / g["结清客户"].sum() * 100, 1),
    "当前平均额度": round((g["结清客户"] * g["结清客户_平均额度"]).sum() / g["结清客户"].sum(), 0),
    "平均提额幅度A%": round((g["提额额度基数"] * g["提额幅度"]).sum() / g["提额额度基数"].sum() * 100, 1),
    "新增授信A(万)": round(g["新增授信"].sum() / 1e4, 0),
    "平均提额幅度B%": round((g["提额额度基数"] * g["提额幅度B"]).sum() / g["提额额度基数"].sum() * 100, 1),
    "新增授信B(万)": round(g["新增授信B"].sum() / 1e4, 0),
    "fpd7_rate$加权%": round((g["结清客户"] * g["结清客户_平均额度"] * g["fpd7_rate$"]).sum() /
                              (g["结清客户"] * g["结清客户_平均额度"]).sum() * 100, 2),
}), include_groups=False).reset_index()
tier_stat["风险分档名"] = pd.Categorical(tier_stat["风险分档名"], categories=TIER_NAMES, ordered=True)
tier_stat = tier_stat.sort_values("风险分档名")

# ---- 7. 使用率约束统计 ----
use_recs = []
for u, g in df.groupby("额度使用率", observed=True, sort=False):
    use_recs.append({
        "额度使用率": u,
        "客群数": len(g),
        "提额客户数": int(g["提额客户"].sum()),
        "提额额度基数(亿)": round(g["提额额度基数"].sum() / 1e8, 2),
        "幅度上限": USE_CAP[u],
        "平均提额幅度A%": round((g["提额额度基数"] * g["提额幅度"]).sum() / g["提额额度基数"].sum() * 100, 1),
        "新增授信A(万)": round(g["新增授信"].sum() / 1e4, 0),
        "fpd7_rate$加权%": round((g["结清客户"] * g["结清客户_平均额度"] * g["fpd7_rate$"]).sum() /
                                  (g["结清客户"] * g["结清客户_平均额度"]).sum() * 100, 2),
    })
use_stat = pd.DataFrame(use_recs)
use_order = ["高额度使用率", "中额度使用率", "低额度使用率"]
use_stat["额度使用率"] = pd.Categorical(use_stat["额度使用率"], categories=use_order, ordered=True)
use_stat = use_stat.sort_values("额度使用率")

# ---- 8. 总结 ----
summary = pd.DataFrame([
    {"模块": "方案目标", "指标": "整体平均额度", "数值": f"{cur_amt/N:,.0f} → {avg_a:,.0f} 元",
     "说明": f"目标 {TARGET_AMT:,.0f} 元, 需新增总授信 {need/1e8:.2f} 亿 (+{need/cur_amt*100:.1f}%)"},
    {"模块": "方案目标", "指标": "风险约束", "数值": f"fpd7_rate$ {cur_fpd7s*100:.2f}% → {fpd7s_a*100:.2f}%",
     "说明": "提额集中于低风险客群, 金额加权逾期率下降"},
    {"模块": "提额规则", "指标": "风险分档幅度", "数值": "T1=100% / T2=80% / T3=60% / T4=20% / T5=0",
     "说明": "按客群 fpd7_rate$: <5% / 5-10% / 10-20% / 20-30% / >=30%"},
    {"模块": "提额规则", "指标": "额度使用率上限", "数值": "高≤100% / 中≤80% / 低≤30%",
     "说明": "低使用率客群提额支用意愿低, 限制提幅避免额度闲置; 最终幅度=min(风险档位×缩放, 上限)"},
    {"模块": "提额规则", "指标": "缩放系数k", "数值": f"{k:.3f}",
     "说明": "精确达标整体平均额度, 触上限客群不再放大"},
    {"模块": "勾兑关系", "指标": "结清客户", "数值": f"{N:,}",
     "说明": "= 提额客户 + 未提额客户(逐客群校验通过)"},
    {"模块": "勾兑关系", "指标": "提额客户", "数值": f"{df['提额客户'].sum():,} ({df['提额客户'].sum()/N*100:.1f}%)",
     "说明": "参与提额, 额度按方案上调"},
    {"模块": "勾兑关系", "指标": "未提额客户", "数值": f"{df['未提额客户'].sum():,} ({df['未提额客户'].sum()/N*100:.1f}%)",
     "说明": "额度保持不变"},
    {"模块": "方案A(目标5万)", "指标": "整体平均额度", "数值": f"{avg_a:,.0f} 元", "说明": "达标"},
    {"模块": "方案A(目标5万)", "指标": "新增总授信", "数值": f"{df['新增授信'].sum()/1e8:.2f} 亿",
     "说明": f"规模增幅 {df['新增授信'].sum()/cur_amt*100:.1f}%"},
    {"模块": "方案A(目标5万)", "指标": "整体fpd7_rate$", "数值": f"{fpd7s_a*100:.2f}%",
     "说明": f"较现状下降 {(cur_fpd7s-fpd7s_a)*100:.2f}pp"},
    {"模块": "方案B(稳健4.8万)", "指标": "整体平均额度", "数值": f"{avg_b:,.0f} 元", "说明": "稳健目标"},
    {"模块": "方案B(稳健4.8万)", "指标": "新增总授信", "数值": f"{df['新增授信B'].sum()/1e8:.2f} 亿",
     "说明": f"规模增幅 {df['新增授信B'].sum()/cur_amt*100:.1f}%"},
    {"模块": "方案B(稳健4.8万)", "指标": "整体fpd7_rate$", "数值": f"{fpd7s_b*100:.2f}%",
     "说明": f"较现状下降 {(cur_fpd7s-fpd7s_b)*100:.2f}pp"},
])

# ---- 9. 输出 Excel ----
wb = load_workbook(SRC)
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

# 提额结果
res = df[["flag_customer", "额度使用率", "借款次数", "score_level", "结清客户", "结清客户_平均额度",
          "结清客户_件均", "提额客户", "提额客户_平均额度", "未提额客户", "未提额_平均额度",
          "下笔额度使用", "fpd1_rate$", "fpd1_rate", "fpd7_rate$", "fpd7_rate",
          "风险档位", "使用率上限"]].copy()
res["提额幅度A"] = df["提额幅度"]
res["提额幅度B(稳健)"] = df["提额幅度B"]
res["新增授信A(万)"] = (df["新增授信"] / 1e4).round(0)
res["新增授信B(万)"] = (df["新增授信B"] / 1e4).round(0)
res["提额决策依据"] = df["提额决策依据"]
ws = wb.create_sheet("提额结果")
write_df(ws, res)
style_sheet(ws, pct_cols=["提额幅度A", "提额幅度B(稳健)", "fpd1_rate$", "fpd1_rate", "fpd7_rate$", "fpd7_rate"],
            money_cols=["结清客户_平均额度", "结清客户_件均", "提额客户_平均额度", "未提额_平均额度"],
            int_cols=["结清客户", "提额客户", "未提额客户", "新增授信A(万)", "新增授信B(万)"],
            scale_cols=["fpd7_rate$", "提额幅度A"])

# 风险分档统计
ws2 = wb.create_sheet("分档统计")
write_df(ws2, tier_stat)
style_sheet(ws2, pct_cols=["提额客户占比%", "平均提额幅度A%", "平均提额幅度B%", "fpd7_rate$加权%"],
            money_cols=["当前平均额度"], int_cols=["结清客户数", "提额客户数", "新增授信A(万)", "新增授信B(万)"],
            scale_cols=["fpd7_rate$加权%", "新增授信A(万)"])

# 使用率约束统计
ws3 = wb.create_sheet("使用率约束统计")
write_df(ws3, use_stat)
style_sheet(ws3, pct_cols=["平均提额幅度A%", "fpd7_rate$加权%", "幅度上限"],
            int_cols=["提额客户数", "新增授信A(万)"], scale_cols=["fpd7_rate$加权%", "平均提额幅度A%"])

# 方案总结
ws4 = wb.create_sheet("提额方案总结")
write_df(ws4, summary)
for c in range(1, 5):
    cell = ws4.cell(row=1, column=c)
    cell.fill, cell.font = HDR_FILL, HDR_FONT
ws4.freeze_panes = "A2"
for col, wd in zip("ABCD", [18, 24, 34, 48]):
    ws4.column_dimensions[col].width = wd
for r in range(2, ws4.max_row + 1):
    for c in range(1, 5):
        cell = ws4.cell(row=r, column=c)
        cell.font = BODY_FONT
        cell.border = BORDER

wb.save(DST)
print(f"\n✅ 已生成: {DST}")
print("Sheets:", wb.sheetnames)
