# 授信归因打标历史 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 为授信归因监控页增加“打标记录”Tab，保存规则进入/移出策略或持续观察的历史区间，并让措施日期使用操作时页面选中的 `pt`。

**Architecture:** 在现有 SQLite 状态库中增加状态历史表；当前状态表保存每条规则的最新状态和当前进入 `pt`，历史表保存每次 1/2 状态区间。后端状态更新接口接收 `action_pt` 并在同一事务内维护两张表，新增历史查询接口；前端在更新时传递 `dashboard.meta.partition`，并使用独立的历史 Tab 展示区间记录。

**Tech Stack:** Python 3.10、SQLite、FastAPI/Pydantic、React、TypeScript、Vite、pytest。

## Global Constraints

- 状态值仍为内部 `0/1/2`，页面标签只能显示“不需要处理”“已上策略”“持续观察”。
- `action_date` 不再使用服务器系统日期；新状态变更必须使用请求中的 `action_pt`，例如 `20260831`。
- “发现规则”仍显示当天 `pt` 的全部异常，不因当前状态为 1/2 而隐藏；只排除仅用于持续统计的 `is_tracked_only` 记录。
- 历史记录只保存状态 1 和 2 的连续区间；状态 0 不新增历史区间。
- 保留现有工作区改动，只提交本计划文件及本功能实际修改的文件；不重置或覆盖其他用户文件。
- 不增加第三方依赖；SQLite 数据库文件继续位于 `server/data/attribution_status.sqlite3`。

---

### Task 1: 为状态库增加可追溯的状态区间

**Files:**
- Modify: `server/attribution_status.py`
- Test: `server/test_attribution_status.py`

**Interfaces:**
- Produces `AttributionStatusStore.set_status(canonical_path, status, updated_by, action_pt, rule=None)`。
- Produces `AttributionStatusStore.get_history()`，返回按 `entered_at` 倒序排列的历史记录列表。
- 历史记录字段固定为 `id`、`canonical_path`、`status`、`rule`、`entered_at`、`entered_pt`、`entered_by`、`exited_at`、`exited_pt`、`exited_by`。

- [ ] **Step 1: 写状态区间的失败测试**

在 `server/test_attribution_status.py` 增加以下测试，先使用尚未实现的 `action_pt` 和 `get_history()`：

```python
def test_status_history_records_entry_exit_switch_and_reentry(tmp_path):
    store = AttributionStatusStore(tmp_path / "status.sqlite3")
    rule = {"canonical_path": "layer=a", "conditions": [{"field": "x"}]}

    store.set_status("layer=a", 1, "alice", action_pt="20260831", rule=rule)
    store.set_status("layer=a", 2, "bob", action_pt="20260901", rule=rule)
    store.set_status("layer=a", 0, "carol", action_pt="20260902", rule=rule)
    store.set_status("layer=a", 2, "dave", action_pt="20260903", rule=rule)

    history = store.get_history()
    assert [item["status"] for item in history] == [2, 2, 1]
    assert history[0]["entered_pt"] == "20260903"
    assert history[0]["exited_pt"] is None
    assert history[1]["entered_pt"] == "20260901"
    assert history[1]["exited_pt"] == "20260902"
    assert history[2]["entered_pt"] == "20260831"
    assert history[2]["exited_pt"] == "20260901"


def test_repeating_same_status_keeps_original_entry_pt(tmp_path):
    store = AttributionStatusStore(tmp_path / "status.sqlite3")
    store.set_status("layer=b", 1, "alice", action_pt="20260831")
    result = store.set_status("layer=b", 1, "bob", action_pt="20260901")

    assert result["action_date"] == "20260831"
    history = store.get_history()
    assert len(history) == 1
    assert history[0]["entered_pt"] == "20260831"
    assert history[0]["entered_by"] == "alice"


def test_action_pt_is_required_and_saved_as_current_action_date(tmp_path):
    store = AttributionStatusStore(tmp_path / "status.sqlite3")
    with pytest.raises(ValueError, match="action_pt"):
        store.set_status("layer=c", 1, "alice", action_pt=" ")

    store.set_status("layer=c", 1, "alice", action_pt="20260901")
    assert store.get_all()["layer=c"]["action_date"] == "20260901"
```

