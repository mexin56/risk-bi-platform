# 授信归因钉钉 AI Agent Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在指定钉钉群中提供一个只读的“授信归因助手”，能够回答最新/指定 pt 的预警、规则、趋势、通过率、打标跟踪和风险总结，并保留可审计的调用记录。

**Architecture:** 将钉钉入站事件适配、自然语言意图解析、固定白名单查询工具、回答生成和审计存储拆成独立模块。查询只复用项目现有的 `AttributionService`、DuckDB/serving 结果，不允许模型接触数据库凭证、拼接 SQL 或执行写操作；当前日报 Webhook 继续只负责出站发送。

**Tech Stack:** Python 3.10、FastAPI、DuckDB/现有 serving 层、SQLite、requests、pytest、可选 OpenAI-compatible HTTP API。

## Global Constraints

- 默认配置 `DINGTALK_AGENT_ENABLED=false`，没有凭证时服务必须正常启动。
- 入站使用可接收群消息的企业机器人事件/Stream 或回调适配器；现有自定义 Webhook 只用于日报出站，不能当作问答入站接口。
- Agent 只能调用固定只读工具：`latest_partition`、`dashboard_summary`、`find_rules`、`rule_detail`、`path_trend`、`tracked_rule_followup`、`compare_partitions`。
- 群 ID 和用户 ID 都必须通过白名单校验；非白名单请求不得返回业务数据。
- 仅处理 `@授信归因助手` 的消息；普通群消息不触发回答；同一消息 ID 不能重复回复。
- 所有回答标注 pt 与时间窗口，区分数据事实、数据推断和无法确认的部分，不输出手机号、身份证号、设备号等个人明细。
- 趋势优先读取已预计算 DuckDB/serving 结果；没有目标 pt 或趋势结果时明确提示实际可用 pt 和刷新动作，不实时扫描 MaxCompute。
- 模型不可直接访问数据库或凭证；模型不可执行用户提供的任意 SQL，也不可修改规则状态、策略或记录。
- 所有敏感凭证只写入 `server/.env.local`，不写入仓库、不写入审计库、不输出到日志；用户已在聊天中公开过的旧 Webhook/Secret 应先轮换后再测试。

---

## 文件结构与职责

- Create: `server/attribution_agent.py` — Agent 配置、结构化响应、固定提示词、模型客户端和确定性降级回答。
- Create: `server/attribution_query_tools.py` — 将自然语言所需查询映射到现有 `AttributionService` 的只读工具。
- Create: `server/dingtalk_agent.py` — 入站事件规范化、签名/白名单/去重、Agent 调用、钉钉回复和 SQLite 审计。
- Create: `server/test_attribution_agent.py` — 意图解析、模型失败降级、回答安全约束测试。
- Create: `server/test_attribution_query_tools.py` — 工具白名单、pt/趋势/通过率/打标查询测试。
- Create: `server/test_dingtalk_agent.py` — 入站适配、权限、去重、审计和回复测试。
- Create: `server/scripts/simulate_dingtalk_agent.py` — 不连接钉钉的本地事件模拟器。
- Modify: `server/app.py:818-1000` — 注册 Agent 健康检查和规范化事件入口；保持现有 API 行为不变。
- Modify: `server/.env.example` — 增加 Agent 配置键及安全说明。
- Modify: `server/.env.local` — 仅由部署者填写测试凭证、群白名单和模型配置，不提交。
- Modify: `README.md` — 增加本地模拟、单群接入、生产启用和定时日报边界说明。

## Task 1: Define agent contracts and configuration

**Files:**
- Create: `server/attribution_agent.py`
- Test: `server/test_attribution_agent.py`

**Interfaces:**
- `AgentConfig.from_env() -> AgentConfig`，字段包括 `enabled: bool`、`app_key: str`、`app_secret: str`、`allowed_group_ids: frozenset[str]`、`allowed_user_ids: frozenset[str]`、`base_url: str`、`api_key: str`、`model: str`、`timeout_seconds: int`。
- `AgentAnswer` 为可序列化数据类，字段为 `conclusion`、`evidence`、`facts`、`inference`、`next_steps`、`links`、`used_tools`、`pt`、`window`。
- `AttributionAgent.answer(question: str, context: dict[str, str]) -> AgentAnswer`。

