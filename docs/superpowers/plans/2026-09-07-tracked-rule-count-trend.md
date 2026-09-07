# 持续观察规则计数与近 60 天趋势 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ensure every currently ongoing rule is counted separately and can open its complete precomputed 60-day path trend even when the current partition has no alert.

**Architecture:** Keep current-alert severity semantics unchanged. The pipeline exposes a `tracked_rule_count` summary field for status-2 rules, while tracked-only records remain `level=0` and `is_tracked_only=true`. The frontend uses that count for the ongoing tab and makes only tracked-only Level0 paths clickable, reusing the existing path-trend request and chart.

**Tech Stack:** Python, pytest, DuckDB/Parquet serving snapshots, React, TypeScript, Vite, existing Dagster/MaxCompute pipeline.

## Global Constraints

- A status-2 rule is counted as ongoing monitoring, not as a new L1/L2/L3 current alert.
- Tracked-only rows retain `level=0`, `Level0 无预警`, and `is_tracked_only=true`.
- The path trend remains the existing precomputed 60-day series; do not change trend SQL or thresholds.
- Do not change status lifecycle, alert thresholds, notification logic, or unrelated dirty working-tree changes.

---

### Task 1: Add a backend ongoing-rule summary contract

**Files:**
- Modify: `server/pipeline/cli.py:170-213`
- Test: `server/test_attribution_status.py`

**Interfaces:**
- Consumes: `service._status_store.get_active_tagged_rules()` entries with `status`, `entered_pt`, and `rule`.
- Produces: `result["summary"]["tracked_rule_count"]`, an integer counting active status-2 rules for the published dashboard payload.

- [ ] **Step 1: Write the failing test**

Add this assertion to the existing `test_compute_and_publish_rebuilds_hit_and_non_hit_tracked_rules_from_entry_pt` after the existing `captured["result"]` assertions:

```python
    assert captured["result"]["summary"]["tracked_rule_count"] == 1
```

- [ ] **Step 2: Run the focused test to verify it fails**

Run from the repository root:

```powershell
python -m pytest server/test_attribution_status.py::test_compute_and_publish_rebuilds_hit_and_non_hit_tracked_rules_from_entry_pt -q
```

Expected: FAIL with `KeyError: 'tracked_rule_count'` because the current pipeline appends the tracked row but does not add the summary field.

- [ ] **Step 3: Implement the minimal backend change**

In `compute_and_publish`, after the tracked-rule merge block and before `path_rows_started`, add:

```python
    result.setdefault("summary", {})["tracked_rule_count"] = sum(
        1 for entry in tracked_rules if int(entry.get("status", 0)) == 2
    )
```

Leave `level1_count`, `level2_count`, `level3_count`, and their current-alert meanings unchanged.

- [ ] **Step 4: Run the focused test to verify it passes**

```powershell
python -m pytest server/test_attribution_status.py::test_compute_and_publish_rebuilds_hit_and_non_hit_tracked_rules_from_entry_pt -q
```

Expected: PASS for both parametrized cases.

- [ ] **Step 5: Commit the backend contract**

```powershell
git add server/pipeline/cli.py server/test_attribution_status.py
git commit -m "fix: count ongoing attribution rules"
```

### Task 2: Make tracked-only Level0 paths open the trend panel

**Files:**
- Modify: `src/pages/CreditAttribution.tsx:638-650` and `src/pages/CreditAttribution.tsx:895-914`
- Modify: `src/lib/creditAttributionApi.ts:168-180`

**Interfaces:**
- Consumes: `dashboard.summary.tracked_rule_count` and `AttributionRecord.is_tracked_only`.
- Produces: an ongoing tab count backed by the API summary and a clickable tracked-only path that calls the existing `selectAlertPath` flow.

- [ ] **Step 1: Add the TypeScript contract**

Add this property to `AttributionDashboard.summary` next to `merged_alert_count`:

```ts
    tracked_rule_count: number;
```

- [ ] **Step 2: Implement the ongoing-tab count**

