# Unified Attribution Tab Monitor Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 将授信归因监控与资金归结监控统一到一个页面，并通过 Tab 切换；资金 Tab 严格复用授信归因页的 UI、交互、快照存储和规则状态生命周期。

**Architecture:** 保留现有授信归因实现不变，在 `App` 中增加统一归因页容器。资金 Tab 新建授信页同构视图，复用现有 `ChartCard`、`FeishuTable`、ECharts、状态存储类和 pipeline 快照读写模块；资金计算继续由 `FundAttributionRunner` 负责，并将结果发布到独立的 DuckDB/serving 目录。

**Tech Stack:** React 19 + TypeScript + Vite + Framer Motion + ECharts；FastAPI + Python 3.10 + pandas + DuckDB + Parquet + SQLite；pytest；openpyxl 仅用于样本 XLSX 只读核验。

## Global Constraints

- 页面唯一入口使用 `page=attribution`；旧 `page=fundMonitor` 必须进入统一页面的资金 Tab。
- 授信 Tab 需要 `attribution` 权限，资金 Tab 需要 `fundMonitor` 权限；后端两个 API 权限不合并。
- 资金计算必须使用 DOCX v1.2：最新 1/3/7 天观察期，观察期外全部历史作为对应基准期。
- 资金阈值必须保持 Level1：5/1.5/1.5/z2，Level2：10/2/2/z3，Level3：20/3/3/z5，四项同时满足。
- 资金 Top-K 必须保持单维全量→内部 Top10→二级→内部 Top5→三级终止；专家强制规则不改变指标和门槛。
- 不新增资金专属 KPI 卡、关系图、自由布局或授信字段以外的视觉模式。
- 不修改授信归因计算逻辑；每个任务必须跑与其范围对应的测试或构建命令。
- 不提交真实凭证、原始客户标识、Office 临时锁文件、运行缓存或生成的数据库。

---

## 文件地图

### 统一页面与前端

- Modify: `src/App.tsx` — 合并导航项、兼容旧 URL、渲染统一归因页。
- Create: `src/pages/AttributionMonitor.tsx` — Tab 容器、权限判断、默认 Tab 和旧链接状态映射。
- Create: `src/pages/FundAttribution.tsx` — 以 `CreditAttribution.tsx` 为版式基线的资金同构页面。
- Modify: `src/pages/FundMonitor.tsx` — 保留旧 import 的兼容导出，不再保留旧的独立页面实现。
- Modify: `src/lib/fundMonitorApi.ts` — 对齐资金同构页面所需的状态历史、趋势和结果字段类型。
- Create: `src/lib/attributionTab.ts` — 纯函数处理 Tab、旧 page 参数和权限默认值，便于测试。
- Create: `tests/attributionTab.test.mjs` — 统一页面 URL/Tab 纯函数测试。

### 资金后端与快照

- Create: `server/fund_pipeline/__init__.py` — 定义资金 DuckDB 与 serving 目录。
- Create: `server/fund_pipeline/cli.py` — 资金计算、路径日序列聚合、DuckDB 持久化、Parquet 发布。
- Modify: `server/fund_service.py` — 接入资金 serving 快照优先读取、在线计算兜底和异步刷新语义。
- Modify: `server/fund_attribution.py` — 仅补齐快照 pipeline 需要的稳定 payload 元数据或路径序列接口，不改 v1.2 指标口径。
- Create: `server/test_fund_pipeline.py` — 资金 pipeline 写入/发布/读取测试。

### 样本核验

- Create: `server/verify_fund_sample.py` — 读取外部 XLSX 的固定单元格，与资金 dashboard JSON 做数值和结果结构核验。
- Create: `server/test_verify_fund_sample.py` — 使用临时 workbook/payload fixture 验证核验器的单元格映射、容差和失败信息。
- Modify: `README.md` — 补充统一页面启动方式、资金 pipeline 命令和样本核验命令。

---

## Task 1: 固化统一 Tab 的纯函数契约

**Files:**
- Create: `src/lib/attributionTab.ts`
- Create: `tests/attributionTab.test.mjs`

**Interfaces:**

```ts
export type AttributionTab = 'credit' | 'fund';

export function normalizeAttributionTab(value: string | null): AttributionTab;
export function normalizePageParam(page: string | null): 'overview' | 'attribution' | string;
export function defaultAttributionTab(canCredit: boolean, canFund: boolean): AttributionTab | null;
export function buildAttributionUrl(currentUrl: string, tab: AttributionTab): string;
```

- [ ] **Step 1: Write failing tests** for `fund`, invalid/missing Tab, `page=fundMonitor` compatibility, no-permission result, and URL cleanup.

