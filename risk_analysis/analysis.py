# %% [markdown]
# # 短账龄客户 · 模型效果评估与提额策略分析
# 
# - 数据: `/data2/jupyter-wenning/strage/ng_pdl_ins_cashjq_analysic.csv` (277万行)
# - 环境: `/data2/jupyter-wenning/ml_env` (python 3.12 / pandas 3.0 / optbinning 0.21)
# - 目标: `y = (fpd7_fz_dd > 0)` (首逾7天发生金额>0)
# - 输出: 4个sheet的Excel (模型效果 / 最优分箱 / 等频分箱 / 提额建议)
# - 口径说明:
#   - 全局剔除: `flag='-1'`, `credit_use_type='-1'`
#   - nextloan指标: 在 `next_loan_prin>0` 子集上计算
#   - KS/AUC/分箱: 剔除该模型 score 缺失或 `<=0`(无分占位-1)的样本
#   - 时间维度: 按 `loan_week_begin` 每周统计 + 追加"全部"合并行
#   - lift = bin的fpd7_dd ÷ 同时间切片客群整体fpd7_dd

# %%
import warnings
warnings.filterwarnings("ignore")
import os, re, time
import numpy as np
import pandas as pd
from sklearn.metrics import roc_auc_score, roc_curve

# %% [markdown]
# ## 0. 配置

# %%
DATA_PATH = "/data2/jupyter-wenning/strage/ng_pdl_ins_cashjq_analysic.csv"
OUT_DIR   = "/data2/jupyter-wenning/strage"
OUT_NAME  = "短账龄客户-模型效果与提额策略分析-" + time.strftime("%Y%m%d_%H%M") + ".xlsx"
OUT_PATH  = os.path.join(OUT_DIR, OUT_NAME)
NROWS     = int(os.environ.get("NROWS", "0")) or None   # 调试用: 限制行数

# 8个模型分(去重后)
SCORE_COLS = [
    "ng_cashjq_loancnt_1plus_v1_score",
    "ng_cashjq_loancnt_1_4_v1_score",
    "pre_ng_cash_settlement_short_mob_v1_score",
    "pre_ng_cash_settlement_long_mob_v1_score",
    "offline_b_score_low_mob_score_v1",
    "offline_b_score_v1",
    "ng_cashjq_utilization_high_v1_score",
    "ng_cashjq_utilization_mideum_v1_score",
]
# 列名缩短(可读性), 原始列名保留在 notebook 说明中
MODEL_SHORT = {c: c.replace("ng_cashjq_", "ng_").replace("_score_v1", "").replace("_v1", "")
                 for c in SCORE_COLS}

# 分群字段
KEYS1 = ["loan_ser_node", "flag_customer", "flag", "credit_use_type"]          # 分群1
KEYS2 = ["loan_ser_node", "flag_customer", "loan_cnt_detal_group", "credit_use_type"]  # 分群2
TIME_COL = "loan_week_begin"
TARGET = "fpd7_fz_dd"          # 目标字段: 首逾7天发生金额
Y = "y_bad"                    # y = fpd7_fz_dd > 0

MAX_BINS = 5                   # optbinning 最大分箱数
QCUT_BINS = 5                  # qcut 等频分箱数

# %% [markdown]
# ## 1. 加载数据 + 预处理(剔除)

# %%
t0 = time.time()
df = pd.read_csv(DATA_PATH, low_memory=False, nrows=NROWS)
print(f"原始行数: {len(df):,}  列数: {len(df.columns)}  加载耗时 {time.time()-t0:.0f}s")

# 目标变量
df[Y] = (df[TARGET] > 0).astype(int)

# 全局剔除: 缺失标签
n0 = len(df)
df = df[df["flag"].astype(str) != "-1"]
df = df[df["credit_use_type"].astype(str) != "-1"]
df = df.reset_index(drop=True)   # 重置索引, groupby.indices 与 loc 对齐
print(f"剔除 flag=-1 / credit_use_type=-1 后: {len(df):,} ({(len(df)/n0*100):.1f}%)")

