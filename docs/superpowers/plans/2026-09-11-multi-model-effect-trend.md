# Multi-Model Effect Trend Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 将模型监控主视图改为所有 `_score` 模型按日期对比 AUC/KS，并支持 FPD7、FPD30、TERM3 切换、成熟度断线和分数覆盖监控。

**Architecture:** MaxCompute 只返回按 `event_date`、模型、50 分桶聚合的成熟好坏样本数；服务端在 `model_monitoring.py` 中计算方向无关的近似 AUC/KS、成熟度和覆盖率，再由 `/api/model-monitoring` 返回给 React 页面。前端以模型选择、目标标签和 AUC/KS 切换驱动同一组趋势图，不返回任何明细标识。

**Tech Stack:** FastAPI、PyODPS、pytest、React 19、TypeScript、ECharts、Vite、Tailwind CSS。

## Global Constraints

- 数据源固定为 `pb_biz_credit.ng_cash_model_monitoring_df`，按 `pt` 分区读取。
- 所有 `_score` 字段均作为模型分；模型字段按 `STRING` 处理。
- NULL、空字符串、`-1` 不参与效果计算；`-1` 计入覆盖质量。
- FPD7/FPD30/TERM3 使用各自 `*_fm_dd=1` 成熟样本和 `*_fz_dd=1` 坏样本。
- 成熟样本数 / 当日放款成功数低于 50%，或成熟样本数低于 1,000 时，AUC/KS 置空并标记成熟度不足。
- 分数按 50 分桶计算近似 AUC/KS；AUC 使用 `max(auc, 1-auc)`，KS 使用最大绝对差，不预设分数方向。
- 保留 15 分钟服务端缓存和 `force=true` 刷新；不返回业务号、客户号、卡号。

---

### Task 1: 实现分桶 AUC/KS 与模型趋势纯函数

**Files:**
- Modify: `server/model_monitoring.py`
- Modify: `server/test_model_monitoring.py`

**Interfaces:**
- Produces `build_model_effect_trend(rows, daily_rows, target='fpd7') -> list[dict[str, Any]]`。
- 每一行输出 `day`、`model`、`auc`、`ks`、`mature_count`、`bad_count`、`good_count`、`score_valid_count`、`score_coverage`、`maturity_warning`。

- [ ] **Step 1: Write the failing tests**

在 `server/test_model_monitoring.py` 增加以下行为测试：

```python
def test_model_effect_trend_calculates_direction_agnostic_auc_and_ks():
    result = build_model_effect_trend(
        [
            {"day": "2026-09-01", "model": "op_v2_score", "score_bin": 0, "score_valid_cnt": 20, "fpd7_base": 10, "fpd7_bad": 8},
            {"day": "2026-09-01", "model": "op_v2_score", "score_bin": 1, "score_valid_cnt": 20, "fpd7_base": 10, "fpd7_bad": 2},
        ],
        [{"day": "2026-09-01", "applications": 50, "loan_success": 40}],
    )
    assert result[0]["auc"] == 0.8
    assert result[0]["ks"] == 0.6
    assert result[0]["score_coverage"] == 0.8


def test_model_effect_trend_reverses_score_direction_without_changing_effect():
    rows = [
        {"day": "2026-09-01", "model": "m", "score_bin": 0, "score_valid_cnt": 20, "fpd7_base": 10, "fpd7_bad": 2},
        {"day": "2026-09-01", "model": "m", "score_bin": 1, "score_valid_cnt": 20, "fpd7_base": 10, "fpd7_bad": 8},
    ]
    result = build_model_effect_trend(rows, [{"day": "2026-09-01", "applications": 40, "loan_success": 40}])
    assert result[0]["auc"] == 0.8
    assert result[0]["ks"] == 0.6


def test_model_effect_trend_blanks_immature_dates_instead_of_zero():
    result = build_model_effect_trend(
        [{"day": "2026-09-01", "model": "m", "score_bin": 0, "score_valid_cnt": 20, "fpd7_base": 10, "fpd7_bad": 4}],
        [{"day": "2026-09-01", "applications": 100, "loan_success": 100}],
    )
    assert result[0]["maturity_warning"] is True
    assert result[0]["auc"] is None
    assert result[0]["ks"] is None
```