- [ ] **Step 2: 运行失败测试确认失败原因正确**

运行：

```powershell
pytest -q server/test_attribution_status.py -k "history or action_pt" --basetemp E:\agent\monitor\.pytest_tmp_plan
```

预期：测试因 `set_status` 不接受 `action_pt` 或 `get_history` 不存在而失败，而不是因为测试收集或临时目录错误。

- [ ] **Step 3: 实现历史表和状态迁移**

在 `_ensure_schema()` 中创建：

```sql
CREATE TABLE IF NOT EXISTS attribution_rule_status_history (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    canonical_path TEXT NOT NULL,
    status INTEGER NOT NULL CHECK (status IN (1, 2)),
    rule_json TEXT,
    entered_at TEXT NOT NULL,
    entered_pt TEXT NOT NULL,
    entered_by TEXT NOT NULL,
    exited_at TEXT,
    exited_pt TEXT,
    exited_by TEXT
)
```

修改 `set_status`：

- 校验 `action_pt.strip()` 非空并保存规范化字符串。
- 在一个连接和事务中读取当前状态。
- 当前状态为 1/2 且新状态不同于当前状态时，关闭该规则最新的 `exited_at IS NULL` 历史行。
- 新状态为 1/2 且与当前状态不同于当前状态时，插入新的历史行。
- 新旧状态相同为 1/2 时不插入新行，并保留原历史行的 `entered_pt` 作为 `action_date`。
- 新状态为 0 时将当前状态的 `action_date` 设为 `NULL`。
- 对旧数据库只新增表和缺失列，不删除既有状态数据。

`get_history()` 查询 `ORDER BY entered_at DESC, id DESC`，解析 `rule_json`，并将 `is_active` 设置为 `exited_at IS NULL`。

- [ ] **Step 4: 运行状态库测试确认通过**

运行：

```powershell
pytest -q server/test_attribution_status.py -k "history or action_pt" --basetemp E:\agent\monitor\.pytest_tmp_plan
```

预期：新增测试全部通过。

- [ ] **Step 5: 运行既有状态测试确认无回归**

运行：

```powershell
pytest -q server/test_attribution_status.py --basetemp E:\agent\monitor\.pytest_tmp_plan_all
```

预期：该文件测试全部通过。

### Task 2: 后端接口接入 pt 和历史查询

**Files:**
- Modify: `server/app.py`
- Modify: `src/lib/creditAttributionApi.ts`
- Test: `server/test_attribution_status.py`

**Interfaces:**
- `RuleStatusUpdate` 新增 `action_pt: str = Field(min_length=1, max_length=64)`。
- `PUT /api/credit-attribution/rule-status` 请求 JSON 为 `{canonical_path, status, action_pt, rule}`。
- 新增 `GET /api/credit-attribution/rule-status-history`，返回 `{records: [...]}`。

- [ ] **Step 1: 写接口模型失败测试**

增加对 Pydantic 模型的直接测试：

```python
def test_rule_status_update_requires_action_pt():
    from app import RuleStatusUpdate

    with pytest.raises(Exception):
        RuleStatusUpdate(canonical_path="layer=a", status=1)
    with pytest.raises(Exception):
        RuleStatusUpdate(canonical_path="layer=a", status=1, action_pt=" ")
```

- [ ] **Step 2: 运行测试确认接口字段尚未存在**

运行：

```powershell
pytest -q server/test_attribution_status.py -k "requires_action_pt" --basetemp E:\agent\monitor\.pytest_tmp_plan_api
```

