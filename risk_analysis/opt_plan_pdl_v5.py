# -*- coding: utf-8 -*-
"""PDL 提额方案 盖帽版 —— 高280%/中260%/低60% + 风险系数矩阵 + 每格提幅盖帽(系数盖帽) + 每格提额盖帽(额度盖帽)
核心结论: 源表自带每格 系数盖帽(0~1.5)/额度盖帽(3万~50万), 为硬约束;
          v4 的 300% 提幅/50万 全局盖帽过宽, 110/120 格子实际超盖帽;
          加盖帽后 5万目标不可达(满档位平均 44,986), 本版为盖帽约束下的最优解 + 放宽情景分析。
"""
import warnings; warnings.filterwarnings("ignore")
import pandas as pd, numpy as np, os
from openpyxl import load_workbook
from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
from openpyxl.utils import get_column_letter
from openpyxl.formatting.rule import ColorScaleRule

SRC = "PDL提额系数20260814.xlsx"
DST = "PDL提额方案-盖帽版-20260814.xlsx"
TARGET_AMT = 50000.0
USE_BASE = {"高额度使用率": 2.8, "中额度使用率": 2.6, "低额度使用率": 0.6}
RISK_COEF = [
    (0.02, 1.00, "T1_<2%"), (0.04, 0.95, "T2_2-4%"), (0.06, 0.90, "T3_4-6%"),
    (0.08, 0.85, "T4_6-8%"), (0.10, 0.80, "T5_8-10%"), (0.15, 0.70, "T6_10-15%"),
    (0.20, 0.60, "T7_15-20%"), (0.25, 0.50, "T8_20-25%"), (0.30, 0.40, "T9_25-30%"),
    (np.inf, 0.30, "T10_>=30%"),
]
def rc_of(f):
    for cap, c, _ in RISK_COEF:
        if f < cap:
            return c
    return 0.30
def tier_of(f):
    for cap, _, n in RISK_COEF:
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

# ---- 2. 资格 & 盖帽参数 ----
df["等级可提"] = df["评级"].isin(["A", "B", "C"]) | ((df["评级"] == "D") & (df["fpd7_rate$"] < cur_fpd7))
df["是否可提额"] = df["等级可提"]
df["风险档"] = df["fpd7_rate$"].apply(tier_of)
df["风险系数"] = df["fpd7_rate$"].apply(rc_of)
df["使用率基础"] = df["use_rate_group"].map(USE_BASE)
df["提幅盖帽"] = df["系数盖帽"]            # 每格提幅盖帽(硬约束)
df["提额盖帽"] = df["额度盖帽"]            # 每格提额盖帽(硬约束)
# 系数盖帽=0 视为不可提额(与 D/E 高风险重叠)
df["是否可提额"] = df["是否可提额"] & (df["提幅盖帽"] > 0)

# ---- 3. 计算: 提幅 = min(使用率基础×风险系数×k, 提幅盖帽); 后额度 = min(原×(1+提幅), 提额盖帽) ----
# 满档位: k 取到所有可提格子全部触顶的临界值 → 盖帽约束下的最优解
k_star = float(np.max(df.loc[df["是否可提额"], "提幅盖帽"] / (df["使用率基础"] * df["风险系数"]))) if df["是否可提额"].any() else 1.0
k_star = min(k_star, 3.0)
print(f"满档位临界缩放 k*={k_star:.3f} (所有可提格子触顶)")

def compute(k=1.0):
    base = df["使用率基础"] * df["风险系数"] * k
    amp = np.where(df["是否可提额"], np.minimum(base, df["提幅盖帽"]), 0.0)
    new_per = np.minimum(df["提额客户_平均额度"] * (1 + amp), df["提额盖帽"])
    inc = df["提额客户"] * np.maximum(0, new_per - df["提额客户_平均额度"])
    return amp, new_per, inc