- [ ] **Step 1: Write the failing tests**

```python
def test_config_is_disabled_without_credentials(monkeypatch):
    monkeypatch.delenv("DINGTALK_AGENT_ENABLED", raising=False)
    config = AgentConfig.from_env()
    assert config.enabled is False

def test_answer_serializes_required_sections():
    answer = AgentAnswer(
        conclusion="当前风险以高等级规则为主。",
        evidence=["pt=20260902, Level3=2"],
        facts=["Level3=2"], inference=["需要结合趋势复核"],
        next_steps=["继续观察下一个 pt"], links=[],
        used_tools=["dashboard_summary"], pt="20260902", window="当天",
    )
    payload = answer.to_dict()
    assert {"conclusion", "evidence", "facts", "inference", "next_steps", "pt", "window"} <= payload.keys()
```

- [ ] **Step 2: Run the focused test and verify it fails**

Run: `python -m pytest server/test_attribution_agent.py -q`

Expected: FAIL because `AgentConfig` and `AgentAnswer` do not exist.

- [ ] **Step 3: Write the minimal contracts**

```python
@dataclass(frozen=True)
class AgentConfig:
    enabled: bool = False
    app_key: str = ""
    app_secret: str = ""
    allowed_group_ids: frozenset[str] = frozenset()
    allowed_user_ids: frozenset[str] = frozenset()
    base_url: str = ""
    api_key: str = ""
    model: str = ""
    timeout_seconds: int = 30

    @classmethod
    def from_env(cls):
        split = lambda name: frozenset(x.strip() for x in os.getenv(name, "").split(",") if x.strip())
        return cls(
            enabled=os.getenv("DINGTALK_AGENT_ENABLED", "false").lower() == "true",
            app_key=os.getenv("DINGTALK_AGENT_APP_KEY", ""),
            app_secret=os.getenv("DINGTALK_AGENT_APP_SECRET", ""),
            allowed_group_ids=split("DINGTALK_AGENT_ALLOWED_GROUP_IDS"),
            allowed_user_ids=split("DINGTALK_AGENT_ALLOWED_USER_IDS"),
            base_url=os.getenv("AI_AGENT_BASE_URL", ""),
            api_key=os.getenv("AI_AGENT_API_KEY", ""),
            model=os.getenv("AI_AGENT_MODEL", ""),
            timeout_seconds=max(1, int(os.getenv("AI_AGENT_TIMEOUT_SECONDS", "30"))),
        )
```

`AgentAnswer.to_dict()` 必须只返回上述字段及 `used_tools`，并将模型原始响应排除在外。

- [ ] **Step 4: Run the focused test and verify it passes**

Run: `python -m pytest server/test_attribution_agent.py -q`

Expected: `2 passed`。

- [ ] **Step 5: Commit**

```bash
git add server/attribution_agent.py server/test_attribution_agent.py
git commit -m "feat: define attribution agent contracts"
```

## Task 2: Add fixed read-only attribution query tools

**Files:**
- Create: `server/attribution_query_tools.py`
- Test: `server/test_attribution_query_tools.py`

**Interfaces:**
- `AttributionQueryTools(service: AttributionService, page_base_url: str = "")`。
- `latest_partition() -> dict`。
- `dashboard_summary(pt: str | None = None) -> dict`。
- `find_rules(pt: str | None = None, keyword: str = "", level: str = "", status: str = "") -> dict`。
- `rule_detail(pt: str | None, record_id_or_path: str) -> dict`。
- `path_trend(pt: str | None, record_id: str, days: int = 60) -> dict`。
- `tracked_rule_followup(path: str, start_pt: str, end_pt: str | None = None) -> dict`。
- `compare_partitions(pt_a: str, pt_b: str) -> dict`。
- 每个返回值包含 `source="duckdb/serving"`、实际 `pt` 或 `pt_range`、`data`、`warnings`；输入非法或超出 `days` 范围时返回结构化错误，不执行 SQL。

- [ ] **Step 1: Write failing tests with a fake service**