# nextloan 指标使用的分子分母预计算列
df["_curr_int_amt"] = df["curr_loan_prin"] * df["curr_interest_ratio"]   # 结清日息分子
df["_next_int_amt"] = df["next_loan_prin"] * df["curr_interest_ratio"]   # nextloan日息分子(按需求用 curr_interest_ratio)
df["_has_next"] = df["next_loan_prin"] > 0                                # 有 next 借款的子集
print(f"有 next 借款样本: {df['_has_next'].sum():,} ({df['_has_next'].mean()*100:.1f}%)")
print(f"y坏样本率: {df[Y].mean():.4f}")

# %% [markdown]
# ## 2. 工具函数: 18个统计指标 + KS/AUC

# %%
# ---- 18个统计指标: 基于 groupby 的向量化聚合 ----
def agg_metrics(g: pd.DataFrame) -> pd.DataFrame:
    """输入已 groupby 的 DataFrameGroupBy, 输出18个指标的 DataFrame(索引=分组键)"""
    n_next = g["_has_next"].sum()
    s_curr_prin = g["curr_loan_prin"].sum()
    out = pd.DataFrame({
        "cnt": g.size(),
        # 结清类(全量样本)
        "结清平均额度": g["curr_credit_quota"].mean(),
        "结清件均": s_curr_prin / g["businessid"].count(),
        "结清日息": g["_curr_int_amt"].sum() / s_curr_prin.replace(0, np.nan),
        "结清总费": g["curr_total_fee"].sum() / s_curr_prin.replace(0, np.nan),
        "结清借款金额": s_curr_prin,
        # nextloan类(仅 next_loan_prin>0 子集)
        "nextloan平均额度": g["next_curr_credit_quota"].sum() / n_next.replace(0, np.nan),
        "nextloan件均": g["next_loan_prin"].sum() / n_next.replace(0, np.nan),
        "nextloan日息": g["_next_int_amt"].sum() / g["next_loan_prin"].sum().replace(0, np.nan),
        "nextloan总费": g["next_total_fee"].sum() / g["next_loan_prin"].sum().replace(0, np.nan),
        "nextloan借款金额": g["next_total_fee"].sum(),
        # 逾期表现
        "due1_cnt": g["fpd1_fm_dd"].sum(),
        "fpd1_dd": g["fpd1_fz_dd"].sum() / g["fpd1_fm_dd"].sum().replace(0, np.nan),
        "fpd1_bj": g["fpd1_fz_bj"].sum() / g["fpd1_fm_bj"].sum().replace(0, np.nan),
        "fpd7_dd": g["fpd7_fz_dd"].sum() / g["fpd7_fm_dd"].sum().replace(0, np.nan),
        "fpd7_bj": g["fpd7_fz_bj"].sum() / g["fpd7_fm_bj"].sum().replace(0, np.nan),
        "fpd15_dd": g["fpd15_fz_dd"].sum() / g["fpd15_fm_dd"].sum().replace(0, np.nan),
        "fpd15_bj": g["fpd15_fz_bj"].sum() / g["fpd15_fm_bj"].sum().replace(0, np.nan),
    })
    return out

def calc_metrics(df_sub: pd.DataFrame, keys: list[str]) -> pd.DataFrame:
    return agg_metrics(df_sub.groupby(keys, observed=True, sort=False)).reset_index()

# ---- KS / AUC ----
# 口径(用户确认): 仅 fpd7_fm_dd==1(分母到期)的样本参与评估, y = fpd7_fz_dd > 0
# 模型为信用评分卡(分数越高越优), 故 KS 取 |max(tpr-fpr)|, AUC 取 max(auc, 1-auc), 均为方向无关的区分度
def ks_auc_one(y: np.ndarray, score: np.ndarray):
    """返回 (KS, AUC); 样本不足或目标单一返回 (NaN, NaN)"""
    y = np.asarray(y, dtype=float); s = np.asarray(score, dtype=float)
    m = np.isfinite(s) & np.isfinite(y)
    y, s = y[m], s[m]
    if len(y) < 50 or len(np.unique(y)) < 2 or np.unique(s).size < 2:
        return np.nan, np.nan
    try:
        auc = roc_auc_score(y, s)
        fpr, tpr, _ = roc_curve(y, s)
        ks = float(np.max(np.abs(tpr - fpr)))          # 取绝对值(方向无关)
        auc = float(max(auc, 1 - auc))                 # 方向无关(信用分: 分高=安全)
        return ks, auc
    except Exception:
        return np.nan, np.nan

