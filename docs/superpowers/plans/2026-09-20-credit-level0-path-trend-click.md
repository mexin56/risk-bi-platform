# 授信归因 Level0 路径趋势点击修复 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** 让授信归因表格中的 Level0 路径可点击，并通过已有选择逻辑加载被点击路径自己的近 60 天趋势。

**Architecture:** 只修改 `CreditAttribution.tsx` 的路径列渲染，把 Level0 与其他等级统一渲染为调用 `selectAlertPath(record)` 的按钮。通过一个无额外依赖的 Node 回归测试锁定“Level0 不得再渲染为普通文本”的行为，再用现有 TypeScript 构建和运行中的接口请求验证。

**Tech Stack:** React 19、TypeScript、Vite、Node `node:test`。

## Global Constraints

- 只修改授信归因页面的 Level0 路径点击行为。
- 不修改后端接口、趋势计算、状态统计、资金归集页面或表格行点击行为。
- 复用现有 `selectAlertPath(record)`，请求仍使用当前 `pt` 和被点击记录的 `id`。

---

### Task 1: Add a failing regression test for Level0 path rendering

**Files:**
- Create: `tests/credit-attribution-level0-path.test.mjs`
- Read: `src/pages/CreditAttribution.tsx`

**Interfaces:**
- Consumes: the source text of `src/pages/CreditAttribution.tsx`.
- Produces: a native Node test that fails while the Level0 non-clickable render branch exists.

- [ ] **Step 1: Write the failing test**

Create a Node test that loads the page source and asserts the path column uses a clickable button for all records, including Level0 records:

```js
import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';
import test from 'node:test';

test('credit attribution path column keeps Level0 records clickable', async () => {
  const source = await readFile(new URL('../src/pages/CreditAttribution.tsx', import.meta.url), 'utf8');
  const pathColumn = source.slice(source.indexOf("key: 'path'"), source.indexOf("key: 'layer'"));

  assert.doesNotMatch(pathColumn, /record\.level === 0 && !record\.is_tracked_only/);
  assert.match(pathColumn, /<button[\s\S]*onClick=\{\(\) => selectAlertPath\(record\)\}/);
  assert.doesNotMatch(pathColumn, /<span[\s\S]*>\{record\.path\}<\/span>/);
});
```

- [ ] **Step 2: Run the test and verify it fails for the expected reason**

Run:

```powershell
node --test tests/credit-attribution-level0-path.test.mjs
```

Expected result: one failing test because the current path column contains the Level0 conditional branch and renders a non-clickable `<span>`.

### Task 2: Make Level0 paths use the existing selection handler

**Files:**
- Modify: `src/pages/CreditAttribution.tsx` in the `key: 'path'` column definition.

**Interfaces:**
- Consumes: `AttributionRecord` and the existing `selectAlertPath(record)` callback.
- Produces: one path-cell render branch that always uses a clickable button and passes the clicked record unchanged.

- [ ] **Step 1: Replace the conditional path renderer with the shared button renderer**

Keep the existing `PathHoverTip`, button classes, title, and `selectAlertPath(record)` callback; remove only the Level0-only `<span>` branch so the renderer has this shape:

```tsx
{
  key: 'path', title: '异常归因路径', width: 360,
  render: (record) => (
    <PathHoverTip path={record.path}>
      <button
        onClick={() => selectAlertPath(record)}
        className="max-w-[340px] cursor-pointer truncate text-left font-medium text-slate-700 underline-offset-2 hover:text-blue-600 hover:underline"
        title="悬停查看完整值; 点击查看该路径近60天趋势"
      >
        {record.path}
      </button>
    </PathHoverTip>
  ),
},
```

- [ ] **Step 2: Run the regression test and verify it passes**

Run:

```powershell
node --test tests/credit-attribution-level0-path.test.mjs
```

Expected result: one passing test.

### Task 3: Validate compilation and the original user flow

**Files:**
- Test: `tests/credit-attribution-level0-path.test.mjs`
- Validate: `src/pages/CreditAttribution.tsx`

**Interfaces:**
- Consumes: the updated path-column renderer.
- Produces: a compiled frontend and evidence that the exact Level0 record uses its own trend request.

- [ ] **Step 1: Run the full frontend build**

Run:

```powershell
npm run build
```

Expected result: TypeScript and Vite both exit with code 0.

- [ ] **Step 2: Run lint and the regression test together**

Run:

```powershell
npm run lint
node --test tests/credit-attribution-level0-path.test.mjs
```

Expected result: ESLint exits 0 and the regression test reports one pass.

- [ ] **Step 3: Verify the API data for the exact record remains available**

Run:

```powershell
$result = Invoke-WebRequest -UseBasicParsing 'http://127.0.0.1:8010/api/credit-attribution/path-trend?record_id=017f87da6fb3&pt=20260919'
$body = $result.Content | ConvertFrom-Json
if ($result.StatusCode -ne 200 -or $body.record_id -ne '017f87da6fb3' -or $body.daily.Count -ne 60) { throw 'exact Level0 trend verification failed' }
"record_id=$($body.record_id); daily_count=$($body.daily.Count)"
```

Expected result: `record_id=017f87da6fb3; daily_count=60`.

- [ ] **Step 4: Review the diff and commit only the scoped changes**

Run:

```powershell
git diff --check
git diff -- src/pages/CreditAttribution.tsx tests/credit-attribution-level0-path.test.mjs
git add -- src/pages/CreditAttribution.tsx tests/credit-attribution-level0-path.test.mjs
git commit -m "fix: make credit level0 paths clickable"
```

Expected result: the commit contains only the Level0 path renderer and its regression test.
