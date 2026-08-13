"""每日新增 6000 万提额方案 → 完整 Excel 报告
Sheet1 方案总览(目标/推荐配置/分层统计/结论)
Sheet2 达标组合(网格扫描全部达标配置)
Sheet3 分层明细(推荐方案各 Tier 统计)
Sheet4 客群明细(每个客群×bin 的提额配置)
"""
import warnings; warnings.filterwarnings("ignore")
import pandas as pd, numpy as np, os

OUT_DIR = "/data2/jupyter-wenning/strage"
XL = os.path.join(OUT_DIR, "短账龄客户-模型效果与提额策略分析-20260807_2343.xlsx")
OUT_PATH = os.path.join(OUT_DIR, "提额6000万方案-20260807.xlsx")
SPAN_DAYS = 105
TARGET_DAILY = 6000
MAX_NEW_DD = 0.08
TIER_CAPS = [0.25, 0.50]
RATIO_PLANS = {
    "S1_温和": [0.50, 0.30, 0.15], "S2_进取": [0.60, 0.40, 0.20],
    "S3_积极": [0.70, 0.50, 0.25], "S4_优选": [0.80, 0.40, 0.15],
}
COVERS = [0.50, 0.65, 0.80]
PENS = [0.50, 0.55, 0.60, 0.65, 0.70, 0.75, 0.80]

s2 = pd.read_excel(XL, sheet_name="最优分箱")
s2 = s2[(s2["loan_week_begin"] == "全部") & (s2["是否最优模型"] == "最优模型")].copy()
s2["bin借款金额"] = s2["结清借款金额"]
s2["bin逾期率"] = s2["fpd7_dd"]
lift = s2["fpd7_dd_lift"]

def calc(cover, ratios, pen):
    mask = lift < cover
    sub = s2[mask].copy()
    r = sub["fpd7_dd_lift"]
    ratio = np.select([r < TIER_CAPS[0], r < TIER_CAPS[1], r < cover], ratios, default=0.0)
    sub["新增"] = sub["bin借款金额"] * ratio * pen
    amt = sub["bin借款金额"].sum()
    new_dd = (sub["bin借款金额"] * sub["bin逾期率"]).sum() / amt if amt > 0 else np.nan
    return sub, sub["新增"].sum() / SPAN_DAYS / 1e4, new_dd, int(sub["cnt"].sum())

# ---- 网格扫描 ----
results = []
for cover in COVERS:
    for pname, ratios in RATIO_PLANS.items():
        for pen in PENS:
            _, daily, new_dd, cust = calc(cover, ratios, pen)
            results.append({
                "覆盖阈值(风险比)": cover, "比率方案": pname,
                "分层比率(T1/T2/T3)": f"{int(ratios[0]*100)}/{int(ratios[1]*100)}/{int(ratios[2]*100)}",
                "渗透率": pen, "日均新增(万)": round(daily, 0),
                "月均新增(万)": round(daily * 30, 0), "规模增幅%": round(daily / 47630 * 100, 2),
                "新增逾期率%": round(new_dd * 100, 2) if new_dd == new_dd else np.nan,
                "覆盖客户数": cust, "达标": "✅" if (daily >= TARGET_DAILY and new_dd <= MAX_NEW_DD) else "",
            })
res = pd.DataFrame(results)
hit = res[res["达标"] == "✅"].sort_values(["新增逾期率%", "日均新增(万)"], ascending=[True, False]).reset_index(drop=True)

# ---- 推荐: 逾期率最低的达标组合 ----
best = hit.iloc[0]
cover, pname, pen = best["覆盖阈值(风险比)"], best["比率方案"], best["渗透率"]
ratios = RATIO_PLANS[pname]
sub, daily, new_dd, cust = calc(cover, ratios, pen)

# 分层统计
r = sub["fpd7_dd_lift"]
sub["层"] = np.select([r < TIER_CAPS[0], r < TIER_CAPS[1], r < cover],
                      ["Tier1_超低风险", "Tier2_低风险", "Tier3_中低风险"], default="不提额")