amp, new_per, inc = compute(k_star)
avg = (cur_amt + inc.sum()) / N
touch = (df["是否可提额"] & (df["使用率基础"] * df["风险系数"] * k_star >= df["提幅盖帽"] - 1e-9)).sum()
print(f"方案[满档位k*={k_star:.3f}]: 新增 {inc.sum()/1e8:.2f} 亿 | 平均额度 {avg:,.0f} | "
      f"最大提幅 {np.max(np.where(df['是否可提额'], amp, 0))*100:.0f}% | 触顶格子 {touch}/{df['是否可提额'].sum()}")
print(f"⚠️  目标 {TARGET_AMT:,.0f} 不可达: 缺口 {(TARGET_AMT-avg):,.0f} 元/人, 需新增 {need/1e8:.2f} 亿, 盖帽约束下最多 {inc.sum()/1e8:.2f} 亿")

amp1, new_per1, inc1 = compute(1.0)
avg1 = (cur_amt + inc1.sum()) / N
print(f"对照[k=1.0公式]: 新增 {inc1.sum()/1e8:.2f} 亿 | 平均 {avg1:,.0f} (9格未触顶, 差 {(avg-avg1):,.0f} 元/人)")

df["方案幅度"] = amp
df["方案后额度"] = new_per
df["方案新增"] = inc
df["方案新增(万)"] = (inc / 1e4).round(0)
df["是否触顶"] = df["是否可提额"] & (df["使用率基础"] * df["风险系数"] * k_star >= df["提幅盖帽"] - 1e-9)

# 放宽情景: 系数盖帽×m 下的满档位可达平均额度(额度盖帽仍生效), 并求达标所需最小倍数
# 语义: 盖帽放宽后全部可提格子打满新盖帽
def scenario(m):
    amp_s = np.where(df["是否可提额"], df["提幅盖帽"] * m, 0.0)
    new_s = np.minimum(df["提额客户_平均额度"] * (1 + amp_s), df["提额盖帽"])
    inc_s = df["提额客户"] * np.maximum(0, new_s - df["提额客户_平均额度"])
    avg_s = (cur_amt + inc_s.sum()) / N
    return inc_s.sum() / 1e8, avg_s

scn_rows = []
for m in [1.0, 1.2, 1.5, 2.0, 2.5, 3.0]:
    inc_s, avg_s = scenario(m)
    scn_rows.append({"提幅盖帽倍数": f"×{m:.1f}", "新增(亿)": round(inc_s, 2),
                     "平均额度": round(avg_s, 0),
                     "达标5万": "✅" if avg_s >= TARGET_AMT else "✗",
                     "说明": ""})
# 求达标最小倍数(在额度盖帽仍生效前提下)
if scenario(3.0)[1] >= TARGET_AMT:
    lo, hi = 1.0, 3.0
    for _ in range(60):
        mid = (lo + hi) / 2
        if scenario(mid)[1] >= TARGET_AMT:
            hi = mid
        else:
            lo = mid
    m_need = (lo + hi) / 2
    scn_rows.append({"提幅盖帽倍数": f"×{m_need:.2f}(达标线)", "新增(亿)": round(scenario(m_need)[0], 2),
                     "平均额度": round(TARGET_AMT, 0), "达标5万": "✅",
                     "说明": "整体放宽系数盖帽至此倍数即可恢复5万目标(额度盖帽不变)"})
else:
    scn_rows.append({"提幅盖帽倍数": ">×3.0", "新增(亿)": round(scenario(3.0)[0], 2),
                     "平均额度": round(scenario(3.0)[1], 0), "达标5万": "✗",
                     "说明": "放宽至×3.0仍不足, 需同步调整额度盖帽或目标"})
scn_df = pd.DataFrame(scn_rows)

# ---- 4. 决策依据 ----
def reason(r):
    if not r["是否可提额"]:
        if r["评级"] == "E":
            return f"评级=E, 系数盖帽{r['提幅盖帽']:.1f}, 不予提额"
        return (f"评级={r['评级']}, fpd7_rate${r['fpd7_rate$']*100:.1f}%≥大盘{cur_fpd7*100:.1f}%, "
                f"系数盖帽{r['提幅盖帽']:.1f}, 不予提额")
    return (f"评级={r['评级']}, fpd7_rate${r['fpd7_rate$']*100:.1f}%({r['风险档']}), {r['use_rate_group']}"
            f"(基础{USE_BASE[r['use_rate_group']]*100:.0f}%)×风险系数{r['风险系数']:.2f}→公式提幅{r['使用率基础']*r['风险系数']*100:.0f}%, "
            f"提幅盖帽截断至{r['方案幅度']*100:.0f}%{'【触顶】' if r['是否触顶'] else '(未触顶)'}, "
            f"提额后额度{r['方案后额度']:,.0f}元(提额盖帽{r['提额盖帽']:,.0f})")