```python
class FakeService:
    def latest_partition(self): return "20260902"
    def dashboard(self, partition=None): return {"partition": partition, "level_counts": {"Level1": 4}}
    def path_trend(self, record_id, partition=None, offset=0): return {"record_id": record_id, "days": ["2026-08-04", "2026-09-02"]}

def test_tools_expose_only_named_read_methods():
    tools = AttributionQueryTools(FakeService())
    assert sorted(tools.available_tools()) == [
        "compare_partitions", "dashboard_summary", "find_rules", "latest_partition",
        "path_trend", "rule_detail", "tracked_rule_followup",
    ]

def test_path_trend_caps_window_at_sixty_days():
    result = AttributionQueryTools(FakeService()).path_trend("20260902", "rule-1", days=90)
    assert result["warnings"] == ["days 已限制为 60"]
```

- [ ] **Step 2: Run the focused test and verify it fails**

Run: `python -m pytest server/test_attribution_query_tools.py -q`

Expected: FAIL because the tool class is not present.

- [ ] **Step 3: Implement adapters using existing service methods**

调用 `service.latest_partition()`、`service.dashboard_summary(...)` 或项目中现有等价只读方法；路径查询调用 `service.path_trend(...)`。工具层不得导入 MaxCompute 客户端、不得接受 SQL 字符串、不得调用状态更新方法。对 `cid_cnt` 与 `approval_cid_cnt` 计算 `sum(approval_cid_cnt) / sum(cid_cnt)`，输出名称固定为“通过率（人数）”，件数指标固定为“通过率（件数）”。

- [ ] **Step 4: Run query-tool tests and existing attribution tests**

Run: `python -m pytest server/test_attribution_query_tools.py server/test_path_trend_duckdb.py server/test_person_approval_rate.py -q`

Expected: all focused tests pass; no MaxCompute network call appears in output.

- [ ] **Step 5: Commit**

```bash
git add server/attribution_query_tools.py server/test_attribution_query_tools.py
git commit -m "feat: add read-only attribution query tools"
```

## Task 3: Add intent parsing, model client, and deterministic fallback

**Files:**
- Modify: `server/attribution_agent.py`
- Test: `server/test_attribution_agent.py`

**Interfaces:**
- `IntentParser.parse(question: str) -> dict`，返回 `intent`、`pt`、`level`、`keyword`、`record_id`、`days`、`pt_a`、`pt_b`。
- `OpenAICompatibleClient.complete(messages: list[dict[str, str]]) -> str`。
- `AttributionAgent(query_tools, config, client=None).answer(...)`。

- [ ] **Step 1: Write failing tests for supported intents**

```python
def test_parser_extracts_latest_level_question():
    intent = IntentParser().parse("看最新pt各等级规则有多少")
    assert intent["intent"] == "dashboard_summary"
    assert intent["pt"] is None

def test_parser_extracts_trend_days_and_rule():
    intent = IntentParser().parse("20260902 规则 abc 看近60天趋势")
    assert intent == {"intent": "path_trend", "pt": "20260902", "record_id": "abc", "days": 60}

def test_model_failure_returns_data_answer_without_inventing_conclusion():
    class BrokenClient:
        def complete(self, messages): raise TimeoutError("timeout")
    agent = AttributionAgent(FakeTools(), AgentConfig(), client=BrokenClient())
    answer = agent.answer("看最新等级", {"group_id": "g", "user_id": "u"})
    assert "AI 总结暂不可用" in answer.conclusion
    assert answer.evidence
```

- [ ] **Step 2: Run tests and verify the new cases fail**

Run: `python -m pytest server/test_attribution_agent.py -q`

Expected: FAIL on missing parser/client/orchestration behavior.

- [ ] **Step 3: Implement deterministic parsing and fixed tool orchestration**

解析仅支持七类意图：最新分区、概览、规则搜索、规则详情、路径趋势、打标跟踪、pt 对比。没有明确规则 ID 时先调用 `find_rules`；没有明确 pt 时调用 `latest_partition`。`days` 只允许 7、15、30、60，其他值归一化到 60 并加入 warning。工具结果先进入结构化 `AgentAnswer`，再交给模型生成自然语言；模型提示词明确要求输出“结论/数据证据/事实/推断/下一步/链接”，且不得生成工具外数字。

- [ ] **Step 4: Implement model timeout and fallback**