def calc_ks_auc(df_sub: pd.DataFrame, keys: list[str]) -> pd.DataFrame:
    """按 keys 分组, 对8个模型计算 KS/AUC(仅到期样本), 并选出 KS 最大的最优模型"""
    out_cols = keys + [f"ks_{MODEL_SHORT[c]}" for c in SCORE_COLS] \
              + [f"auc_{MODEL_SHORT[c]}" for c in SCORE_COLS] + ["最优模型", "最优模型KS"]
    sub = df_sub[df_sub["fpd7_fm_dd"] == 1]   # 口径: 分母到期才参与模型评估
    recs = []
    for kv, g in sub.groupby(keys, observed=True, sort=False):
        if len(g) < 50:
            continue
        row = dict(zip(keys, kv)) if isinstance(kv, tuple) else {keys[0]: kv}
        best_ks, best_m = -1.0, ""
        for c in SCORE_COLS:
            sc = g[c]
            sc = sc[sc > 0]          # 剔除 score 缺失/<=0(无分占位)
            y = g.loc[sc.index, Y].to_numpy()
            if len(sc) < 50:
                row[f"ks_{MODEL_SHORT[c]}"], row[f"auc_{MODEL_SHORT[c]}"] = np.nan, np.nan
                continue
            ks, auc = ks_auc_one(y, sc.to_numpy())
            row[f"ks_{MODEL_SHORT[c]}"], row[f"auc_{MODEL_SHORT[c]}"] = ks, auc
            if ks == ks and ks > best_ks:
                best_ks, best_m = ks, MODEL_SHORT[c]
        row["最优模型"] = best_m if best_m else ""
        row["最优模型KS"] = best_ks if best_ks >= 0 else np.nan
        recs.append(row)
    return pd.DataFrame(recs, columns=out_cols)   # 空结果也保留列结构

# %% [markdown]
# ## 3. Sheet1 模型效果 (分群1)

# %%
def build_sheet_model_effect(df: pd.DataFrame) -> pd.DataFrame:
    weeks = sorted(df[TIME_COL].unique())
    parts = []
    for wk in weeks + ["全部"]:
        sub = df if wk == "全部" else df[df[TIME_COL] == wk]
        ks = calc_ks_auc(sub, KEYS1)
        met = calc_metrics(sub, KEYS1)
        m = ks.merge(met, on=KEYS1, how="outer")
        m.insert(0, TIME_COL, wk)
        parts.append(m)
    return pd.concat(parts, ignore_index=True)

sheet1 = build_sheet_model_effect(df)
print(f"Sheet1 行数: {len(sheet1):,}  客群组合: {sheet1.groupby(KEYS1).ngroups:,}")

# %% [markdown]
# ## 4. 分箱函数: optbinning / qcut

# %%
def fit_optbinning_bins(g_df: pd.DataFrame, score_col: str, y_col: str, max_bins: int = 5):
    """optbinning 最优分箱(不要求单调, bin<=max_bins), 返回 pd.IntervalIndex 边界; 失败返回 None
    口径: 仅 fpd7_fm_dd==1(到期)样本参与分箱拟合"""
    from optbinning import OptimalBinning
    g_df = g_df[g_df["fpd7_fm_dd"] == 1]
    s = g_df[score_col]; y = g_df[y_col]
    m = (s > 0) & np.isfinite(s) & np.isfinite(y)
    s, y = s[m], y[m]
    if len(s) < 100 or len(np.unique(y)) < 2 or np.unique(s).size < 2:
        return None
    try:
        optb = OptimalBinning(name=score_col, dtype="numerical", solver="cp",
                              max_n_bins=max_bins, monotonic_trend=None,
                              min_bin_size=0.01, cat_cutoff=None)
        optb.fit(s.to_numpy(), y.to_numpy())
        splits = optb.splits
        if splits is None or len(splits) < 1:
            return None
        edges = [-np.inf] + list(splits) + [np.inf]
        return pd.IntervalIndex.from_breaks(edges, closed="left")
    except Exception:
        return None