- [ ] **Step 2: Run the tests to verify they fail**

Run `python -m pytest server/test_model_monitoring.py -q`。
Expected: FAIL because `build_model_effect_trend` does not exist。

- [ ] **Step 3: Implement the minimal pure calculation**

在 `server/model_monitoring.py` 中按 `(day, model)` 分组，按 `score_bin` 升序累计好/坏样本；使用秩概率计算 AUC，再取 `max(auc, 1 - auc)`；使用累计坏样本率与好样本率的最大绝对差计算 KS。成熟度不足时保留样本量与覆盖率，但将 `auc`、`ks` 置为 `None`。

- [ ] **Step 4: Run the focused tests**

Run `python -m pytest server/test_model_monitoring.py -q`。
Expected: PASS。

- [ ] **Step 5: Commit the pure calculation**

Run `git add server/model_monitoring.py server/test_model_monitoring.py && git commit -m "feat: calculate daily multi-model auc ks"`。

### Task 2: 接入 MaxCompute 逐日模型聚合接口

**Files:**
- Modify: `server/app.py`
- Modify: `server/model_monitoring.py`

**Interfaces:**
- `AttributionService.model_monitoring(partition: str | None = None, force: bool = False)` 继续作为服务入口。
- `/api/model-monitoring` 增加 `model_effect_trend`、`latest_model_effect`，保留 `model_coverage` 和业务环节概览。

- [ ] **Step 1: Write the failing service test**

增加一个注入 `_run_sql_rows` 的服务测试，断言生成的 SQL 包含 `WHERE pt = '20260910'`、每个模型字段的聚合、`score_bin`，并断言返回的 `model_effect_trend` 使用纯函数结果；同时断言非法分区不执行查询。

```python
def test_model_monitoring_rejects_bad_partition_before_query(monkeypatch):
    service = AttributionService()
    called = False

    def fail_if_called(_sql):
        nonlocal called
        called = True
        raise AssertionError("invalid partition must not query MaxCompute")

    monkeypatch.setattr(service, "_run_sql_rows", fail_if_called)
    with pytest.raises(AttributionServiceError, match="分区"):
        service.model_monitoring(partition="2026-09-10", force=True)
    assert called is False
```

该测试先验证输入防护；真实 SQL 的分区条件和模型字段由 Task 2 的集成检查验证，避免在离线单元测试中重复模拟 MaxCompute。

- [ ] **Step 2: Run the test to verify it fails**

Run `python -m pytest server/test_model_monitoring.py -q`。
Expected: FAIL because the service does not yet request model-by-day score buckets or return `model_effect_trend`。

- [ ] **Step 3: Add one UNION ALL aggregation query**

对 `MODEL_SCORES` 逐个生成同构 SQL：

```sql
SELECT event_date AS day,
       '<score_field>' AS model,
       FLOOR(CAST(<score_field> AS DOUBLE) / 50) AS score_bin,
       COUNT(*) AS score_valid_cnt,
       SUM(CASE WHEN fpd7_fm_dd = 1 THEN 1 ELSE 0 END) AS fpd7_base,
       SUM(CASE WHEN fpd7_fz_dd = 1 THEN 1 ELSE 0 END) AS fpd7_bad,
       SUM(CASE WHEN fpd30_fm_dd = 1 THEN 1 ELSE 0 END) AS fpd30_base,
       SUM(CASE WHEN fpd30_fz_dd = 1 THEN 1 ELSE 0 END) AS fpd30_bad,
       SUM(CASE WHEN term3_fm_dd = 1 THEN 1 ELSE 0 END) AS term3_base,
       SUM(CASE WHEN term3_fz_dd = 1 THEN 1 ELSE 0 END) AS term3_bad
FROM pb_biz_credit.ng_cash_model_monitoring_df
WHERE pt = '20260910' AND event_date IS NOT NULL
  AND <score_field> IS NOT NULL AND <score_field> <> ''
  AND CAST(<score_field> AS DOUBLE) >= 0
GROUP BY event_date, FLOOR(CAST(<score_field> AS DOUBLE) / 50)
```