```js
import test from 'node:test';
import assert from 'node:assert/strict';
import {
  normalizeAttributionTab,
  normalizePageParam,
  defaultAttributionTab,
  buildAttributionUrl,
} from '../src/lib/attributionTab.ts';

test('normalizes fund tab and invalid values', () => {
  assert.equal(normalizeAttributionTab('fund'), 'fund');
  assert.equal(normalizeAttributionTab('bad'), 'credit');
  assert.equal(normalizeAttributionTab(null), 'credit');
});

test('maps legacy fund page to unified attribution page', () => {
  assert.equal(normalizePageParam('fundMonitor'), 'attribution');
  assert.equal(normalizePageParam('attribution'), 'attribution');
});

test('chooses a tab only when the user has permission', () => {
  assert.equal(defaultAttributionTab(true, true), 'credit');
  assert.equal(defaultAttributionTab(false, true), 'fund');
  assert.equal(defaultAttributionTab(false, false), null);
});

test('writes tab without changing unrelated query parameters', () => {
  const result = buildAttributionUrl('http://localhost/?page=fundMonitor&pt=20260903', 'fund');
  assert.equal(result, 'http://localhost/?page=attribution&pt=20260903&tab=fund');
});
```

- [ ] **Step 2: Run the focused test and verify it fails**.

Run: `node --experimental-transform-types --test tests/attributionTab.test.mjs`

Expected: FAIL because `src/lib/attributionTab.ts` does not exist.

- [ ] **Step 3: Implement the four pure functions** with only the accepted values `credit` and `fund`; map legacy `fundMonitor` to `attribution`; preserve every query key other than `page` and `tab`.

- [ ] **Step 4: Run the focused test and verify it passes**.

Run: `node --experimental-transform-types --test tests/attributionTab.test.mjs`

Expected: 4 passing tests and 0 failures.

- [ ] **Step 5: Commit**.

```powershell
git add src/lib/attributionTab.ts tests/attributionTab.test.mjs
git commit -m "feat: define unified attribution tab routing"
```

## Task 2: Add the unified page container and merge navigation

**Files:**
- Create: `src/pages/AttributionMonitor.tsx`
- Modify: `src/App.tsx`

**Interfaces:**

`AttributionMonitor` receives the already authenticated `AuthUser` from `App`, reads the current URL, renders only tabs for which the user has permission, and renders exactly one child page:

```tsx
<AttributionMonitor user={session.user} />
// child: <CreditAttribution /> or <FundAttribution />
```

- [ ] **Step 1: Add a failing routing assertion** to `tests/attributionTab.test.mjs` that the unified URL uses `page=attribution`, and that selecting the fund tab stores `tab=fund`.

- [ ] **Step 2: Run the focused test and verify it fails** with the current URL helper behavior.

Run: `node --experimental-transform-types --test tests/attributionTab.test.mjs`

Expected: FAIL on the new unified-page assertion.

- [ ] **Step 3: Implement `AttributionMonitor.tsx`** with a small top tab bar using the same border, typography, spacing and `theme-select`/button conventions already used in `CreditAttribution.tsx`.

Required behavior:

```tsx
const canCredit = hasPermission(user, 'attribution');
const canFund = hasPermission(user, 'fundMonitor');
const tab = normalizeAttributionTab(new URLSearchParams(window.location.search).get('tab'));
const activeTab = canCredit ? (tab === 'fund' && canFund ? 'fund' : 'credit') : canFund ? 'fund' : null;
```

If `activeTab` is `null`, render the existing permission-denied state. Clicking a tab updates only `page=attribution&tab=...` and preserves the remaining share parameters.

- [ ] **Step 4: Modify `App.tsx`** so the navigation has one item named `归因监控`, visible when either `attribution` or `fundMonitor` permission exists; render `<AttributionMonitor />` for `page === 'attribution'`; normalize an incoming `page=fundMonitor` to the unified page before initial state selection.

- [ ] **Step 5: Run build and focused tests**.

Run: `node --test tests/attributionTab.test.mjs`

Expected: all routing tests pass.

Run: `npm run build`

Expected: TypeScript and Vite build complete with exit code 0.

- [ ] **Step 6: Commit**.

```powershell
git add src/pages/AttributionMonitor.tsx src/App.tsx src/lib/attributionTab.ts tests/attributionTab.test.mjs
git commit -m "feat: add unified attribution monitor page"
```

## Task 3: Build the fund result contract for the授信同构 UI