def fit_qcut_bins(g_df: pd.DataFrame, score_col: str, n_bins: int = 5):
    """qcut 等频分箱, 返回 pd.IntervalIndex; 唯一值不足时降级
    口径: 仅 fpd7_fm_dd==1(到期)样本参与分箱拟合"""
    s = g_df.loc[g_df["fpd7_fm_dd"] == 1, score_col]
    s = s[s > 0]
    if s.nunique() < 2:
        return None
    try:
        _, bins = pd.qcut(s, n_bins, duplicates="drop", retbins=True)
        edges = [-np.inf] + list(bins[1:-1]) + [np.inf]
        return pd.IntervalIndex.from_breaks(edges, closed="left")
    except Exception:
        try:
            _, bins = pd.qcut(s.rank(method="first"), n_bins, duplicates="drop", retbins=True)
            edges = [-np.inf] + list(bins[1:-1]) + [np.inf]
            return pd.IntervalIndex.from_breaks(edges, closed="left")
        except Exception:
            return None

def map_bins(g_df: pd.DataFrame, score_col: str, bins: pd.IntervalIndex):
    """把分箱边界映射回样本, 返回 (bin序号, bin区间); score<=0/缺失 -> NaN(无分, 剔除)"""
    s = g_df[score_col]
    out = pd.Series(np.nan, index=g_df.index, dtype="object")
    mask = (s > 0) & np.isfinite(s)
    out.loc[mask] = pd.cut(s[mask], bins).astype(str)
    return out

# %% [markdown]
# ## 5. Sheet2 / Sheet3 通用构建 (分群2 × 模型分箱)

# %%
def build_sheet_binning(df: pd.DataFrame, method: str) -> pd.DataFrame:
    """method: 'optbinning' | 'qcut'
    对每个客群(分群2)在每个模型上拟合分箱边界(全量时间拟合,保证时间切片可比),
    然后按 客群×模型×bin×时间 统计 18指标 + fpd7_dd_lift + 最优模型标签
    """
    weeks = sorted(df[TIME_COL].unique())
    # 客群整体 fpd7_dd(各时间切片 + 全部)
    grp_rate = (df.groupby(KEYS2 + [TIME_COL], observed=True, sort=False)
                .apply(lambda g: pd.Series({"grp_fpd7_dd": g["fpd7_fz_dd"].sum() / g["fpd7_fm_dd"].sum()}),
                       include_groups=False).reset_index())
    grp_rate_all = (df.groupby(KEYS2, observed=True, sort=False)
                    .apply(lambda g: pd.Series({"grp_fpd7_dd": g["fpd7_fz_dd"].sum() / g["fpd7_fm_dd"].sum()}),
                           include_groups=False).reset_index())
    grp_rate_all[TIME_COL] = "全部"
    grp_rate = pd.concat([grp_rate, grp_rate_all], ignore_index=True)

    # 客群KS最大的模型(基于全量时间) → 最优模型标签
    grp_best = calc_ks_auc(df, KEYS2)[KEYS2 + ["最优模型"]]

    parts = []
    for model in SCORE_COLS:
        short = MODEL_SHORT[model]
        t0m = time.time()
        # 1) 每个客群拟合分箱边界
        bin_map = {}
        for kv, g in df.groupby(KEYS2, observed=True, sort=False):
            key = kv if isinstance(kv, tuple) else (kv,)
            bins = (fit_optbinning_bins(g, model, Y, MAX_BINS) if method == "optbinning"
                    else fit_qcut_bins(g, model, QCUT_BINS))
            if bins is None:  # 降级: 单bin(全部样本)
                bins = pd.IntervalIndex.from_breaks([-np.inf, np.inf], closed="left")
            bin_map[key] = bins
        # 2) 映射 bin 列到全量 df
        df["_bin"] = pd.Series(np.nan, index=df.index, dtype="object")
        for kv, idx in df.groupby(KEYS2, observed=True, sort=False).indices.items():
            iv = map_bins(df.iloc[idx], model, bin_map[kv])
            df.loc[idx, "_bin"] = iv
        sub = df[df["_bin"].notna()]
        # 3) 一次聚合(客群×bin×时间), 再补"全部"时间
        met = agg_metrics(sub.groupby(KEYS2 + ["_bin", TIME_COL], observed=True, sort=False)).reset_index()
        met_all = agg_metrics(sub.groupby(KEYS2 + ["_bin"], observed=True, sort=False)).reset_index()
        met_all.insert(len(KEYS2) + 1, TIME_COL, "全部")
        met = pd.concat([met, met_all], ignore_index=True)
        # 4) 补 lift / 最优模型标签 / 模型名
        met = met.merge(grp_rate, on=KEYS2 + [TIME_COL], how="left")
        met["fpd7_dd_lift"] = met["fpd7_dd"] / met["grp_fpd7_dd"]
        met = met.merge(grp_best, on=KEYS2, how="left")
        met["是否最优模型"] = np.where(met["最优模型"] == short, "最优模型", "非最优模型")
        met.insert(0, "模型", short)
        met = met.rename(columns={"_bin": "bin区间"})
        parts.append(met)
        print(f"  [{method}] {short} 完成, 耗时 {time.time()-t0m:.0f}s")
    out = pd.concat(parts, ignore_index=True)
    # bin 序号(按区间排序)
    out["bin序号"] = out.groupby(KEYS2 + ["模型"], observed=True)["bin区间"].transform(
        lambda x: pd.factorize(x, sort=True)[0] + 1)
    return out