sub["提额比率"] = np.select([r < TIER_CAPS[0], r < TIER_CAPS[1], r < cover], ratios, default=0.0)
tier_sum = sub.groupby("层").apply(lambda g: pd.Series({
    "bin数": len(g), "覆盖客户数": int(g["cnt"].sum()),
    "当前借款金额(万)": round(g["bin借款金额"].sum() / 1e4, 0),
    "日均新增(万)": round((g["bin借款金额"] * g["提额比率"] * pen).sum() / SPAN_DAYS / 1e4, 0),
    "新增逾期率%": round((g["bin借款金额"] * g["bin逾期率"]).sum() / g["bin借款金额"].sum() * 100, 2),
}), include_groups=False).reset_index()
tier_sum["提额比率"] = tier_sum["层"].map(
    {"Tier1_超低风险": "+80%", "Tier2_低风险": "+40%", "Tier3_中低风险": "+15%"})

# ---- Sheet1 方案总览 ----
base_daily = 47630  # 现状日均(万)
overview = pd.DataFrame([
    {"模块": "目标", "指标": "每日新增借款额度", "数值": "≥ 6,000 万/天", "说明": "较现状日均 4.76 亿 提升 ≥12.6%"},
    {"模块": "目标", "指标": "质量红线", "数值": "新增借款加权逾期率 ≤ 8%", "说明": "远低于现状组合逾期率 19.86%"},
    {"模块": "推荐配置", "指标": "覆盖阈值(风险比)", "数值": f"{cover}", "说明": "bin逾期率/客群逾期率 < {cover} 才可提额"},
    {"模块": "推荐配置", "指标": "分层提额比率", "数值": "T1 +80% / T2 +40% / T3 +15%", "说明": "风险比<0.25 / 0.25-0.5 / 0.5-{cover}"},
    {"模块": "推荐配置", "指标": "渗透率(实际支用比例)", "数值": f"{pen*100:.0f}%", "说明": "提额客户中实际使用新增额度的比例"},
    {"模块": "推荐配置", "指标": "覆盖客户数", "数值": f"{cust:,}", "说明": f"占全量客户 {cust/2767597*100:.1f}%"},
    {"模块": "预期效果", "指标": "日均新增", "数值": f"{daily:,.0f} 万/天", "说明": "✅ 达标(目标 6,000 万)"},
    {"模块": "预期效果", "指标": "月均新增", "数值": f"{daily*30:,.0f} 万/月", "说明": f"规模增幅 {daily/base_daily*100:.1f}%"},
    {"模块": "预期效果", "指标": "新增借款加权逾期率", "数值": f"{new_dd*100:.2f}%", "说明": f"仅为现状组合逾期率 19.86% 的 {new_dd/0.1986*100:.0f}%"},
    {"模块": "预期效果", "指标": "提额后组合逾期率(测算)", "数值": "见下方计算", "说明": "新增规模稀释组合风险"},
    {"模块": "落地节奏", "指标": "第一周", "数值": "仅开 Tier1", "说明": "风险比<0.25 客群, 观察支用与逾期"},
    {"模块": "落地节奏", "指标": "第二周", "数值": "开 Tier1+Tier2", "说明": "风险比<0.5 客群, 目标日均 4,500 万"},
    {"模块": "落地节奏", "指标": "第三周起", "数值": "全量上线", "说明": "Tier1+Tier2+Tier3, 目标日均 6,000 万+"},
])

# 提额后组合逾期率
tot_amt = 500.11e8  # 现状总借款 500.11 亿
tot_dd = 0.1986
new_amt = daily * 1e4 * SPAN_DAYS
mix_dd = (tot_amt * tot_dd + new_amt * new_dd) / (tot_amt + new_amt)
overview.loc[overview["指标"] == "提额后组合逾期率(测算)", "数值"] = f"{mix_dd*100:.2f}%"
overview.loc[overview["指标"] == "新增借款加权逾期率", "说明"] = \
    f"仅为现状组合逾期率 19.86% 的 {new_dd/0.1986*100:.0f}%"

# ---- 输出 Excel ----
from openpyxl import Workbook
from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
from openpyxl.utils import get_column_letter
from openpyxl.formatting.rule import ColorScaleRule

HDR_FILL = PatternFill("solid", fgColor="4E83FD")
HDR_FONT = Font(name="微软雅黑", size=10, bold=True, color="FFFFFF")
BODY_FONT = Font(name="微软雅黑", size=9)
THIN = Side(style="thin", color="D9E2F3")
BORDER = Border(left=THIN, right=THIN, top=THIN, bottom=THIN)
MOD_FILL = PatternFill("solid", fgColor="EAF1FE")