Change the `ruleStatusCounts` memo so status 2 uses the backend count with a compatibility fallback for old snapshots:

```tsx
  const ruleStatusCounts = useMemo(() => {
    return {
      0: allRows.filter((record) => !record.is_tracked_only).length,
      1: allRows.filter((record) => (record.status ?? 0) === 1).length,
      2: dashboard?.summary.tracked_rule_count
        ?? allRows.filter((record) => (record.status ?? 0) === 2).length,
    } satisfies Record<RuleStatus, number>;
  }, [allRows, dashboard?.summary.tracked_rule_count]);
```

- [ ] **Step 3: Implement the tracked-only clickable path**

In the `alertColumns` path renderer, replace the Level0-only branch with a tracked-only exception:

```tsx
      record.level === 0 && !record.is_tracked_only ? (
        <PathHoverTip path={record.path}>
          <span
            className="max-w-[340px] cursor-pointer truncate text-slate-500 hover:text-slate-700"
            title="悬停查看完整值"
          >{record.path}</span>
        </PathHoverTip>
      ) : (
        <PathHoverTip path={record.path}>
          <button
            onClick={() => selectAlertPath(record)}
            className="max-w-[340px] cursor-pointer truncate text-left font-medium text-slate-700 underline-offset-2 hover:text-blue-600 hover:underline"
            title="点击查看该路径近60天趋势"
          >
            {record.path}
          </button>
        </PathHoverTip>
      )
```

Keep regular Level0 candidates non-clickable; only `is_tracked_only` rows gain the trend action.

- [ ] **Step 4: Build the frontend**

```powershell
npm run build
```

Expected: TypeScript compilation and Vite build exit with code 0.

- [ ] **Step 5: Commit the frontend change**

```powershell
git add src/pages/CreditAttribution.tsx src/lib/creditAttributionApi.ts
git commit -m "fix: open trends for ongoing rules"
```

### Task 3: Republish and verify the affected partition

**Files:**
- No source changes expected.
- Verify: `server/data/attribution.duckdb`, `server/data/serving/`, running API on `127.0.0.1:8010`, running Vite app on `10.130.164.198:3000`.

**Interfaces:**
- Consumes: the Task 1/2 changes and the existing status-2 rule `4916e4008700` entered at `20260901`.
- Produces: a dashboard payload whose ongoing count includes the rule and whose existing path-trend endpoint returns 60 points.

- [ ] **Step 1: Run the backend regression suite**

```powershell
python -m pytest server/test_attribution_status.py server/test_path_trend_duckdb.py -q
```

Expected: all tests pass with zero failures.

- [ ] **Step 2: Recompute and publish the latest partition**

From `server/`, run:

```powershell
python -m pipeline.cli run --pt 20260906 --source manual_tracked_rule_fix
```

Expected: one `OK` result and a new serving snapshot for `pt=20260906`.

- [ ] **Step 3: Verify the API payload**

Use the existing authenticated API check and assert:

```python
assert payload["summary"]["tracked_rule_count"] >= 1
tracked = next(item for item in payload["merged_alerts"] if item["id"] == "4916e4008700")
assert tracked["status"] == 2
assert tracked["is_tracked_only"] is True
```

- [ ] **Step 4: Verify the trend endpoint**

Request `/api/credit-attribution/path-trend?record_id=4916e4008700&pt=20260906` with a valid session and assert:

```python
assert response.status_code == 200
assert response.json()["summary"]["period_days"] == 60
```

- [ ] **Step 5: Verify the running frontend**

```powershell
$response = Invoke-WebRequest -UseBasicParsing http://10.130.164.198:3000/ -TimeoutSec 10
if ([int]$response.StatusCode -ne 200) { throw "BI frontend unavailable" }
```

Expected: HTTP 200. In the “持续观察监控” tab, the affected row remains `Level0 无预警` but its path is clickable and opens the 60-day chart.

- [ ] **Step 6: Record final diff and status**

```powershell
git status --short
git log -2 --oneline
```

Confirm only the intended source/test files and the already-approved plan/spec changes are present; do not stage unrelated existing modifications.