# %% [markdown]
# ## 6. 执行 Sheet2 最优分箱 / Sheet3 等频分箱

# %%
sheet2 = build_sheet_binning(df, "optbinning")
print(f"Sheet2 最优分箱 行数: {len(sheet2):,}")
sheet2.to_csv(os.path.join(OUT_DIR, "_sheet2_最优分箱.csv"), index=False, encoding="utf-8-sig")

# %%
sheet3 = build_sheet_binning(df, "qcut")
print(f"Sheet3 等频分箱 行数: {len(sheet3):,}")
sheet3.to_csv(os.path.join(OUT_DIR, "_sheet3_等频分箱.csv"), index=False, encoding="utf-8-sig")

# %% [markdown]
# ## 7. Sheet4 提额策略建议
# 
# 逻辑(可调参数, 见下方 CONFIG):
# - 目标: 在低风险客群上提额 → 提升件均/规模, 同时控制逾期
# - 每个客群(分群2)取 KS 最大的模型(最优模型), 选其分箱中 **fpd7_dd 最低且样本数>=min_cnt** 的 bin 作为可提额客群
# - 提额比率按 风险比 = bin_fpd7_dd / 客群_fpd7_dd 分档

# %%
CONFIG = dict(
    min_cnt=100,          # 最优bin最小样本数
    ratio_tiers=[(0.5, 0.50), (0.8, 0.30), (1.0, 0.15)],  # (风险比上限, 提额比率)
)

