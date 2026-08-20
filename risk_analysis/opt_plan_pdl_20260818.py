# -*- coding: utf-8 -*-
"""PDL 提额方案测算 20260818 —— Sheet2 策略盖帽(提幅/额度) 匹配 Sheet3 提额结果
约束: 提额幅度 = min(系数盖帽[Sheet2.提幅, 直接生效不放大],
                     使用率盖帽[低额度使用率≤50%, 高/中不限制],
                     额度盖帽换算上限[(额度盖帽-提额客户_平均额度)/提额客户_平均额度])
提额后额度 = min(提额客户_平均额度×(1+最终提幅), 额度盖帽); 未提额客户额度保持不变
"""
import warnings; warnings.filterwarnings("ignore")
import pandas as pd, numpy as np
from openpyxl import load_workbook
from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
from openpyxl.utils import get_column_letter
from openpyxl.formatting.rule import ColorScaleRule

SRC = "PDL提额分析样本20260818.xlsx"
DST = "PDL提额方案-20260818.xlsx"

# 使用率盖帽: 低额度使用率提额系数最高50%; 高/中额度使用率不额外限制(系数盖帽直接生效)
# 若需对高/中再加档位, 修改此字典即可, 如 {"高额度使用率": 1.2, "中额度使用率": 1.0, "低额度使用率": 0.5}
USE_CAP = {"高额度使用率": np.inf, "中额度使用率": np.inf, "低额度使用率": 0.5}
KEYS = ["flag_customer", "额度使用率", "借款次数", "ng_loancnt_bin"]

def norm_cols(df):
    cols, seen = [], {}
    for c in df.columns:
        s = str(c).strip()
        seen[s] = seen.get(s, 0) + 1
        cols.append(s if seen[s] == 1 else f"{s}_dup{seen[s]}")
    df.columns = cols
    return df

# ---- 1. 读数据 ----
s2 = norm_cols(pd.read_excel(SRC, "Sheet2"))
s3 = norm_cols(pd.read_excel(SRC, "Sheet3"))
assert (s2["结清客户"] - s2["提额客户"] - s2["未提额客户"]).abs().max() == 0, "Sheet2 勾兑失败"
assert (s3["结清客户"] - s3["提额客户"] - s3["未提额客户"]).abs().max() == 0, "Sheet3 勾兑失败"

# ---- 2. 匹配策略盖帽到 Sheet3 ----
df = s3.merge(s2[KEYS + ["提幅", "额度"]], on=KEYS, how="left", validate="one_to_one")
assert df["提幅"].notna().all(), "存在未匹配到策略盖帽的格子"

# ---- 3. 约束计算 ----
df["提额客户_平均额度"] = df["提额客户_平均额度"].fillna(0.0)   # 3格提额客户=0, 无均值
df["系数盖帽"] = df["提幅"]                                   # 提幅盖帽(按评级给定, 直接生效)
df["额度盖帽"] = df["额度"]                                   # 额度盖帽(元)
df["使用率盖帽"] = df["额度使用率"].map(USE_CAP)              # 使用率盖帽
# 额度盖帽折算为幅度上限(提额客户=0 的格子无客户可提, 上限置0)
q0 = df["提额客户_平均额度"] > 0
df["额度盖帽换算上限"] = np.where(q0, (df["额度盖帽"] - df["提额客户_平均额度"]) / df["提额客户_平均额度"], 0.0)
df["额度盖帽换算上限"] = df["额度盖帽换算上限"].clip(lower=0.0)
# 最终提幅 = min(系数盖帽, 使用率盖帽, 额度盖帽换算上限)
df["最终提幅"] = df[["系数盖帽", "使用率盖帽", "额度盖帽换算上限"]].min(axis=1)
df["最终提幅"] = df["最终提幅"].clip(lower=0.0)
# 提额后额度 = min(原×(1+最终提幅), 额度盖帽); 新增 = 提额客户 × (后-原)
df["提额后额度"] = np.minimum(df["提额客户_平均额度"] * (1 + df["最终提幅"]), df["额度盖帽"])
df["提额新增"] = df["提额客户"] * np.maximum(0.0, df["提额后额度"] - df["提额客户_平均额度"])
df["提额新增(万)"] = (df["提额新增"] / 1e4).round(0)