df["提额决策依据"] = df.apply(reason, axis=1)

# ---- 5. 整体指标 ----
amt_after = df["结清客户"] * df["平均额度"] + df["方案新增"]
fpd7_after = (amt_after * df["fpd7_rate$"]).sum() / amt_after.sum()

# ---- 6. 提幅矩阵(盖帽后实际幅度) ----
order = [t[2] for t in RISK_COEF]
matrix_rows = []
for u in ["高额度使用率", "中额度使用率", "低额度使用率"]:
    row = {"使用率": u, "基础档%": USE_BASE[u] * 100}
    for tg in order:
        sub = df[(df["use_rate_group"] == u) & (df["风险档"] == tg) & df["是否可提额"]]
        if len(sub):
            row[tg] = round((sub["提额客户"] * sub["方案幅度"]).sum() / sub["提额客户"].sum() * 100, 0)
        else:
            row[tg] = None
    matrix_rows.append(row)
matrix_df = pd.DataFrame(matrix_rows)

# ---- 7. 思路 sheet ----
idea = pd.DataFrame([
    {"模块": "方案目标", "内容": f"整体平均额度目标 {TARGET_AMT:,.0f} 元; 但受每格提幅/提额盖帽硬约束, 满档位最大可达 44,986 元, 目标需下调或放宽盖帽(见敏感性)"},
    {"模块": "提额资格", "内容": f"评级 A/B/C 全部 + D级且客群fpd7_rate$<大盘({cur_fpd7*100:.2f}%)可提额; 系数盖帽=0 的格子一律不提额(全部落在D/E高风险)"},
    {"模块": "提额原则①", "内容": "额度使用率优先(使用意愿): 高280% > 中260% > 低60% 作为公式基础档"},
    {"模块": "提额原则②", "内容": "风险档调节: 客群fpd7_rate$分10档, 风险系数×1.00(超低风险)~×0.30(高风险)"},
    {"模块": "提幅盖帽限制", "内容": "每格提幅 = min(使用率基础×风险系数, 系数盖帽); 源表系数盖帽 0~1.5(高使用率A≈1.15/中A≈0.65/低A≈0.45, 随评级与风险递减), 110/120 格子被盖帽截断, 最大实际提幅 150%"},
    {"模块": "提额盖帽限制", "内容": "提额后额度 = min(原额度×(1+提幅), 额度盖帽); 源表额度盖帽 3万~50万(5个低额度格子为3万~10万), 满档位下均未超限, 作为第二道保险"},
    {"模块": "提额公式", "内容": f"提幅 = min(使用率基础档 × 风险系数 × k(满档位缩放), 系数盖帽); 提额后额度 = min(原额度×(1+提幅), 额度盖帽); 满档位 k={k_star:.3f} 使所有可提格子全部触顶, 即盖帽约束下最优"},
    {"模块": "达标测算", "内容": f"满档位(全部触顶)新增 {inc.sum()/1e8:.2f} 亿(+{inc.sum()/cur_amt*100:.1f}%), 平均额度 {avg:,.0f}元, fpd7_rate$ {cur_fpd7*100:.2f}%→{fpd7_after*100:.2f}%; 距5万目标差 {(TARGET_AMT-avg):,.0f} 元/人"},
    {"模块": "放宽建议", "内容": f"如需恢复5万目标, 需将系数盖帽整体放宽至 {scn_df.iloc[-1]['提幅盖帽倍数']} 或调整目标; 放宽额度盖帽(3万~10万格子)影响甚微"},
])