**Files:**
- Modify: `src/lib/fundMonitorApi.ts`
- Modify: `server/fund_attribution.py` only where the payload contract is incomplete
- Test: `server/test_fund_attribution.py`

**Interfaces:**

The fund UI consumes these existing API functions without changing endpoint names:

```ts
fetchFundAttribution(pt?: string, force?: boolean, offset?: number): Promise<FundDashboard>;
fetchFundPartitions(force?: boolean): Promise<{ partitions: string[]; ranges?: Record<string, { min: string; max: string }> }>;
fetchFundPathTrend(recordId: string, pt?: string, offset?: number): Promise<FundPathTrend>;
updateFundRuleStatus(canonicalPath: string, status: RuleStatus, actionPt: string, rule?: FundRecord): Promise<...>;
fetchFundRuleStatusHistory(): Promise<{ records: FundRuleStatusHistory[] }>;
```

- [ ] **Step 1: Add or tighten failing tests** for the exact v1.2 payload contract: `meta.partition`, `meta.offset_days`, `meta.cache_hit`, `summary`, `window_overview`, `merged_alerts`, `top_k`, `expert`, `review_items`, `suppressed_alerts`, `rules`, and `daily_trend`.

- [ ] **Step 2: Run the focused backend tests**.

Run: `python -m pytest -q --basetemp=E:\agent\monitor\.pytest_tmp_plan server/test_fund_attribution.py`

Expected: existing fund attribution tests pass before contract changes; any failure identifies a real contract gap rather than a pytest temp-directory permission error.

- [ ] **Step 3: Update only the missing contract fields**. Preserve the formulas in `FundMetrics.window_metrics`, the full-history date split in `FundMetrics._build_window_specs`, and the Top-K/expert orchestration in `FundAttributionRunner.run`.

- [ ] **Step 4: Add tests for workbook-aligned summary values using the existing synthetic runner seam**: total order count, abnormal order count, three window day counts, expert forced single count, and zero formal alerts for the supplied result shape.

- [ ] **Step 5: Run the backend tests again**.

Run: `python -m pytest -q --basetemp=E:\agent\monitor\.pytest_tmp_plan server/test_fund_attribution.py`

Expected: all tests pass.

- [ ] **Step 6: Commit**.

```powershell
git add src/lib/fundMonitorApi.ts server/fund_attribution.py server/test_fund_attribution.py
git commit -m "test: lock fund attribution result contract"
```

## Task 4: Add the fund DuckDB and serving snapshot pipeline

**Files:**
- Create: `server/fund_pipeline/__init__.py`
- Create: `server/fund_pipeline/cli.py`
- Modify: `server/fund_service.py`
- Create: `server/test_fund_pipeline.py`

**Interfaces:**

`server/fund_pipeline/__init__.py` exports:

```python
DB_PATH = SERVER_DIR / "data" / "fund_attribution.duckdb"
SERVING_DIR = SERVER_DIR / "data" / "fund_serving"
```

`server/fund_pipeline/cli.py` exports:

```python
def build_path_rows(runner: FundAttributionRunner, result: dict[str, Any]) -> list[dict[str, Any]]: ...
def compute_and_publish(service: FundAttributionService, pt: str, offset: int, source: str) -> dict[str, Any]: ...
```

The pipeline reuses `pipeline.store`, `pipeline.exporter`, and `pipeline.assemble` against the independent fund DB and serving directory. The existing `attr_*` table names are safe because the database file is independent.

- [ ] **Step 1: Write failing pipeline tests** for atomic publish/read and path daily rows.

```python
def test_fund_pipeline_publishes_dashboard_and_path_snapshots(tmp_path, monkeypatch):
    # Use a fake FundAttributionService and a fake runner with one alert path.
    # Assert dashboard_<pt>_<offset>.parquet and path_daily_<pt>_<offset>.parquet exist.
    # Assert assemble.read_dashboard_snapshot() returns the same payload.
    # Assert assemble.read_path_daily_frame() returns the path's daily rows.
    assert False
```

- [ ] **Step 2: Run the new test and verify it fails**.

Run: `python -m pytest -q --basetemp=E:\agent\monitor\.pytest_tmp_plan server/test_fund_pipeline.py::test_fund_pipeline_publishes_dashboard_and_path_snapshots`

Expected: FAIL because `server/fund_pipeline/` does not exist.

- [ ] **Step 3: Implement `fund_pipeline/__init__.py`** with the two independent paths and create parent directories only when a writer runs.

