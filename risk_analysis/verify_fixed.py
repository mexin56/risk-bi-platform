"""修正逻辑验证: 全量客户 8 个模型的 KS/AUC(仅 fpd7_fm_dd==1 到期样本, KS取绝对值, AUC方向无关)"""
import warnings; warnings.filterwarnings("ignore")
import pandas as pd, numpy as np, time
from sklearn.metrics import roc_auc_score, roc_curve

t0 = time.time()
df = pd.read_csv("/data2/jupyter-wenning/strage/ng_pdl_ins_cashjq_analysic.csv", low_memory=False)
print(f"加载 {len(df):,} 行, {time.time()-t0:.0f}s")

SCORE_COLS = [
    "ng_cashjq_loancnt_1plus_v1_score","ng_cashjq_loancnt_1_4_v1_score",
    "pre_ng_cash_settlement_short_mob_v1_score","pre_ng_cash_settlement_long_mob_v1_score",
    "offline_b_score_low_mob_score_v1","offline_b_score_v1",
    "ng_cashjq_utilization_high_v1_score","ng_cashjq_utilization_mideum_v1_score",
]

# ===== 修正后的口径 =====
sub = df[df["fpd7_fm_dd"] == 1].copy()
y = (sub["fpd7_fz_dd"] > 0).astype(int)
print(f"到期样本: {len(sub):,}  坏率: {y.mean():.4f}")

print(f"\n{'模型':<42}{'样本数':>10}{'坏率':>8}{'KS(绝对值)':>12}{'AUC(方向无关)':>14}{'原始AUC':>10}")
rows = []
for c in SCORE_COLS:
    sc = sub[c]
    m2 = (sc > 0) & np.isfinite(sc)
    y2, s2 = y[m2], sc[m2]
    if len(y2) < 50 or y2.nunique() < 2:
        print(f"{c:<42}{'样本不足':>10}")
        continue
    auc_raw = roc_auc_score(y2, s2)
    fpr, tpr, _ = roc_curve(y2, s2)
    ks = float(np.max(np.abs(tpr - fpr)))
    auc = float(max(auc_raw, 1 - auc_raw))
    print(f"{c:<42}{len(y2):>10,}{y2.mean():>8.4f}{ks:>12.4f}{auc:>14.4f}{auc_raw:>10.4f}")
    rows.append({"模型": c, "样本数": len(y2), "坏率": round(y2.mean(), 4), "KS": round(ks, 4),
                 "AUC": round(auc, 4), "原始AUC": round(auc_raw, 4)})

out = pd.DataFrame(rows)
out.to_csv("/data2/jupyter-wenning/risk_analysis/ks_auc_full_verify.csv", index=False, encoding="utf-8-sig")
print("\n已保存: ~/risk_analysis/ks_auc_full_verify.csv")