使用已有 `requests` 发送 OpenAI-compatible JSON，超时使用 `AgentConfig.timeout_seconds`；缺少 `base_url`、`api_key` 或 `model` 时直接走确定性回答。任何 HTTP、JSON 或模型内容错误都保留工具数据，并在 `conclusion` 中说明“AI 总结暂不可用”，不阻断业务结果。

- [ ] **Step 5: Run agent tests**

Run: `python -m pytest server/test_attribution_agent.py -q`

Expected: all parser, tool-orchestration, timeout and safety tests pass.

- [ ] **Step 6: Commit**

```bash
git add server/attribution_agent.py server/test_attribution_agent.py
git commit -m "feat: add attribution agent orchestration"
```

## Task 4: Add DingTalk adapter, allowlist, dedupe, and audit store

**Files:**
- Create: `server/dingtalk_agent.py`
- Test: `server/test_dingtalk_agent.py`

**Interfaces:**
- `DingTalkEvent.from_payload(payload: dict) -> DingTalkEvent | None`，字段为 `message_id`、`group_id`、`user_id`、`text`、`mentioned_agent`、`reply_target`。
- `DingTalkAdapter(config, agent, sender, audit_store).handle(payload) -> dict`。
- `DingTalkSender.send(reply_target: dict, markdown: str) -> dict`。
- `AgentAuditStore(path).seen(message_id) -> bool`、`record_start(...)`、`record_finish(...)`。

- [ ] **Step 1: Write failing adapter tests**

```python
def test_non_mention_is_ignored():
    result = adapter.handle({"messageId": "m1", "conversationId": "g1", "senderId": "u1", "text": "普通消息"})
    assert result["status"] == "ignored"
    assert sender.messages == []

def test_unauthorized_group_returns_no_business_data():
    result = adapter.handle({"messageId": "m2", "conversationId": "blocked", "senderId": "u1", "text": "@助手 最新风险"})
    assert result["status"] == "forbidden"
    assert "Level" not in sender.messages[-1]

def test_duplicate_message_is_not_replied_twice():
    payload = {"messageId": "m3", "conversationId": "g1", "senderId": "u1", "text": "@助手 最新pt"}
    assert adapter.handle(payload)["status"] == "replied"
    assert adapter.handle(payload)["status"] == "duplicate"
    assert len(sender.messages) == 1
```

- [ ] **Step 2: Run tests and verify they fail**

Run: `python -m pytest server/test_dingtalk_agent.py -q`

Expected: FAIL because event, adapter, sender and audit classes are absent.

- [ ] **Step 3: Implement event normalization and security checks**

同时兼容钉钉事件中常见的 `messageId`/`msgId`、`conversationId`/`openConversationId`、`senderId`/`senderStaffId` 字段；文本去掉机器人 mention 后再交给 Agent。先检查 `enabled`、group allowlist、user allowlist、`mentioned_agent`，再写入去重键。白名单为空时视为未配置，不放行任何线上群消息。

- [ ] **Step 4: Implement SQLite audit and idempotent reply**

SQLite 表固定包含 `message_id` 主键、`group_id`、`user_id`、`question`、`pt`、`paths_json`、`tools_json`、`status`、`elapsed_ms`、`error_summary`、`created_at`、`finished_at`。只保存脱敏问题摘要和聚合结果元数据；模型密钥、数据库密码、个人明细不落库。发送前记录 started，发送成功/失败分别记录 replied/failed；重复 message ID 直接返回 duplicate。

- [ ] **Step 5: Implement sender boundary**

`DingTalkSender` 只接受已生成的 Markdown 和规范化 `reply_target`，不在 Adapter 中拼接业务 SQL。发送异常转为结构化 failed 结果并保留审计记录。既有日报 `DingTalkNotifier` 不改行为。

- [ ] **Step 6: Run adapter tests**

Run: `python -m pytest server/test_dingtalk_agent.py -q`

Expected: all mention, allowlist, dedupe, audit and send-failure tests pass.

- [ ] **Step 7: Commit**

```bash
git add server/dingtalk_agent.py server/test_dingtalk_agent.py
git commit -m "feat: add dingtalk agent adapter and audit"
```

## Task 5: Register the normalized event route in FastAPI

**Files:**
- Modify: `server/app.py:818-1000`
- Modify: `server/.env.example`
- Test: `server/test_dingtalk_agent.py`