预期：测试失败，因为当前模型没有必填的 `action_pt`。

- [ ] **Step 3: 实现后端请求模型和两个接口**

在 `server/app.py` 中：

- 给 `RuleStatusUpdate` 增加 `action_pt` 字段。
- 调用 `set_status(..., action_pt=update.action_pt, rule=update.rule)`。
- 返回 `action_date` 为当前状态历史行的 `entered_pt`，同时返回本次更新后的历史记录。
- 新增历史 GET 路由，使用同一 `attribution` 权限，返回 `json_safe({"records": service._status_store.get_history()})`。
- 保留现有 dashboard 的状态叠加逻辑，只把最新状态的 `action_date` 改为历史区间的进入 `pt`。

在 `src/lib/creditAttributionApi.ts` 中：

```typescript
export interface AttributionRuleStatusUpdateResponse {
  canonical_path: string;
  status: RuleStatus;
  updated_at: string;
  updated_by: string;
  action_date: string | null;
  history: AttributionRuleStatusHistory | null;
}

export function updateAttributionRuleStatus(
  canonicalPath: string,
  status: RuleStatus,
  actionPt: string,
  rule?: AttributionRecord,
): Promise<AttributionRuleStatusUpdateResponse>;

export interface AttributionRuleStatusHistory {
  id: number;
  canonical_path: string;
  status: 1 | 2;
  rule: AttributionRecord | null;
  entered_at: string;
  entered_pt: string;
  entered_by: string;
  exited_at: string | null;
  exited_pt: string | null;
  exited_by: string | null;
  is_active: boolean;
}

export function fetchAttributionRuleStatusHistory() {
  return getJson<{ records: AttributionRuleStatusHistory[] }>(
    '/api/credit-attribution/rule-status-history',
  );
}
```

- [ ] **Step 4: 运行后端测试和 Python 编译检查**

运行：

```powershell
pytest -q server/test_attribution_status.py --basetemp E:\agent\monitor\.pytest_tmp_plan_api_all
python -m py_compile server/attribution_status.py server/app.py
```

预期：测试全部通过，编译命令无输出且退出码为 0。

### Task 3: 页面增加“打标记录”Tab并按当前 pt 更新

**Files:**
- Modify: `src/pages/CreditAttribution.tsx`
- Modify: `src/lib/creditAttributionApi.ts`

**Interfaces:**
- 页面 Tab 状态类型扩展为 `RuleStatus | 'history'`。
- `updateRuleStatus` 从 `dashboard.meta.partition` 读取 `actionPt` 并传入 API。
- 历史 Tab 使用 `fetchAttributionRuleStatusHistory()` 的结果，不参与当天异常筛选。

- [ ] **Step 1: 先增加可验证的前端行为断言**

如果项目已有前端测试运行器，增加测试断言：

```typescript
expect(screen.getByRole('tab', { name: /打标记录/ })).toBeInTheDocument();
expect(screen.getByText('进入 pt')).toBeInTheDocument();
expect(screen.getByText('移出 pt')).toBeInTheDocument();
```

如果当前项目没有前端测试运行器，则使用下面的构建和浏览器验证作为可重复验收，且先执行 `npm run build` 记录当前基线结果。

- [ ] **Step 2: 实现历史 Tab 状态和数据加载**

在页面中新增：

```typescript
type RuleStatusTab = RuleStatus | 'history';
const [ruleStatusTab, setRuleStatusTab] = useState<RuleStatusTab>(0);
const [statusHistory, setStatusHistory] = useState<AttributionRuleStatusHistory[]>([]);
const [statusHistoryError, setStatusHistoryError] = useState<string | null>(null);
```

dashboard 加载成功后请求历史；历史请求失败只设置 `statusHistoryError`，不清空 dashboard。

在现有四个状态 Tab 中加入 `打标记录`。前三个 Tab 沿用现有计数和筛选；历史 Tab 不使用 `filteredAlerts`，改用历史表渲染。