def build_sheet4(sheet2_binning: pd.DataFrame) -> pd.DataFrame:
    s2 = sheet2_binning[sheet2_binning[TIME_COL] == "全部"].copy()
    s2 = s2[s2["是否最优模型"] == "最优模型"]          # 只看最优模型的bin
    # 客群级汇总(全部时间): 件均 = Σ结清借款金额/Σcnt
    grp_sum = s2.groupby(KEYS2, observed=True, sort=False).apply(
        lambda g: pd.Series({
            "客群件均": g["结清借款金额"].sum() / g["cnt"].sum(),
            "客群平均额度": (g["结清平均额度"] * g["cnt"]).sum() / g["cnt"].sum(),
        }), include_groups=False).reset_index()
    rows = []
    for kv, g in s2.groupby(KEYS2, observed=True, sort=False):
        key = dict(zip(KEYS2, kv)) if isinstance(kv, tuple) else {KEYS2[0]: kv}
        best_m = g["模型"].iloc[0]                     # 该客群最优模型(由标签保证唯一)
        cand = g[g["cnt"] >= CONFIG["min_cnt"]].sort_values("fpd7_dd")  # 低风险优先
        if cand.empty:
            continue
        b = cand.iloc[0]                               # 最优bin = fpd7_dd最低且规模足够的bin
        grp_dd = b["grp_fpd7_dd"]
        risk_ratio = b["fpd7_dd"] / grp_dd if grp_dd and grp_dd > 0 else np.nan
        ratio = 0.0
        for cap, r in CONFIG["ratio_tiers"]:
            if risk_ratio == risk_ratio and risk_ratio < cap:
                ratio = r
                break
        gs = grp_sum[(grp_sum[KEYS2[0]] == key[KEYS2[0]]) & (grp_sum[KEYS2[1]] == key[KEYS2[1]]) &
                     (grp_sum[KEYS2[2]] == key[KEYS2[2]]) & (grp_sum[KEYS2[3]] == key[KEYS2[3]])]
        rows.append({
            **key,
            "最优模型": best_m,
            "最优bin": b["bin区间"],
            "bin样本数": int(b["cnt"]),
            "客群样本数": int(g["cnt"].sum()),
            "bin件均": round(b["结清件均"], 2),
            "客群件均": round(float(gs["客群件均"].iloc[0]), 2) if not gs.empty else np.nan,
            "bin_fpd7_dd": round(b["fpd7_dd"], 4),
            "客群_fpd7_dd": round(grp_dd, 4) if grp_dd == grp_dd else np.nan,
            "风险比": round(risk_ratio, 4) if risk_ratio == risk_ratio else np.nan,
            "bin平均额度": round(b["结清平均额度"], 2),
            "客群平均额度": round(float(gs["客群平均额度"].iloc[0]), 2) if not gs.empty else np.nan,
            "建议提额比率": ratio,
            "策略说明": f"低风险bin提额: fpd7_dd={b['fpd7_dd']:.4f} < 客群{grp_dd:.4f}, 目标在控制当前逾期的同时提升件均与规模",
        })
    return pd.DataFrame(rows)

sheet4 = build_sheet4(sheet2)
print(f"Sheet4 提额建议 行数: {len(sheet4):,}")
print(sheet4[KEYS2 + ["最优模型", "最优bin", "建议提额比率"]].head(10).to_string())

# %% [markdown]
# ## 8. Excel 输出 + 美化(openpyxl)

# %%
from openpyxl import Workbook
from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
from openpyxl.utils import get_column_letter
from openpyxl.formatting.rule import ColorScaleRule, CellIsRule

HDR_FILL = PatternFill("solid", fgColor="4E83FD")
HDR_FONT = Font(name="微软雅黑", size=10, bold=True, color="FFFFFF")
BODY_FONT = Font(name="微软雅黑", size=9)
THIN = Side(style="thin", color="D9E2F3")
BORDER = Border(left=THIN, right=THIN, top=THIN, bottom=THIN)

