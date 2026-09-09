# 资金归因结果区 Tab Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans (inline execution is appropriate for this small UI change).

**Goal:** 在资金归因“合并预警结果”内容区增加“合并预警结果 / 大盘日趋势”同级 Tab，并按要求用柱状图展示每日异常订单、折线图展示每日异常率。

**Architecture:** 保留 `FundAttribution.tsx` 当前 dashboard 数据流和规则处理子 Tab。将大盘趋势 ECharts option 提取为纯函数，页面 Tab 仅负责选择内容，避免改变后端接口或计算逻辑。

**Tech Stack:** React 19, TypeScript, ECharts 6, `echarts-for-react`, Node built-in test runner.

## Global Constraints

- 仅修改资金归因前端展示和前端测试，不修改后端计算、缓存和 API。
- 默认展示“合并预警结果”；“大盘日趋势”复用 `dashboard.daily_trend`。
- 每日异常订单使用柱状图，每日异常率使用折线图及右侧百分比坐标轴。

---

### Task 1: Add result tabs and the market trend chart

**Files:**
- Create: `src/lib/fundDailyTrend.ts`
- Modify: `src/pages/FundAttribution.tsx`
- Test: `tests/fundDailyTrend.test.mjs`

**Interfaces:**
- `buildFundDailyTrendOption(points, colors, baseOption)` consumes `FundDailyPoint[]`-compatible records and returns an ECharts option with one bar series (`异常订单数`) and one line series (`异常率`).
- `FundAttribution.tsx` imports the helper, owns `resultTab: 'alerts' | 'trend'`, and renders the existing rule-status content or the trend chart inside the same `ChartCard`.

- [ ] **Step 1: Write the failing test**

  Add tests asserting that the trend option contains exactly two series, with `type: 'bar'` for abnormal orders and `type: 'line'` with `yAxisIndex: 1` for abnormal rate, and that both series preserve the input dates/values.

- [ ] **Step 2: Run the test to verify it fails**

  Run `node --experimental-transform-types --test tests/fundDailyTrend.test.mjs`.
  Expected: FAIL because `src/lib/fundDailyTrend.ts` does not exist yet.

- [ ] **Step 3: Implement the pure trend option helper**

  Create `buildFundDailyTrendOption` with the existing dashboard chart conventions: formatted date labels, axis tooltip, left axis for order counts, right axis for rates, blue/brand bar marks, and orange rate line. Keep the bar axis anchored at zero and do not add a total-order series.

- [ ] **Step 4: Run the focused test to verify it passes**

  Run `node --experimental-transform-types --test tests/fundDailyTrend.test.mjs`.
  Expected: PASS.

- [ ] **Step 5: Wire the helper into the result card**

  Add the two top-level result tabs inside the existing `ChartCard`. Keep the rule-status tabs and table under the alerts branch. Replace the standalone “大盘日趋势” card with the trend branch of the result card, using `dashboard.daily_trend` and the extracted helper. Remove the old total-order bar series.

- [ ] **Step 6: Run all frontend verification**

  Run `node --experimental-transform-types --test tests/*.test.mjs` and `npm run build`.
  Expected: all Node tests pass and the TypeScript/Vite build exits 0.

- [ ] **Step 7: Review the final diff**

  Confirm the diff only changes the approved tab/chart UI, the helper test, and no backend or API files.