# 触发约束识别
def cap_source(r):
    parts = [f"系数盖帽{int(round(r['系数盖帽']*100))}%"]
    if np.isfinite(r["使用率盖帽"]) and r["最终提幅"] >= r["使用率盖帽"] - 1e-9:
        parts.append(f"使用率盖帽{int(round(r['使用率盖帽']*100))}%")
    if r["最终提幅"] >= r["额度盖帽换算上限"] - 1e-9:
        parts.append(f"额度盖帽{int(round(r['额度盖帽换算上限']*100))}%")
    return "+".join(parts)

df["决策说明"] = df.apply(lambda r: (
    f"该格提额客户=0, 无提额动作" if r["提额客户"] == 0 else (
    f"评级{r['ng_loancnt_bin']} {r['flag_customer']} {r['额度使用率']} 借款{r['借款次数']}次: "
    f"提幅=min({cap_source(r)})={r['最终提幅']*100:.0f}%, "
    f"后额度{int(round(r['提额后额度'])):,}元(盖帽{int(r['额度盖帽']):,}元), "
    f"人均新增{int(round(r['提额新增']/max(r['提额客户'],1))):,}元")), axis=1)

# ---- 4. 整体测算 ----
N = df["结清客户"].sum()
cur_amt = (df["结清客户"] * df["平均额度"]).sum()
cur_avg = cur_amt / N
tq = df["提额客户"].sum()
new_total = df["提额新增"].sum()
amt_after = df["结清客户"] * df["平均额度"] + df["提额新增"]
avg_after = amt_after.sum() / N
tq_amt_before = (df["提额客户"] * df["提额客户_平均额度"]).sum()
tq_amt_after = (df["提额客户"] * df["提额后额度"]).sum()
w_amp = new_total / tq_amt_before
per_tq = new_total / tq
print(f"结清客户 {N:,} | 提额客户 {tq:,} ({tq/N*100:.1f}%)")
print(f"当前平均额度 {cur_avg:,.0f} | 提额后 {avg_after:,.0f} (+{avg_after-cur_avg:,.0f}, +{(avg_after-cur_avg)/cur_avg*100:.1f}%)")
print(f"新增总授信 {new_total/1e8:.2f} 亿 (+{new_total/cur_amt*100:.1f}%) | 提额客户人均新增 {per_tq:,.0f} 元 | 加权平均提幅 {w_amp*100:.1f}%")

# ---- 5. 分组统计 ----
def group_stats(df, by, name):
    rows = []
    for k, g in df.groupby(by, observed=True, sort=False):
        if isinstance(k, tuple):
            k = "_".join(str(x) for x in k)
        n = g["结清客户"].sum()
        t = g["提额客户"].sum()
        a0 = (g["结清客户"] * g["平均额度"]).sum()
        a1 = (g["结清客户"] * g["平均额度"] + g["提额新增"]).sum()
        rows.append({name: k, "结清客户": int(n), "提额客户": int(t), "提额客户占比%": round(t / n * 100, 1),
                     "当前平均额度": round(a0 / n, 0), "提额后平均额度": round(a1 / n, 0),
                     "平均提升": round(a1 / n - a0 / n, 0),
                     "新增授信(万)": round(g["提额新增"].sum() / 1e4, 0),
                     "加权提幅%": round(g["提额新增"].sum() / (g["提额客户"] * g["提额客户_平均额度"]).sum() * 100, 1)
                     if (g["提额客户"] * g["提额客户_平均额度"]).sum() else 0})
    return pd.DataFrame(rows)

stat_groups = [
    (["ng_loancnt_bin"], "评级"),
    (["额度使用率"], "使用率"),
    (["借款次数"], "借款次数"),
    (["flag_customer"], "客群"),
    (["ng_loancnt_bin", "额度使用率"], "评级x使用率"),
]

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

# Sheet3_提额结果: 原 Sheet3 12列 + 方案列
res = df[KEYS + ["结清客户", "额度使用率_dup2", "件均", "平均额度", "提额客户", "提额客户_平均额度",
                 "未提额客户", "未提额_额度件均",
                 "系数盖帽", "额度盖帽", "使用率盖帽", "额度盖帽换算上限", "最终提幅",
                 "提额后额度", "提额新增(万)", "决策说明"]].copy()