**Interfaces:**
- `POST /api/dingtalk/attribution-agent/events` 接受 JSON 事件并返回 `ignored|forbidden|duplicate|replied|failed`。
- `GET /api/dingtalk/attribution-agent/health` 返回 `enabled`、`configured`、`allowed_group_count`，不返回任何密钥。

- [ ] **Step 1: Write failing route tests**

```python
def test_agent_health_does_not_expose_secrets(client, monkeypatch):
    monkeypatch.setenv("DINGTALK_AGENT_APP_SECRET", "secret-value")
    response = client.get("/api/dingtalk/attribution-agent/health")
    assert response.status_code == 200
    assert "secret-value" not in response.text

def test_disabled_agent_accepts_event_without_business_processing(client):
    response = client.post("/api/dingtalk/attribution-agent/events", json={"messageId": "m-disabled"})
    assert response.status_code == 200
    assert response.json()["status"] == "disabled"
```

- [ ] **Step 2: Run route tests and verify they fail**

Run: `python -m pytest server/test_dingtalk_agent.py -q`

Expected: FAIL because the routes are not registered.

- [ ] **Step 3: Register dependency-safe routes**

在 `app.py` 中延迟构造 Agent 依赖，启用关闭或配置不完整时仍返回 200/disabled；启用时实例化现有 `AttributionService`、`AttributionQueryTools`、`AttributionAgent`、`DingTalkAdapter`。事件路由只转发规范化 payload，不绕过 Adapter；健康接口只返回布尔值和数量。

- [ ] **Step 4: Add environment documentation**

在 `.env.example` 增加：

```text
DINGTALK_AGENT_ENABLED=false
DINGTALK_AGENT_APP_KEY=
DINGTALK_AGENT_APP_SECRET=
DINGTALK_AGENT_ALLOWED_GROUP_IDS=
DINGTALK_AGENT_ALLOWED_USER_IDS=
AI_AGENT_BASE_URL=
AI_AGENT_API_KEY=
AI_AGENT_MODEL=
AI_AGENT_TIMEOUT_SECONDS=30
```

并注明 `server/.env.local` 不提交、现有日报 Webhook 与 Agent 入站凭证用途不同。

- [ ] **Step 5: Run API tests and existing suites**

Run: `python -m pytest server/test_dingtalk_agent.py server/test_notification_report_route.py server/test_schedule_config.py -q`

Expected: all selected tests pass and existing notification/schedule tests remain green.

- [ ] **Step 6: Commit**

```bash
git add server/app.py server/.env.example server/test_dingtalk_agent.py
git commit -m "feat: expose dingtalk agent event routes"
```

## Task 6: Add local simulation and operator documentation

**Files:**
- Create: `server/scripts/simulate_dingtalk_agent.py`
- Modify: `README.md`
- Test: `server/test_dingtalk_agent.py`

- [ ] **Step 1: Write failing simulation test**

```python
def test_simulator_runs_without_network(monkeypatch, capsys):
    monkeypatch.setenv("DINGTALK_AGENT_ENABLED", "false")
    run_simulation({"messageId": "local-1", "text": "@助手 最新pt"})
    assert "disabled" in capsys.readouterr().out
```

- [ ] **Step 2: Run and verify failure**

Run: `python -m pytest server/test_dingtalk_agent.py::test_simulator_runs_without_network -q`

Expected: FAIL because the simulator is absent.

- [ ] **Step 3: Implement offline simulator**

脚本读取一个 JSON payload 或使用内置最小 payload，强制使用 fake sender，不访问钉钉、不访问模型网络；命令为 `python server/scripts/simulate_dingtalk_agent.py --payload path.json`。README 说明如何先调用 health，再使用一个已轮换凭证的测试群，如何验证普通消息、非白名单、重复消息、最新 pt、规则趋势、人数/件数通过率五类场景。

- [ ] **Step 4: Run simulator and docs checks**

Run: `python server/scripts/simulate_dingtalk_agent.py`; `python -m pytest server/test_dingtalk_agent.py -q`; `rg -n "DINGTALK_AGENT|AI_AGENT|simulate_dingtalk" README.md server/.env.example server/scripts/simulate_dingtalk_agent.py`