- [ ] **Step 3: 传递当前 pt 并同步更新历史**

把现有调用：

```typescript
updateAttributionRuleStatus(canonicalPath, status, record)
```

改为：

```typescript
updateAttributionRuleStatus(
  canonicalPath,
  status,
  dashboard?.meta.partition ?? selectedPartition,
  record,
)
```

更新成功后使用接口返回的最新状态、`action_date` 和 `history` 更新当前 dashboard，并将返回的历史行合并到 `statusHistory`；必要时重新获取一次历史，保证关闭旧区间和新增新区间同时反映在页面上。

- [ ] **Step 4: 调整措施日期和历史表格列**

前三个状态 Tab 的列规则：

- 发现规则：不包含 `措施日期`。
- 已上策略、持续观察监控：包含 `措施日期`，显示当前历史区间的 `entered_pt`。

“打标记录”使用独立列：

```typescript
const statusHistoryColumns: FeishuColumn<AttributionRuleStatusHistory>[] = [
  { key: 'status', title: '标记状态', render: (row) => row.status === 1 ? '已上策略' : '持续观察' },
  { key: 'canonical_path', title: '异常归因路径' },
  { key: 'entered_pt', title: '进入 pt' },
  { key: 'entered_at', title: '进入时间' },
  { key: 'entered_by', title: '进入操作人' },
  { key: 'exited_pt', title: '移出 pt', render: (row) => row.exited_pt ?? '—' },
  { key: 'exited_at', title: '移出时间', render: (row) => row.exited_at ?? '—' },
  { key: 'exited_by', title: '移出操作人', render: (row) => row.exited_by ?? '—' },
  { key: 'is_active', title: '当前状态', render: (row) => row.is_active ? '进行中' : '已结束' },
];
```

- [ ] **Step 5: 运行前端构建**

运行：

```powershell
npm run build
```

预期：TypeScript 检查和 Vite 构建成功；既有 browserslist、Tailwind class 和 chunk size warning 不作为本功能失败。

### Task 4: 集成验证和交付检查

**Files:**
- Verify: `server/attribution_status.py`
- Verify: `server/app.py`
- Verify: `server/pipeline/cli.py`
- Verify: `src/lib/creditAttributionApi.ts`
- Verify: `src/pages/CreditAttribution.tsx`

- [ ] **Step 1: 运行相关 Python 测试**

运行：

```powershell
pytest -q server/test_attribution_status.py server/test_dashboard_snapshot_fallback.py server/test_path_trend_duckdb.py server/test_person_approval_rate.py server/test_schedule_config.py --basetemp E:\agent\monitor\.pytest_tmp_final
```

预期：9 个相关测试全部通过。

- [ ] **Step 2: 检查 Python 编译和差异格式**

运行：

```powershell
python -m py_compile server/attribution_status.py server/app.py server/warehouse.py server/pipeline/cli.py
git diff --check
```

预期：编译退出码为 0；`git diff --check` 没有 whitespace error。

- [ ] **Step 3: 浏览器验证四个 Tab**

在 `http://localhost:3000/?page=attribution` 验证：

1. 发现规则表头没有“措施日期”，且当天状态为 1/2 的异常仍在表中。
2. 已上策略表头显示“措施日期”，值为当前规则进入状态时的 `pt`。
3. 持续观察监控表头显示“措施日期”，值为当前规则进入状态时的 `pt`。
4. 打标记录显示进入/移出时间和对应 `pt`；新进入记录为“进行中”，移出后显示结束信息。
5. 对规则执行 1→2、2→0、0→1，历史 Tab 顺序和区间边界符合状态变更规则。

- [ ] **Step 4: 运行最终前端构建并汇总**

运行：

```powershell
npm run build
git status --short
```

预期：构建成功；汇报中明确列出本功能文件和验证结果，不把现有无关工作区改动当成本次改动。