def style_sheet(ws, pct_cols=(), num4_cols=(), money_cols=(), int_cols=(), scale_cols=()):
    """统一美化: 表头/冻结/列宽/数字格式/条件格式"""
    ncol = ws.max_column
    # 表头
    for c in range(1, ncol + 1):
        cell = ws.cell(row=1, column=c)
        cell.fill, cell.font = HDR_FILL, HDR_FONT
        cell.alignment = Alignment(horizontal="center", vertical="center")
        cell.border = BORDER
    ws.freeze_panes = "B2"
    ws.auto_filter.ref = ws.dimensions
    ws.row_dimensions[1].height = 24
    # 列宽(粗略: 中文×2)
    for c in range(1, ncol + 1):
        hdr = str(ws.cell(row=1, column=c).value or "")
        w = max(9, min(40, len(hdr) * 2 + 4))
        ws.column_dimensions[get_column_letter(c)].width = w
    # 内容样式
    for r in range(2, ws.max_row + 1):
        for c in range(1, ncol + 1):
            cell = ws.cell(row=r, column=c)
            cell.font = BODY_FONT
            cell.border = BORDER
    # 数字格式
    hdrs = [str(ws.cell(row=1, column=c).value) for c in range(1, ncol + 1)]
    for c, h in enumerate(hdrs, 1):
        col = get_column_letter(c)
        if h in pct_cols:
            for r in range(2, ws.max_row + 1):
                ws.cell(row=r, column=c).number_format = "0.00%"
        elif h in num4_cols:
            for r in range(2, ws.max_row + 1):
                ws.cell(row=r, column=c).number_format = "0.0000"
        elif h in money_cols:
            for r in range(2, ws.max_row + 1):
                ws.cell(row=r, column=c).number_format = "#,##0.00"
        elif h in int_cols:
            for r in range(2, ws.max_row + 1):
                ws.cell(row=r, column=c).number_format = "#,##0"
    # 条件格式: 三色刻度
    for c, h in enumerate(hdrs, 1):
        if h in scale_cols and ws.max_row > 2:
            rng = f"{get_column_letter(c)}2:{get_column_letter(c)}{ws.max_row}"
            ws.conditional_formatting.add(rng, ColorScaleRule(
                start_type="min", start_color="F8696B",
                mid_type="percentile", mid_value=50, mid_color="FFEB84",
                end_type="max", end_color="63BE7B"))
    ws.auto_filter.ref = f"A1:{get_column_letter(ncol)}{ws.max_row}"

PCT_COLS = ["结清日息", "结清总费", "nextloan日息", "nextloan总费", "fpd1_dd", "fpd1_bj",
            "fpd7_dd", "fpd7_bj", "fpd15_dd", "fpd15_bj", "建议提额比率"]
NUM4_COLS = ["fpd7_dd_lift", "风险比", "最优模型KS"] + [f"ks_{MODEL_SHORT[c]}" for c in SCORE_COLS] \
          + [f"auc_{MODEL_SHORT[c]}" for c in SCORE_COLS]
MONEY_COLS = ["结清平均额度", "结清件均", "结清借款金额", "nextloan平均额度", "nextloan件均",
              "nextloan借款金额", "bin件均", "客群件均", "bin平均额度"]
INT_COLS = ["cnt", "due1_cnt", "bin样本数", "客群样本数"]
SCALE_COLS = ["fpd7_dd", "fpd7_dd_lift", "fpd1_dd", "建议提额比率"] + \
             [f"ks_{MODEL_SHORT[c]}" for c in SCORE_COLS]

with pd.ExcelWriter(OUT_PATH, engine="openpyxl") as writer:
    sheet1.to_excel(writer, sheet_name="模型效果", index=False)
    sheet2.to_excel(writer, sheet_name="最优分箱", index=False)
    sheet3.to_excel(writer, sheet_name="等频分箱", index=False)
    sheet4.to_excel(writer, sheet_name="提额建议", index=False)

    style_sheet(writer.sheets["模型效果"], PCT_COLS, NUM4_COLS, MONEY_COLS, INT_COLS, SCALE_COLS)
    style_sheet(writer.sheets["最优分箱"], PCT_COLS, NUM4_COLS, MONEY_COLS, INT_COLS, SCALE_COLS)
    style_sheet(writer.sheets["等频分箱"], PCT_COLS, NUM4_COLS, MONEY_COLS, INT_COLS, SCALE_COLS)
    style_sheet(writer.sheets["提额建议"], PCT_COLS, NUM4_COLS, MONEY_COLS, INT_COLS, SCALE_COLS)

print(f"\n✅ Excel 已生成: {OUT_PATH}")
for s in ["模型效果", "最优分箱", "等频分箱", "提额建议"]:
    ws = pd.ExcelFile(OUT_PATH).parse(s)
    print(f"  {s}: {ws.shape[0]:,} 行 × {ws.shape[1]} 列")