Expected: simulator prints a structured disabled/ignored result, tests pass, and all configuration/documentation keys are discoverable.

- [ ] **Step 5: Commit**

```bash
git add server/scripts/simulate_dingtalk_agent.py README.md server/test_dingtalk_agent.py
git commit -m "docs: add local dingtalk agent simulation"
```

## Task 7: Configure one test group and validate the end-to-end flow

**Files:**
- Modify only local ignored file: `server/.env.local`
- Test/command: `server/scripts/simulate_dingtalk_agent.py`, FastAPI health/event endpoints

- [ ] **Step 1: Keep the Agent disabled and verify startup**

Set `DINGTALK_AGENT_ENABLED=false`, start the API with the project’s existing command, then run `Invoke-RestMethod http://127.0.0.1:8010/api/dingtalk/attribution-agent/health`. Expected: `enabled=false`, no secret fields.

- [ ] **Step 2: Configure only a fresh test-group credential**

After the user supplies a newly rotated enterprise robot App Key/App Secret, set `DINGTALK_AGENT_APP_KEY`, `DINGTALK_AGENT_APP_SECRET`, one test group ID in `DINGTALK_AGENT_ALLOWED_GROUP_IDS`, one operator ID in `DINGTALK_AGENT_ALLOWED_USER_IDS`, and the model keys in `.env.local`; leave production groups absent.

- [ ] **Step 3: Validate five read-only questions**

Send only these test questions from the allowlisted operator: “看最新 pt 各等级规则有多少”、“看 20260902 某规则近 60 天趋势”、“这个规则件数通过率和人数通过率分别是多少”、“持续观察中的规则从打标 pt 开始表现如何”、“比较 20260901 和 20260902 的风险变化”。Expected: every answer contains pt/window/evidence; missing trend data reports the actual available pt; no state-changing endpoint is called.

- [ ] **Step 4: Validate security and idempotency**

Send a non-mention message, a blocked group message, an unauthorized user message, and the same message ID twice. Expected: no business data for unauthorized inputs and exactly one reply for the duplicate pair; audit rows show ignored/forbidden/duplicate/replied statuses.

- [ ] **Step 5: Enable the test group only after validation**

Set `DINGTALK_AGENT_ENABLED=true` only for the test group, restart the API, repeat the health check, and save the response status plus audit row count as the test evidence. Do not enable the existing daily-report Webhook path through this switch.

## Task 8: Full regression and handoff

**Files:**
- No new source files; preserve unrelated worktree changes.

- [ ] **Step 1: Run focused Agent regression**

Run: `python -m pytest server/test_attribution_agent.py server/test_attribution_query_tools.py server/test_dingtalk_agent.py -q`

Expected: all Agent tests pass.

- [ ] **Step 2: Run existing attribution, trend, notification and schedule regression**

Run: `python -m pytest server/test_path_trend_duckdb.py server/test_attribution_status.py server/test_person_approval_rate.py server/test_attribution_notification.py server/test_attribution_notification_sender.py server/test_schedule_config.py server/test_dingtalk_schedule.py -q`

Expected: existing suites remain green; the known script-style `smoke_auth_test.py`/`test_store_batch.py` collection behavior is reported separately rather than “fixed” as part of Agent work.

- [ ] **Step 3: Run static safety checks**

Run: `rg -n "execute\(|raw_sql|MAXCOMPUTE|APP_SECRET|API_KEY" server/attribution_agent.py server/attribution_query_tools.py server/dingtalk_agent.py`; `git diff --check`

Expected: no user-SQL execution path, no MaxCompute access in Agent modules, no secret value in source, and no whitespace errors.

- [ ] **Step 4: Commit the final documentation/test evidence**

```bash
git add README.md server/.env.example server/attribution_agent.py server/attribution_query_tools.py server/dingtalk_agent.py server/app.py server/scripts/simulate_dingtalk_agent.py server/test_attribution_agent.py server/test_attribution_query_tools.py server/test_dingtalk_agent.py
git commit -m "feat: deliver dingtalk attribution ai agent"
```

- [ ] **Step 5: Handoff**

交付内容包括：测试群入站配置、health 检查结果、五类问题验证结果、审计去重验证结果、回归测试结果，以及明确说明日报出站 Webhook 与 Agent 入站机器人是两套配置。