- [ ] **Step 4: Implement `build_path_rows()`** using `FundAttributionRunner.path_daily_batch()` for `merged_alerts` and `suppressed_alerts`, the runner's full date index, and the fields required by `pipeline.exporter`: `alert_id`, `date`, `application_count`, `total_application_count`, `approval_count=None`, `cid_cnt=None`, `approval_cid_cnt=None`.

- [ ] **Step 5: Implement `compute_and_publish()`**:

```python
runner = FundAttributionRunner(
    config=service.config,
    table=service.table_name,
    partition=pt,
    offset=offset,
    query_rows=service._run_sql_rows,
)
result = json_safe(runner.run())
path_rows = build_path_rows(runner, result)
conn = store.connect(DB_PATH)
run_id = store.persist_result(
    conn,
    result=result,
    path_rows=path_rows,
    pt=pt,
    offset=offset,
    config=service.config,
    duration_ms=duration_ms,
    source=source,
)
exporter.export_snapshot(DB_PATH, SERVING_DIR, run_id=run_id, pt=pt, offset=offset)
```

The implementation must close the DuckDB connection in `finally` and publish through the existing atomic Parquet writer.

- [ ] **Step 6: Update `FundAttributionService.dashboard()`** to check the serving snapshot before JSON disk cache, adopt a newer serving snapshot by `meta.generated_at`, and keep JSON disk cache as an online fallback. Keep `force=true` behavior: return the last result with `async_refresh=true`, run `_compute_and_cache()` in a background thread, and let the UI poll `generated_at`.

- [ ] **Step 7: Update `FundAttributionService.path_trend()`** to read `path_daily_<pt>_<offset>.parquet` through `pipeline.assemble` when available; format the same fund daily fields (`abnormal_order_count`, `order_count`, `abnormal_rate`) and fall back to the record payload when the snapshot is not present.

- [ ] **Step 8: Run the pipeline tests**.

Run: `python -m pytest -q --basetemp=E:\agent\monitor\.pytest_tmp_plan server/test_fund_pipeline.py server/test_fund_service_api.py`

Expected: all pipeline and service tests pass; no write occurs in the credit `attribution.duckdb` or `serving` directory.

- [ ] **Step 9: Commit**.

```powershell
git add server/fund_pipeline server/fund_service.py server/test_fund_pipeline.py
git commit -m "feat: publish fund attribution serving snapshots"
```

## Task 5: Replace the free-form fund page with a授信同构 page

**Files:**
- Create: `src/pages/FundAttribution.tsx`
- Modify: `src/pages/FundMonitor.tsx`

**Interfaces:**

`FundAttribution.tsx` owns the fund-specific versions of the same state groups used by `CreditAttribution.tsx`: selected partition, offset, filters, selected record, path trend request, rule status tab/history, loading/error, share URL, screenshot, and trend range.

It must use:

```tsx
import ChartCard from '@/components/ChartCard';
import FeishuTable, { StatusTag, type FeishuColumn } from '@/components/FeishuTable';
import ReactECharts from 'echarts-for-react';
import { baseOption } from '@/lib/chartTheme';
```

- [ ] **Step 1: Create a snapshot of the current授信 page structure** by copying only the render/state skeleton from `src/pages/CreditAttribution.tsx`; do not copy approval-specific labels or credit API calls into the final file.

- [ ] **Step 2: Replace API and type imports** with `fundMonitorApi.ts`; keep the same load lifecycle, latest-request protection, refresh polling, status history loading, selected-path scroll, share/screenshot behavior, and filter layout.

- [ ] **Step 3: Replace the result columns** with the exact fund fields:

```ts
status;
level_label;
source;
path;
layer;
anomaly_type;
primary_window_label;
observation_abnormal_count;
growth_factor;
rate_lift_factor;
z_score;
excess_abnormal_count;
```

Keep status editing, path click, hover full-path tooltip, sticky level column, source tags and `FeishuTable` styling identical to the授信 page.

- [ ] **Step 4: Implement the selected fund path trend** as the same `ChartCard` composition and ECharts option shape, with a bar for `abnormal_order_count`, a line for `abnormal_rate`, a baseline daily abnormal-order mark line, and the primary observation-window mark area.

- [ ] **Step 5: Implement the three fund window cards** in the same order and style. Display abnormal counts, abnormal rates, daily counts, growth factor, rate-lift factor, z-score, excess abnormal count, and special labels. Do not display approval rate or CID rate.

- [ ] **Step 6: Implement the bottom audit/threshold cards** with `suppression_rules`, `thresholds`, `field_labels`, and `meta.note` from the fund dashboard. Keep the授信 page's card spacing, typography, colors, and collapse behavior.

- [ ] **Step 7: Replace `src/pages/FundMonitor.tsx` with a compatibility export**:

```tsx
export { default } from './FundAttribution';
```

- [ ] **Step 8: Run TypeScript build**.

Run: `npm run build`

Expected: exit code 0; no import remains from the old free-form fund implementation.

- [ ] **Step 9: Commit**.

```powershell
git add src/pages/FundAttribution.tsx src/pages/FundMonitor.tsx src/lib/fundMonitorApi.ts
git commit -m "feat: make fund attribution UI mirror credit monitor"
```

## Task 6: Add Excel-based sample verification

**Files:**
- Create: `server/verify_fund_sample.py`
- Modify: `README.md`

**Interfaces:**

```powershell
python server/verify_fund_sample.py `
  --xlsx "C:\Users\PP-2026070302\Desktop\daddayup\2026\资金归结\中介团伙异常订单归因_20260905样本_v1.2_全历史基准期运行结果.xlsx" `
  --payload path\to\fund-dashboard.json
```

The verifier reads these sheets and checks these values with exact integer equality and `1e-9` relative tolerance for floating-point fields:

- `结论摘要`: 60 effective dates, 867724 total orders, 2409 abnormal orders, final formal alerts 0, expert forced singles 3.
- `窗口总览`: observation days 1/3/7, baseline days 59/57/53, and the baseline/observation counts, rates, factors and z-scores.
- `专家_强制单维结果`: 3 rows and the three lifecycle paths.
- `大盘日趋势`: 60 daily dates, abnormal order count, total order count, and abnormal rate.

- [ ] **Step 1: Write the verifier test** with a temporary workbook/payload fixture containing the same sheet names and expected cells.

- [ ] **Step 2: Run it and verify it fails** because the verifier does not exist.

Run: `python -m pytest -q --basetemp=E:\agent\monitor\.pytest_tmp_plan server/test_verify_fund_sample.py`

Expected: FAIL with module-not-found or command-not-found.

- [ ] **Step 3: Implement the verifier** using `openpyxl.load_workbook(..., read_only=True, data_only=True)` and explicit sheet/cell mappings; never write to the supplied XLSX.

- [ ] **Step 4: Run the fixture test and then run the real workbook check** against a captured funds dashboard payload.

Run: `python -m pytest -q --basetemp=E:\agent\monitor\.pytest_tmp_plan server/test_verify_fund_sample.py`

Expected: all fixture tests pass.

Run: the PowerShell command above with the supplied workbook and a real `fund-dashboard.json`.

Expected: all summary, window, expert-path and daily-trend checks pass; mismatches print sheet/cell/expected/actual.

- [ ] **Step 5: Document the verification command** in `README.md` without embedding the external Desktop path as a project default.

- [ ] **Step 6: Commit**.

```powershell
git add server/verify_fund_sample.py server/test_verify_fund_sample.py README.md
git commit -m "test: verify fund attribution against sample workbook"
```

## Task 7: Full verification and visual handoff

**Files:**
- No new source files; inspect the changes from Tasks 1–6.

- [ ] **Step 1: Run frontend tests and build**.

Run: `node --test tests/attributionTab.test.mjs`

Expected: all routing tests pass.

Run: `npm run build`

Expected: TypeScript and Vite build complete with exit code 0.

- [ ] **Step 2: Run the complete fund backend suite with a workspace-local pytest base directory**.

Run: `python -m pytest -q --basetemp=E:\agent\monitor\.pytest_tmp_plan server/test_fund_attribution.py server/test_fund_pipeline.py server/test_fund_service_api.py`

Expected: all selected fund tests pass; the command avoids the known Windows permission failure under the global pytest temp directory.

- [ ] **Step 3: Start the frontend and API**, then open `/?page=attribution&tab=credit` and `/?page=attribution&tab=fund`.

Expected: both tabs render the same page skeleton; only labels, columns, metrics and data source differ.

- [ ] **Step 4: Verify interactions manually**: switch tabs, select partition, change offset, refresh, filter level/source/layer/type/window, click a path, change trend range, copy share link, capture screenshot, update status, open status history, and open legacy `/?page=fundMonitor`.

Expected: legacy URL opens the fund Tab inside the unified page; credit behavior is unchanged; fund path trends and status history use fund data.

- [ ] **Step 5: Inspect git status** and confirm only intended source/docs/test files are staged; do not stage existing unrelated `.pytest_tmp_*`, logs, screenshots, local databases or credentials.

- [ ] **Step 6: Commit the verification-only fixes**, if any, as one final commit.

```powershell
git add src server tests README.md
git commit -m "test: verify unified attribution monitor"
```