def style_sheet(ws, pct_cols=(), int_cols=(), scale_cols=()):
    ncol = ws.max_column
    for c in range(1, ncol + 1):
        cell = ws.cell(row=1, column=c)
        cell.fill, cell.font = HDR_FILL, HDR_FONT
        cell.alignment = Alignment(horizontal="center", vertical="center")
        cell.border = BORDER
    ws.freeze_panes = "A2"
    ws.row_dimensions[1].height = 24
    hdrs = [str(ws.cell(row=1, column=c).value) for c in range(1, ncol + 1)]
    for c, h in enumerate(hdrs, 1):
        col = get_column_letter(c)
        ws.column_dimensions[col].width = max(10, min(34, len(h) * 2 + 4))
        if h in pct_cols:
            for r in range(2, ws.max_row + 1):
                ws.cell(row=r, column=c).number_format = "0.0%"
        elif h in int_cols:
            for r in range(2, ws.max_row + 1):
                ws.cell(row=r, column=c).number_format = "#,##0"
        if h in scale_cols and ws.max_row > 2:
            rng = f"{col}2:{col}{ws.max_row}"
            ws.conditional_formatting.add(rng, ColorScaleRule(
                start_type="min", start_color="63BE7B", mid_type="percentile", mid_value=50,
                mid_color="FFEB84", end_type="max", end_color="F8696B"))
    ws.auto_filter.ref = f"A1:{get_column_letter(ncol)}{ws.max_row}"

with pd.ExcelWriter(OUT_PATH, engine="openpyxl") as w:
    overview.to_excel(w, sheet_name="方案总览", index=False)
    hit.to_excel(w, sheet_name="达标组合", index=False)
    tier_sum.to_excel(w, sheet_name="分层明细", index=False)
    detail = sub[["loan_ser_node", "flag_customer", "loan_cnt_detal_group", "credit_use_type",
                  "模型", "bin区间", "层", "提额比率", "cnt", "bin借款金额", "bin逾期率",
                  "fpd7_dd_lift"]].copy()
    detail["日均新增(万)"] = (detail["bin借款金额"] * detail["提额比率"] * pen / SPAN_DAYS / 1e4).round(0)
    detail = detail.sort_values(["层", "日均新增(万)"], ascending=[True, False])
    detail.to_excel(w, sheet_name="客群明细", index=False)

    # 方案总览样式
    ws = w.sheets["方案总览"]
    ws.freeze_panes = None
    ws.auto_filter.ref = None
    for r in range(2, ws.max_row + 1):
        for c in range(1, 5):
            cell = ws.cell(row=r, column=c)
            cell.font = BODY_FONT
            cell.border = BORDER
            if c == 1:
                cell.fill = MOD_FILL
                cell.font = Font(name="微软雅黑", size=9, bold=True)
            if c == 3:
                cell.font = Font(name="微软雅黑", size=10, bold=True, color="1F3C88")
    for col, wd in zip("ABCD", [12, 26, 26, 44]):
        ws.column_dimensions[col].width = wd
    for r in range(2, ws.max_row + 1):
        if "目标" in str(ws.cell(row=r, column=1).value):
            for c in range(1, 5):
                ws.cell(row=r, column=c).fill = PatternFill("solid", fgColor="FFF3E0")

    style_sheet(w.sheets["达标组合"], pct_cols=["渗透率", "新增逾期率%", "规模增幅%"],
                int_cols=["日均新增(万)", "月均新增(万)", "覆盖客户数"], scale_cols=["日均新增(万)", "新增逾期率%"])
    style_sheet(w.sheets["分层明细"], pct_cols=["新增逾期率%"],
                int_cols=["覆盖客户数", "当前借款金额(万)", "日均新增(万)"], scale_cols=["日均新增(万)", "新增逾期率%"])
    style_sheet(w.sheets["客群明细"], pct_cols=["bin逾期率", "fpd7_dd_lift"],
                int_cols=["cnt", "bin借款金额", "日均新增(万)"], scale_cols=["bin逾期率", "日均新增(万)"])

print(f"✅ 方案 Excel 已生成: {OUT_PATH}")
print(f"  Sheet1 方案总览 | Sheet2 达标组合 {len(hit)} 个 | Sheet3 分层明细 | Sheet4 客群明细 {len(detail):,} 行")