以一条 SQL 读取结果后，分别生成 FPD7、FPD30、TERM3 三套趋势数据，并按最新可用日期生成 `latest_model_effect`。

- [ ] **Step 4: Run unit and live aggregation checks**

Run `python -m py_compile server/app.py server/model_monitoring.py` and `python -m pytest server/test_model_monitoring.py -q`。
Then run the real `pt=20260910` aggregation and assert that models with empty scores have no effect rows, `op_v2_score` has non-empty rows, and no trend metric is zero solely because of maturity filtering。

- [ ] **Step 5: Commit the API change**

Run `git add server/app.py server/model_monitoring.py server/test_model_monitoring.py && git commit -m "feat: expose multi-model effect trend api"`。

### Task 3: 更新前端数据类型和多模型趋势视图

**Files:**
- Modify: `src/lib/modelMonitoringApi.ts`
- Modify: `src/pages/ModelEffectiveness.tsx`
- Modify: `src/App.tsx` only if the page import/render contract changes

**Interfaces:**
- `ModelMonitoringPayload.model_effect_trend` 为 `ModelEffectTrend[]`。
- 前端支持目标标签 `fpd7 | fpd30 | term3` 和效果指标 `auc | ks`。

- [ ] **Step 1: Define the frontend contract before the page binding**

在 `src/lib/modelMonitoringApi.ts` 增加如下类型，确保 null 语义保留到 ECharts：

```typescript
export type EffectMetric = 'auc' | 'ks';
export type TargetMetric = 'fpd7' | 'fpd30' | 'term3';
export interface ModelEffectTrend {
  day: string;
  model: string;
  auc: number | null;
  ks: number | null;
  mature_count: number;
  bad_count: number;
  good_count: number;
  score_valid_count: number;
  score_coverage: number | null;
  maturity_warning: boolean;
  target: TargetMetric;
}
```

页面内的图表映射使用 `row[metric]`，不得使用 `Number(row[metric] ?? 0)`，从而保留成熟度不足日期的断线。

- [ ] **Step 2: Run the frontend contract check**

Run `npm run build`。
Expected: 当前实现未绑定新接口字段时保持通过；完成页面绑定后，TypeScript 会检查字段名称、null 类型和切换枚举。

- [ ] **Step 3: Implement the model effect UI**

在 `ModelEffectiveness.tsx` 中增加：

- AUC/KS segmented control。
- FPD7/FPD30/TERM3 segmented control。
- 模型多选/图例开关；默认选有效覆盖率最高的模型。
- 多模型效果趋势折线图，null 断线。
- 有效分覆盖率趋势图。
- 模型最新表现表，显示最新可用日期、AUC、KS、成熟样本量、覆盖率和状态。
- 保留业务环节概览卡，移除“OP V2 唯一主模型”文案。

- [ ] **Step 4: Run frontend checks**

Run `npx eslint src/pages/ModelEffectiveness.tsx src/lib/modelMonitoringApi.ts` and `npm run build`。
Expected: 新增文件 lint 通过，Vite 构建通过。

- [ ] **Step 5: Commit the frontend change**

Run `git add src/pages/ModelEffectiveness.tsx src/lib/modelMonitoringApi.ts src/App.tsx && git commit -m "feat: compare model effects over time"`。

### Task 4: 真实数据与页面验收

**Files:**
- Verify: `server/test_model_monitoring.py`
- Verify: `server/app.py`
- Verify: `src/pages/ModelEffectiveness.tsx`

- [ ] **Step 1: Run the regression suite**

Run `python -m pytest server/test_attribution_query_tools.py server/test_model_monitoring.py -q`。
Expected: all tests pass。

- [ ] **Step 2: Verify the live route**

Restart the local API process, request `/openapi.json`, and verify `/api/model-monitoring` is registered. Querying the protected route requires the existing login session; do not automate password entry.

- [ ] **Step 3: Verify the displayed behavior**

Open `http://127.0.0.1:3000/?page=model` after login and confirm the model selector, AUC/KS switch, FPD target switch, null gaps, coverage trend, and latest model table are visible.

- [ ] **Step 4: Commit only task files**

Run `git diff --check` and inspect `git status --short`; do not stage unrelated existing changes.