res.columns = [KEYS[0], KEYS[1], KEYS[2], "评级", "结清客户", "额度使用率均值", "件均", "平均额度",
               "提额客户", "提额客户_平均额度", "未提额客户", "未提额_额度件均",
               "系数盖帽", "额度盖帽", "使用率盖帽", "额度盖帽换算上限", "最终提幅",
               "提额后额度", "提额新增(万)", "决策说明"]
ws = wb.create_sheet("Sheet3_提额结果")
write_df(ws, res)
style_sheet(ws, pct_cols=["系数盖帽", "使用率盖帽", "额度盖帽换算上限", "最终提幅"],
            money_cols=["件均", "平均额度", "提额客户_平均额度", "未提额_额度件均", "额度盖帽", "提额后额度"],
            int_cols=["结清客户", "提额客户", "未提额客户", "提额新增(万)"],
            scale_cols=["最终提幅", "提额后额度"])
ws.column_dimensions["T"].width = 80

# 约束触发统计(排除提额客户=0 的格子)
valid = df["提额客户"] > 0
use_cap_hit = int(((df["使用率盖帽"] < np.inf) & (df["最终提幅"] >= df["使用率盖帽"] - 1e-9)
                  & (df["系数盖帽"] > df["使用率盖帽"]) & valid).sum())
amt_cap_hit = int(((df["最终提幅"] >= df["额度盖帽换算上限"] - 1e-9)
                   & (df["系数盖帽"] > df["额度盖帽换算上限"]) & valid).sum())

# 测算汇总
summary = pd.DataFrame([
    {"指标": "结清客户数", "数值": f"{N:,}", "口径": "Sheet3 全部结清客户(=提额客户+未提额客户)"},
    {"指标": "提额客户数", "数值": f"{tq:,} ({tq/N*100:.1f}%)", "口径": "仅提额客户提额, 未提额客户额度保持不变"},
    {"指标": "整体平均额度", "数值": f"{cur_avg:,.0f} → {avg_after:,.0f} 元", "口径": f"提升 {avg_after-cur_avg:,.0f} 元 (+{(avg_after-cur_avg)/cur_avg*100:.1f}%)"},
    {"指标": "新增总授信", "数值": f"{new_total/1e8:.2f} 亿", "口径": f"规模增幅 +{new_total/cur_amt*100:.1f}%"},
    {"指标": "提额客户人均新增", "数值": f"{per_tq:,.0f} 元", "口径": f"加权平均提幅 {w_amp*100:.1f}%"},
    {"指标": "提额客户总额度", "数值": f"{tq_amt_before/1e8:.2f} 亿 → {tq_amt_after/1e8:.2f} 亿",
     "口径": f"提额客户额度增幅 +{(tq_amt_after/tq_amt_before-1)*100:.1f}%"},
    {"指标": "约束① 提幅盖帽", "数值": "Sheet2.提幅 直接生效(不放大)", "口径": "A档0.3~1.2 / B档0.2~1.0 / C档0.15~0.6 / D档0.1~0.2 / E档0~0.1"},
    {"指标": "约束② 额度盖帽", "数值": "10万/20万/30万", "口径": "折算幅度上限=(额度盖帽-提额客户_平均额度)/提额客户_平均额度"},
    {"指标": "约束③ 使用率盖帽", "数值": "低额度使用率≤50%; 高/中不限制", "口径": "同等风险评级下高使用率高系数、低使用率低系数(Sheet2提幅列已体现)"},
    {"指标": "约束生效情况", "数值": f"使用率盖帽压降 {use_cap_hit} 格 | 额度盖帽压降 {amt_cap_hit} 格 | 提额客户=0 无动作 {int((~valid).sum())} 格",
     "口径": "额度盖帽当前0触发: 提额客户_平均额度(2千~13万)远低于10万~30万盖帽, 换算上限均大于系数盖帽"},
])

ws_sum = wb.create_sheet("提额测算汇总")
write_df(ws_sum, summary)
for c in range(1, 4):
    cell = ws_sum.cell(row=1, column=c)
    cell.fill, cell.font = HDR_FILL, HDR_FONT
ws_sum.freeze_panes = "A2"
for col, wd in zip("ABC", [20, 42, 55]):
    ws_sum.column_dimensions[col].width = wd
for r in range(2, ws_sum.max_row + 1):
    for c in range(1, 4):
        cell = ws_sum.cell(row=r, column=c)
        cell.font = BODY_FONT
        cell.border = BORDER

