"""把 analysis.py (percent 格式) 转换为可复现的 Jupyter notebook"""
import nbformat as nbf

SRC = "/data2/jupyter-wenning/risk_analysis/analysis.py"
DST = "/data2/jupyter-wenning/risk_analysis/短账龄模型效果与提额策略分析.ipynb"

with open(SRC, encoding="utf-8") as f:
    lines = f.readlines()

blocks = []
cur, cur_type = [], "code"
for line in lines:
    if line.startswith("# %%"):
        if cur:
            blocks.append((cur_type, cur))
        cur = [line]
        cur_type = "markdown" if "[markdown]" in line else "code"
    else:
        cur.append(line)
if cur:
    blocks.append((cur_type, cur))

nb = nbf.v4.new_notebook()
nb.metadata = {
    "kernelspec": {"display_name": "ml_env", "language": "python", "name": "python3"},
    "language_info": {"name": "python", "version": "3.12"},
}
cells = []
for ctype, blk in blocks:
    src = "".join(l if i > 0 or not l.startswith("# %%") else "" for i, l in enumerate(blk))
    src = src.strip("\n")
    if not src:
        continue
    cells.append(nbf.v4.new_markdown_cell(src) if ctype == "markdown" else nbf.v4.new_code_cell(src))

# 末尾追加说明 cell
cells.append(nbf.v4.new_markdown_cell(
    "## 复现说明\n\n"
    "- **环境**: `/data2/jupyter-wenning/ml_env/bin/python` (python 3.12, pandas 3.0, optbinning 0.21, sklearn, openpyxl)\n"
    "- **数据**: `/data2/jupyter-wenning/strage/ng_pdl_ins_cashjq_analysic.csv` (277万行)\n"
    "- **输出**: `/data2/jupyter-wenning/strage/短账龄客户-模型效果与提额策略分析-*.xlsx` (4个sheet)\n"
    "- **调试**: 设置环境变量 `NROWS=300000` 可小样本快速验证; 全量运行直接执行所有 cell\n"
    "- **提额规则**: Sheet4 中 `CONFIG.ratio_tiers` 与 `CONFIG.min_cnt` 为可调参数\n"
    "- 分箱边界在**全量时间**上拟合(保证周间可比), 每周统计沿用同一边界\n"
    "- 最优模型 = 客群(全量时间)KS最大的模型; fpd7_dd_lift = bin的fpd7_dd ÷ 同时间切片客群fpd7_dd"
))
nb.cells = cells

with open(DST, "w", encoding="utf-8") as f:
    nbf.write(nb, f)
print(f"notebook 已生成: {DST}  ({len(cells)} cells)")