# ---- 8. 汇总 ----
summary = pd.DataFrame([
    {"模块": "方案目标", "指标": "整体平均额度", "数值": f"{cur_amt/N:,.0f} → {avg:,.0f} 元",
     "说明": f"目标 {TARGET_AMT:,.0f} 元 ❌ 不可达(盖帽硬约束), 缺口 {(TARGET_AMT-avg):,.0f} 元/人; 满档位为盖帽约束下最优"},
    {"模块": "约束规则", "指标": "提额客群范围", "数值": "A/B/C 全部 + D级低风险",
     "说明": f"D级且fpd7_rate$<大盘{cur_fpd7*100:.1f}%可提额; E级({df.loc[df['评级']=='E','提额客户'].sum():,})及D级高风险({df.loc[(df['评级']=='D')&~df['等级可提'],'提额客户'].sum():,})不予提额"},
    {"模块": "提幅盖帽", "指标": "每格系数盖帽", "数值": "0 ~ 150%",
     "说明": f"110/120 格被截断(原公式超盖帽); 触顶格子 {touch} 个, 未触顶 {int(df['是否可提额'].sum())-touch} 个; 满档位最大提幅 {np.max(np.where(df['是否可提额'], amp, 0))*100:.0f}%"},
    {"模块": "提额盖帽", "指标": "每格额度盖帽", "数值": "3万 ~ 50万",
     "说明": "115格50万; 低额度5格3万~10万; 满档位下均未超限(第二道保险, 防放宽后爆额度)"},
    {"模块": "提幅规则", "指标": "额度使用率优先", "数值": "高280% / 中260% / 低60%",
     "说明": "仅作用于未触顶格子; 触顶格子幅度=系数盖帽(盖帽已内嵌使用意愿×风险排序)"},
    {"模块": "提幅规则", "指标": "风险档系数", "数值": "10档 ×1.00 ~ ×0.30",
     "说明": "T1<2%×1.00 / T3 4-6%×0.90 / T5 8-10%×0.80 / T7 15-20%×0.60 / T9 25-30%×0.40 / T10>=30%×0.30"},
    {"模块": "勾兑关系", "指标": "结清/提额/未提额", "数值": f"{N:,} = {df['提额客户'].sum():,} + {df['未提额客户'].sum():,}",
     "说明": "勾兑校验通过, 未提额客户额度保持不变"},
    {"模块": "方案(盖帽满档)", "指标": "整体平均额度", "数值": f"{avg:,.0f} 元", "说明": "盖帽约束下的最优解"},
    {"模块": "方案(盖帽满档)", "指标": "新增总授信", "数值": f"{inc.sum()/1e8:.2f} 亿", "说明": f"规模增幅 {inc.sum()/cur_amt*100:.1f}%"},
    {"模块": "方案(盖帽满档)", "指标": "整体fpd7_rate$", "数值": f"{fpd7_after*100:.2f}%",
     "说明": f"现状 {cur_fpd7*100:.2f}%, 降低 {(cur_fpd7-fpd7_after)*100:.2f}pp (相对{(cur_fpd7-fpd7_after)/cur_fpd7*100:.1f}%)"},
    {"模块": "恢复5万目标", "指标": "所需放宽", "数值": scn_df.iloc[-1]["提幅盖帽倍数"],
     "说明": "将源表系数盖帽整体放大至该倍数(额度盖帽不变)即可达标; 或下调目标至44,986"},])

# ---- 9. 输出 Excel ----
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

# 提额思路
ws_i = wb.create_sheet("提额思路")
write_df(ws_i, idea)
for c in range(1, 3):
    cell = ws_i.cell(row=1, column=c)
    cell.fill, cell.font = HDR_FILL, HDR_FONT
ws_i.freeze_panes = "A2"
ws_i.column_dimensions["A"].width = 16
ws_i.column_dimensions["B"].width = 95
for r in range(2, ws_i.max_row + 1):
    ws_i.cell(row=r, column=1).font = Font(name="微软雅黑", size=9, bold=True)
    ws_i.cell(row=r, column=2).font = BODY_FONT
    for c in range(1, 3):
        ws_i.cell(row=r, column=c).border = BORDER

