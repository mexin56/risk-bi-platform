# CashJY Feature SQL Generator Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a runnable Jupyter Notebook that converts the CashJY feature-importance workbook into a reviewed, parameterized feature-extraction SQL template.

**Architecture:** The notebook keeps configuration, workbook loading, normalization, source assignment, SQL rendering, validation, and export in separate cells. The `table` column drives source-table grouping; source candidates in one cell are split and retained as an explicit ambiguity warning.

**Tech Stack:** Python 3, Jupyter, pandas, openpyxl, pathlib, collections.

## Global Constraints

- Never modify the source workbook.
- Do not execute generated warehouse SQL.
- Keep `${pt_beg}` and `${pt_end}` as literal SQL placeholders.
- Preserve feature order from the selected workbook rows.

### Task 1: Create the generator notebook

**Files:**
- Create: `risk_analysis/cashjy_feature_sql_generator.ipynb`

- [ ] Add configuration cells with the supplied workbook path, sheet name, base table settings, join settings, feature-set metadata, optional model filter, and output directory.
- [ ] Add loader and normalization cells that validate the required `变量名` and `table` columns, remove blank rows, trim BOMs and whitespace, and split comma-separated source candidates.
- [ ] Add mapping cells that preserve row order, allocate stable aliases, produce output aliases for duplicate feature/source occurrences, and collect warnings.
- [ ] Add SQL-rendering cells that generate the header, `select`, source subqueries, `left join` clauses, and literal partition placeholders.
- [ ] Add export cells that write SQL, mapping CSV, warnings CSV, and source summary CSV.

### Task 2: Validate the notebook

**Files:**
- Validate: `risk_analysis/cashjy_feature_sql_generator.ipynb`

- [ ] Execute the notebook top-to-bottom with `python -m jupyter nbconvert --execute --to notebook --inplace`.
- [ ] Confirm the default workbook loads 594 nonblank feature rows, 12 distinct source tables, and 593 unique variable names.
- [ ] Confirm generated SQL contains the configured join condition and partition placeholders, and that the duplicate `payer_repay_cnt_360d_v2` appears with an explicit versioned alias.
- [ ] Confirm all four output artifacts exist and contain bounded previews or row counts.