# 分组统计
for cols, name in stat_groups:
    st = group_stats(df, cols, name)
    ws_g = wb.create_sheet(f"统计_{name}")
    write_df(ws_g, st)
    style_sheet(ws_g, pct_cols=["提额客户占比%", "加权提幅%"],
                money_cols=["当前平均额度", "提额后平均额度", "平均提升"],
                int_cols=["结清客户", "提额客户", "新增授信(万)"],
                scale_cols=["平均提升", "新增授信(万)"])

# 约束与说明
notes = pd.DataFrame([
    {"模块": "方案逻辑", "内容": "两阶段: ① 策略生成 = 基于 Sheet2 早期样本(48.3万结清)制定提额策略, 产物为每格 提幅(系数盖帽)+额度(额度盖帽), 直接生效不放大; ② 效果测算 = 将策略盖帽匹配到 Sheet3 最新样本(6.2万结清), 用最新客户数/额度计算实际提额效果(提幅/后额度/新增/平均额度)"},
    {"模块": "数据来源", "内容": "strage/PDL提额分析样本20260818.xlsx; Sheet2=早期样本(用于生成提额策略), Sheet3=最新样本(用于测算实际效果); 两表同分组结构(120格)"},
    {"模块": "测算口径", "内容": "测算基表=Sheet3 最新样本: 结清客户/提额客户/未提额客户/提额客户_平均额度/未提额_额度件均/件均/平均额度/额度使用率 全部取自 Sheet3; Sheet2 仅提供 提幅(系数盖帽)/额度(额度盖帽) 两列策略盖帽, 不参与任何客户数与额度计算"},
    {"模块": "勾兑关系", "内容": "结清客户 = 提额客户 + 未提额客户(两表勾兑均校验通过); 仅对提额客户提额, 未提额客户额度保持不变"},
    {"模块": "评级口径", "内容": "按风险分从低到高每20%分位一级, A(最优)~E(最差)五档, 每档24个分组(共120格)"},
    {"模块": "提额公式", "内容": "最终提幅 = min(系数盖帽[Sheet2.提幅], 使用率盖帽[低使用率≤50%], 额度盖帽换算上限[(额度盖帽-提额客户_平均额度)/提额客户_平均额度]); 提额后额度 = min(提额客户_平均额度×(1+最终提幅), 额度盖帽)"},
    {"模块": "风险提示", "内容": "提额分bin切分依据为 fpd7_rate$ 金额逾期率(Sheet2口径); 客户逾期率 fpd7_rate 与金额逾期率存在倒挂, 金额逾期率理论上应小于客户逾期率, 测算时注意以金额口径为准; Sheet3 不含逾期率字段, 风险排序已内嵌于评级(A~E)"},
    {"模块": "样本提示", "内容": "Sheet3(最新样本)格子样本量偏小: 提额客户<30人的格子占64/120(53%), <10人37格, =0人3格, 格子级均值噪声较大, 建议关注整体/评级维度结论"},
    {"模块": "约束生效情况", "内容": f"使用率盖帽压降 {use_cap_hit} 格(无借款低使用率A/B/C 1.2/1.0/0.6→0.5); 额度盖帽压降 {amt_cap_hit} 格(提额客户_平均额度远低于10万~30万盖帽, 约束暂不生效, 属保险机制)"},
    {"模块": "可调参数", "内容": "使用率盖帽高/中档当前不限制(USE_CAP={高:不限, 中:不限, 低:0.5}), 如需分级改为 {高:1.2, 中:1.0, 低:0.5} 等即可"},
])
ws_n = wb.create_sheet("约束与说明")
write_df(ws_n, notes)
for c in range(1, 3):
    cell = ws_n.cell(row=1, column=c)
    cell.fill, cell.font = HDR_FILL, HDR_FONT
ws_n.freeze_panes = "A2"
ws_n.column_dimensions["A"].width = 14
ws_n.column_dimensions["B"].width = 110
for r in range(2, ws_n.max_row + 1):
    ws_n.cell(row=r, column=1).font = Font(name="微软雅黑", size=9, bold=True)
    ws_n.cell(row=r, column=2).font = BODY_FONT
    for c in range(1, 3):
        ws_n.cell(row=r, column=c).border = BORDER

wb.save(DST)
print(f"\n✅ 已生成: {DST}")
print("Sheets:", wb.sheetnames)
