# Model Effect Table BI Style Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 将模型效果监控页面的展示层优化为正式 BI 表格风格，同时保持现有接口、计算逻辑和筛选交互不变。

**Architecture:** 继续使用 `ModelEffectiveness.tsx` 作为模型效果页面容器和表格组件，不新增后端接口。通过 Tailwind 类调整工具条、两层表头、固定列和指标单元格样式；通过局部 CSS/sticky 类保证横向滚动时模型身份列始终可见。

**Tech Stack:** React 18, TypeScript, Tailwind CSS, lucide-react, Vite。

## Global Constraints

- 不修改模型效果后端查询、周度聚合、成熟度判断和接口字段。
- 不新增趋势图、分页、导出或新的筛选维度。
- 保留筛选先编辑、点击“查询”后应用的现有交互。
- 保留黄色“查询”按钮和现有中文字段口径。
- 固定列必须在横向滚动时保持可读，周数据区必须可以横向滚动。

---

### Task 1: Add focused visual regression assertions

**Files:**
- Modify: `src/pages/ModelEffectiveness.tsx`
- Test: browser accessibility state at `http://127.0.0.1:3000/?page=model`

**Interfaces:**
- Consumes: existing `ModelMonitoringPayload`, `ModelEffectWeekly`, `TargetMetric` and `fetchModelMonitoring` interfaces.
- Produces: unchanged page-level controls and table semantics with stable labels for browser verification.

- [ ] **Step 1: Capture the current acceptance selectors and table semantics**

Verify the running page exposes these labels before editing:

```text
筛选器
选择业务环节
选择目标变量
查询
模型编码
模型名称
count
badrate
AUC
KS
```

Run: browser accessibility inspection for `http://127.0.0.1:3000/?page=model`

Expected: the controls and two table header rows are present.

- [ ] **Step 2: Keep stable testable labels while restyling**

Do not rename the existing `aria-label` values or table header text. The visual changes in later steps must be verifiable from the same labels and from the changed layout classes.

- [ ] **Step 3: Re-check the acceptance surface**

Run: the same browser accessibility inspection after the implementation.

Expected: the controls, two table header rows, grouped dates, model rows, and footer metric note remain present.

### Task 2: Restyle the filter toolbar and page framing

**Files:**
- Modify: `src/pages/ModelEffectiveness.tsx`

**Interfaces:**
- Consumes: the existing `load`, `alias`, `target`, `appliedAlias`, and `appliedTarget` state.
- Produces: a compact toolbar with the same button actions and filter state behavior.

- [ ] **Step 1: Replace the plain page wrapper with a BI content surface**

Use a page background of `#f5f7fa`, a white content surface, and a thin neutral border. Keep the table and footer inside the same surface so the screen reads as one monitoring card.

- [ ] **Step 2: Add hierarchy to the filter toolbar**

Use a light gray toolbar background, a small uppercase/secondary label treatment for “筛选器”, 32px controls, and a consistent 8px gap. Keep the yellow query button and make “刷新数据” a neutral outlined secondary action.

- [ ] **Step 3: Preserve loading and error states**

Apply the same neutral surface to loading/error states and keep the existing `RefreshCw`, `AlertTriangle`, retry, and error message behavior unchanged.

### Task 3: Restyle grouped headers, frozen identity columns, and metric cells

**Files:**
- Modify: `src/pages/ModelEffectiveness.tsx`

**Interfaces:**
- Consumes: existing `weeks`, `models`, `rowByKey`, and `formatTableValue` helpers.
- Produces: the same table data with BI-grade visual hierarchy and horizontal scrolling.

- [ ] **Step 1: Introduce explicit table dimensions and scroll container**

Keep the horizontal scroll container and give the table a minimum width based on the two identity columns plus four metric columns per week. Use `border-separate`/`border-spacing-0` or equivalent classes so borders remain thin and controlled.

- [ ] **Step 2: Style the two-level header**

Use a dark slate text color, a blue-gray background for date groups, a lighter gray-blue background for metric subheaders, and a sticky top header if it does not break the existing page scroll. Keep date groups centered and metric labels centered.

- [ ] **Step 3: Freeze the two identity columns**

Add `position: sticky` classes to the model code and model name cells with explicit left offsets, white backgrounds, z-index above body cells, and a subtle right-side shadow on the model-name column. Ensure header cells use higher z-index than body cells.

- [ ] **Step 4: Add body readability states**

Use thin `#d9e1ea` borders, alternating very light row backgrounds, a hover background, compact vertical padding, and tabular numerals. Keep model code/name left aligned and metric values right aligned.

- [ ] **Step 5: Add restrained AUC/KS status coloring**

Derive a small display class from the numeric metric value only in the component:

```ts
function metricTone(value: number | null | undefined): string {
  if (value == null) return 'text-slate-400';
  if (value >= 0.7) return 'bg-emerald-50 text-emerald-700';
  if (value >= 0.6) return 'bg-amber-50 text-amber-700';
  return 'bg-rose-50 text-rose-700';
}
```

Apply it as a light background/text treatment to AUC and KS cells only; do not change values or add badges.

### Task 4: Run regression and visual verification

**Files:**
- Modify: none unless verification finds a scoped issue in `src/pages/ModelEffectiveness.tsx`
- Verify: `src/pages/ModelEffectiveness.tsx`, `src/lib/modelMonitoringApi.ts`

**Interfaces:**
- Consumes: local Vite app, running attribution API, and existing model monitoring test suite.
- Produces: a verified BI-styled table with unchanged controls and data semantics.

- [ ] **Step 1: Run frontend lint**

Run: `npx eslint src/pages/ModelEffectiveness.tsx src/lib/modelMonitoringApi.ts`

Expected: exit code 0 with no errors or warnings.

- [ ] **Step 2: Run focused backend regression tests**

Run: `python -m pytest server/test_model_monitoring.py server/test_attribution_query_tools.py -q`

Expected: all existing focused tests pass; no backend file changes are required for this visual task.

- [ ] **Step 3: Run production build**

Run: `npm run build`

Expected: TypeScript compilation and Vite build exit with code 0. Existing Browserslist/chunk-size warnings may remain.

- [ ] **Step 4: Verify the browser surface**

Open `http://127.0.0.1:3000/?page=model` and verify:

```text
- toolbar is compact and visually separated from the table
- date groups and metric subheaders have distinct light backgrounds
- first two columns remain visible while horizontal scrolling
- rows have thin borders, alternating background, and hover highlight
- AUC/KS use restrained status colors
- CASHBO + FPD7 and CASHJQ + FPD30 still change the table after clicking 查询
```

Expected: no browser console errors/warnings and no change to displayed metric values caused by the visual refactor.

- [ ] **Step 5: Commit the implementation**

```bash
git add src/pages/ModelEffectiveness.tsx
git commit -m "feat: refine model effect table BI styling"
```