# 提幅矩阵
ws_m = wb.create_sheet("提幅矩阵")
write_df(ws_m, matrix_df)
style_sheet(ws_m, pct_cols=[], money_cols=[], int_cols=["基础档%"])
for r in range(2, ws_m.max_row + 1):
    for c in range(3, ws_m.max_column + 1):
        cell = ws_m.cell(row=r, column=c)
        if isinstance(cell.value, (int, float)):
            cell.number_format = "0%"
            if cell.value >= 1.0:
                cell.fill = PatternFill("solid", fgColor="FDE8E8")
            elif cell.value >= 0.5:
                cell.fill = PatternFill("solid", fgColor="FFF3CD")
            else:
                cell.fill = PatternFill("solid", fgColor="E7F6EE")

# 提额结果
res = df[["flag_customer", "use_rate_group", "借款次数", "评级", "结清客户", "额度使用率",
          "件均", "平均额度", "提额客户", "提额客户_平均额度", "提额客户_提额后平均",
          "未提额客户", "未提额_额度件均", "未提额客户_提后件均", "发起下一笔订单",
          "fpd1_fm_dd", "fpd7_fm_dd", "fpd1_rate", "fpd1_rate$", "fpd7_rate", "fpd7_rate$",
          "提幅盖帽", "提额盖帽", "风险档", "风险系数", "使用率基础", "是否可提额", "是否触顶",
          "方案幅度", "方案后额度", "方案新增(万)", "提额决策依据"]].copy()
ws = wb.create_sheet("提额结果")
write_df(ws, res)
style_sheet(ws, pct_cols=["方案幅度", "风险系数", "使用率基础", "fpd1_rate", "fpd1_rate$", "fpd7_rate", "fpd7_rate$", "提幅盖帽"],
            money_cols=["平均额度", "件均", "提额客户_平均额度", "提额客户_提额后平均", "未提额_额度件均",
                        "未提额客户_提后件均", "提额盖帽", "方案后额度"],
            int_cols=["结清客户", "提额客户", "未提额客户", "发起下一笔订单", "fpd1_fm_dd", "fpd7_fm_dd", "方案新增(万)"],
            scale_cols=["fpd7_rate$", "方案幅度", "方案后额度"])

# 分档统计
tier_recs = []
for rn, g in df.groupby("风险档", observed=True, sort=False):
    tier_recs.append({
        "风险档": rn, "客群数": len(g),
        "结清客户数": int(g["结清客户"].sum()),
        "提额客户数": int(g["提额客户"].sum()),
        "风险系数": g["风险系数"].iloc[0],
        "平均提幅盖帽%": round((g["提额客户"] * g["提幅盖帽"]).sum() / g["提额客户"].sum() * 100, 0) if g["提额客户"].sum() else 0,
        "方案平均幅度%": round((g["提额客户"] * g["方案幅度"]).sum() / g["提额客户"].sum() * 100, 0) if g["提额客户"].sum() else 0,
        "方案新增(万)": round(g["方案新增"].sum() / 1e4, 0),
        "fpd7_rate$加权%": round((g["结清客户"] * g["平均额度"] * g["fpd7_rate$"]).sum() /
                                  (g["结清客户"] * g["平均额度"]).sum() * 100, 2),
    })
tier_stat = pd.DataFrame(tier_recs)
tier_stat["风险档"] = pd.Categorical(tier_stat["风险档"], categories=order, ordered=True)
tier_stat = tier_stat.sort_values("风险档")
ws2 = wb.create_sheet("分档统计")
write_df(ws2, tier_stat)
style_sheet(ws2, pct_cols=["风险系数", "平均提幅盖帽%", "方案平均幅度%", "fpd7_rate$加权%"],
            int_cols=["结清客户数", "提额客户数", "方案新增(万)"], scale_cols=["fpd7_rate$加权%", "方案新增(万)"])

# 盖帽敏感性
ws3 = wb.create_sheet("盖帽敏感性")
write_df(ws3, scn_df)
style_sheet(ws3, money_cols=["平均额度"], int_cols=["新增(亿)"])
ws3.column_dimensions["A"].width = 20
ws3.column_dimensions["D"].width = 10
ws3.column_dimensions["E"].width = 50

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
