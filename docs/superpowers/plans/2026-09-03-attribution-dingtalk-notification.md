# 授信归因钉钉日报通知 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 每天 10:30 从最新授信归因 serving 快照生成完整长截图和预警摘要，并通过钉钉加签 Markdown 发送。

**Architecture:** 新增一个纯 Python 通知模块，负责摘要、报告文件、钉钉签名和幂等发送；Dagster 的 10:30 job 只负责读取最新 serving payload、调用通知模块和记录结果。截图由 Playwright 使用配置账号打开前端页面完成，PNG 通过 API 的安全只读接口提供 URL。

**Tech Stack:** Python 3、FastAPI、Dagster、DuckDB/Parquet serving、Playwright、SQLite、pytest、DingTalk custom robot webhook。

## Global Constraints

- 使用最新已发布 serving 快照，不在 10:30 通知 job 中重新查询 MaxCompute。
- 时区固定为 `Asia/Shanghai`，调度 cron 固定为 `30 10 * * *`。
- 钉钉 Webhook URL、Secret、截图登录凭据只从环境变量或 `server/.env.local` 读取，禁止写入 Git、测试输出和日志。
- 当前处于 status 1/2 且当天未命中的规则仍要出现在摘要中，并标记为持续跟踪。
- 同一 pt 只发送一次；dry-run 生成截图但不写入已发送记录。
- 不修改用户已有的未提交文件：`server/config/attribution_config.json`、`server/pipeline/dagster_defs.py`、`server/scripts/start_dagster.ps1`、`server/scripts/stop_dagster.ps1` 以外的无关改动也不纳入本次提交。

---

### Task 1: Add notification data contracts and digest builder

**Files:**
- Create: `server/attribution_notification.py`
- Create: `server/test_attribution_notification.py`

**Interfaces:**
- Produces `build_digest(payload: dict[str, Any], *, report_url: str | None, page_url: str | None) -> dict[str, Any]`.
- Produces `format_markdown(digest: dict[str, Any]) -> str`.
- Produces `DingTalkNotifier.build_signed_url(timestamp_ms: int | None = None) -> str`.

- [ ] **Step 1: Write the failing tests**

```python
from attribution_notification import build_digest, format_markdown


def test_digest_counts_levels_and_lists_active_hit_and_non_hit_rules():
    payload = {
        "meta": {"partition": "20260901", "generated_at": "2026-09-03T01:58:11Z"},
        "summary": {"merged_alert_count": 2, "level1_count": 1, "level2_count": 1, "level3_count": 0},
        "merged_alerts": [
            {"path": "命中规则", "level": 2, "level_label": "Level2", "status": 1,
             "tracking_start_pt": "20260828", "is_tracked_only": False,
             "hit_windows": ["近1日", "近3日"]},
            {"path": "未命中规则", "level": 0, "level_label": "未命中", "status": 2,
             "tracking_start_pt": "20260901", "is_tracked_only": True,
             "hit_windows": []},
        ],
    }

    digest = build_digest(payload, report_url="http://host/report.png", page_url="http://host/?page=attribution")

    assert digest["partition"] == "20260901"
    assert digest["level_counts"] == {"1": 1, "2": 1, "3": 0}
    assert digest["active_hits"][0]["path"] == "命中规则"
    assert digest["active_misses"][0]["path"] == "未命中规则"
    message = format_markdown(digest)
    assert "Level2" in message
    assert "本日未命中，仍在持续跟踪" in message
    assert "http://host/report.png" in message


def test_signed_url_uses_dingtalk_hmac():
    notifier = DingTalkNotifier(
        webhook_url="https://oapi.dingtalk.com/robot/send?access_token=token",
        secret="secret",
    )
    signed = notifier.build_signed_url(timestamp_ms=1700000000000)
    assert "timestamp=1700000000000" in signed
    assert "sign=" in signed
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest -q server/test_attribution_notification.py --basetemp E:\\agent\\monitor\\.pytest_tmp_notify_red`

Expected: FAIL with `ModuleNotFoundError: No module named 'attribution_notification'`.

- [ ] **Step 3: Implement the minimal digest and signer**

Implement `build_digest` with these exact rules:

```python
level_counts = {
    "1": int(summary.get("level1_count", 0)),
    "2": int(summary.get("level2_count", 0)),
    "3": int(summary.get("level3_count", 0)),
}
active_hits = [item for item in merged_alerts if int(item.get("status", 0)) in (1, 2) and not item.get("is_tracked_only")]
active_misses = [item for item in merged_alerts if int(item.get("status", 0)) in (1, 2) and item.get("is_tracked_only")]
```

Implement DingTalk signing with `HMAC-SHA256(timestamp + "\\n" + secret, secret)`, Base64, then `urllib.parse.quote_plus`. `format_markdown` must contain pt, Level 1/2/3 counts, total alerts, current active hits, tracked-but-not-hit rules, report link, and page link.

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest -q server/test_attribution_notification.py --basetemp E:\\agent\\monitor\\.pytest_tmp_notify_green`

Expected: PASS.

- [ ] **Step 5: Commit**

```powershell
git add server/attribution_notification.py server/test_attribution_notification.py
git commit -m "feat: build attribution dingtalk digest"
```

### Task 2: Add report file storage and safe API route

**Files:**
- Modify: `server/attribution_notification.py`
- Modify: `server/app.py`
- Create: `server/test_notification_report_route.py`

**Interfaces:**
- Produces `save_report_png(report_dir: Path, pt: str, content: bytes, now: datetime | None = None) -> Path`.
- Produces `report_path_is_safe(report_dir: Path, filename: str) -> Path`.
- API route: `GET /api/credit-attribution/notification-reports/{filename}` returns PNG only for validated filenames inside `server/data/notification_reports`.

- [ ] **Step 1: Write the failing tests**

```python
from datetime import datetime, timezone
from pathlib import Path
import pytest
from attribution_notification import report_path_is_safe, save_report_png


def test_report_filename_contains_pt_and_is_saved_under_report_dir(tmp_path: Path):
    path = save_report_png(tmp_path, "20260901", b"png", datetime(2026, 9, 3, tzinfo=timezone.utc))
    assert path.parent == tmp_path
    assert "20260901" in path.name
    assert path.suffix == ".png"
    assert path.read_bytes() == b"png"


def test_report_path_rejects_traversal(tmp_path: Path):
    with pytest.raises(ValueError):
        report_path_is_safe(tmp_path, "..\\secret.png")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest -q server/test_notification_report_route.py --basetemp E:\\agent\\monitor\\.pytest_tmp_report_red`

Expected: FAIL because the report helpers do not exist.

- [ ] **Step 3: Implement report storage and route**

Use a filename regex such as `^credit_attribution_(?:[A-Za-z0-9_-]+)_\\d{8}_\\d{6}\\.png$`. Resolve the candidate path and verify `candidate.parent == report_dir.resolve()` before reading. In `app.py`, import `FileResponse`, create `NOTIFICATION_REPORT_DIR`, and register the route without dashboard computation or MaxCompute access.

- [ ] **Step 4: Run focused tests**

Run: `pytest -q server/test_notification_report_route.py server/test_attribution_notification.py --basetemp E:\\agent\\monitor\\.pytest_tmp_report_green`

Expected: PASS.

- [ ] **Step 5: Commit**

```powershell
git add server/attribution_notification.py server/app.py server/test_notification_report_route.py
git commit -m "feat: serve attribution notification reports"
```

### Task 3: Add Playwright screenshotter and send/idempotency behavior

**Files:**
- Modify: `server/attribution_notification.py`
- Create: `server/test_attribution_notification_sender.py`

**Interfaces:**
- Produces `capture_attribution_page(web_url: str, username: str, password: str, output_path: Path, timeout_ms: int = 120000) -> Path`.
- Produces `DingTalkNotifier.send_markdown(markdown: str, *, title: str) -> dict[str, Any]`.
- Produces `NotificationLedger(path: Path).claim(pt: str) -> bool` and `.mark_sent(pt: str, report_name: str) -> None`.

- [ ] **Step 1: Write failing tests**

```python
from pathlib import Path
from attribution_notification import NotificationLedger


def test_notification_ledger_claims_a_pt_once(tmp_path: Path):
    ledger = NotificationLedger(tmp_path / "ledger.sqlite3")
    assert ledger.claim("20260901") is True
    assert ledger.claim("20260901") is False


def test_dry_run_does_not_claim_pt(tmp_path: Path):
    ledger = NotificationLedger(tmp_path / "ledger.sqlite3")
    assert ledger.claim("20260901") is True
    assert ledger.claim("20260902") is True
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest -q server/test_attribution_notification_sender.py --basetemp E:\\agent\\monitor\\.pytest_tmp_sender_red`

Expected: FAIL with missing `NotificationLedger`.

- [ ] **Step 3: Implement minimal sender**

Use `requests.post(..., json=payload, timeout=15)` and raise a descriptive error for non-200 or DingTalk `errcode != 0`. For screenshot capture, create a Playwright Chromium page, fill the first two login inputs, submit, navigate to the attribution page if necessary, wait for a visible `授信归因`/`合并预警结果` marker or network idle, then call `page.screenshot(path=..., full_page=True)`. Never log credentials or signed URLs.

Use SQLite table `attribution_dingtalk_notification(pt TEXT PRIMARY KEY, sent_at TEXT NOT NULL, report_name TEXT NOT NULL)`; `claim` is an atomic `INSERT OR IGNORE`. The caller must only mark sent after the Webhook returns success; on failure remove the claim or use a separate pending state so a later daily retry can send.

- [ ] **Step 4: Run tests and static compile**

Run: `pytest -q server/test_attribution_notification_sender.py server/test_attribution_notification.py --basetemp E:\\agent\\monitor\\.pytest_tmp_sender_green`

Run: `python -m py_compile server/attribution_notification.py`

Expected: PASS and exit code 0.

- [ ] **Step 5: Commit**

```powershell
git add server/attribution_notification.py server/test_attribution_notification_sender.py
git commit -m "feat: capture and send attribution report"
```

### Task 4: Register the 10:30 Dagster job and configuration

**Files:**
- Modify: `server/pipeline/dagster_defs.py`
- Modify: `server/.env.example`
- Create: `server/test_dingtalk_schedule.py`

**Interfaces:**
- Produces `notify_attribution_dingtalk(context) -> dict[str, Any]`.
- Produces Dagster schedule named `daily_attribution_dingtalk_1030` with cron `30 10 * * *` and timezone `Asia/Shanghai`.

- [ ] **Step 1: Write failing schedule/config tests**

```python
from pathlib import Path


def test_dingtalk_schedule_runs_at_1030_shanghai():
    text = Path("server/pipeline/dagster_defs.py").read_text(encoding="utf-8")
    assert 'cron_schedule="30 10 * * *"' in text
    assert 'execution_timezone="Asia/Shanghai"' in text
    assert 'name="daily_attribution_dingtalk_1030"' in text


def test_env_example_documents_dingtalk_without_credentials():
    text = Path("server/.env.example").read_text(encoding="utf-8")
    assert "DINGTALK_WEBHOOK_URL=" in text
    assert "DINGTALK_SECRET=" in text
    assert "ATTRIBUTION_PUBLIC_BASE_URL=" in text
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest -q server/test_dingtalk_schedule.py --basetemp E:\\agent\\monitor\\.pytest_tmp_schedule_red`

Expected: FAIL because the second schedule and environment entries do not exist.

- [ ] **Step 3: Implement the Dagster notification op/job/schedule**

The op must:

1. Read the newest local serving dashboard snapshot using `serving_assemble`/`SERVING_DIR`.
2. Return a clear `SkipReason` when no snapshot exists or no webhook is configured, while preserving a dry-run result when screenshot credentials and web URL are configured.
3. Build report URL from `ATTRIBUTION_PUBLIC_BASE_URL + /api/credit-attribution/notification-reports/<file>` and page URL from `ATTRIBUTION_WEB_URL`.
4. Capture the screenshot, build the digest, send Markdown when Webhook settings exist, and mark the pt sent only after success.

Do not call `compute_and_publish`. Keep the existing 09:50 job unchanged. Add the new job to `Definitions.jobs` and its schedule to `Definitions.schedules`.

- [ ] **Step 4: Run schedule tests and Dagster list**

Run: `pytest -q server/test_dingtalk_schedule.py server/test_schedule_config.py --basetemp E:\\agent\\monitor\\.pytest_tmp_schedule_green`

Run from `server`: `$env:DAGSTER_HOME=(Resolve-Path .\\dagster_home); dagster schedule list --workspace .\\workspace.yaml`

Expected: focused tests PASS and output contains `daily_attribution_dingtalk_1030 [RUNNING]` with cron `30 10 * * *`.

- [ ] **Step 5: Commit**

```powershell
git add server/pipeline/dagster_defs.py server/.env.example server/test_dingtalk_schedule.py
git commit -m "feat: schedule attribution dingtalk digest"
```

### Task 5: Generate and visually verify the dry-run screenshot

**Files:**
- Modify only local ignored file: `server/.env.local` if needed; never commit it.
- Output: `server/data/notification_reports/credit_attribution_<pt>_<timestamp>.png`

- [ ] **Step 1: Configure local non-secret URLs and credentials**

Set `ATTRIBUTION_PUBLIC_BASE_URL`, `ATTRIBUTION_WEB_URL`, `ATTRIBUTION_NOTIFY_USERNAME`, and `ATTRIBUTION_NOTIFY_PASSWORD` in local environment. Set `DINGTALK_WEBHOOK_URL` and `DINGTALK_SECRET` only when ready for real sending; first run with them absent.

- [ ] **Step 2: Execute dry-run**

Run a direct Python entry point or Dagster op with `dry_run=True` against the newest local serving snapshot. Expected output includes selected pt, report path, level counts, current-hit count, and tracked-but-not-hit count; no `requests.post` is called.

- [ ] **Step 3: View the screenshot**

Use the image viewer on the generated PNG and confirm the full page contains the授信归因 title, current pt, summary cards, merged alert result, and no loading/error overlay. If the screenshot is not correct, fix the screenshotter and rerun Task 3 tests before proceeding.

### Task 6: Perform one real DingTalk test and verify running services

**Files:**
- No tracked source changes expected.
- Local logs: `server/dagster_home/logs/`, preserve for verification.

- [ ] **Step 1: Add rotated test Webhook settings locally**

Do not use the exposed values from the user message without rotating them. Add the newly generated values to `server/.env.local`.

- [ ] **Step 2: Execute one real send for the newest pt**

Run the 10:30 notification op once with the same latest pt. Expected: DingTalk response JSON has `errcode == 0`, and the Markdown message contains the level counts, persistent tracking section, screenshot URL, and page URL.

- [ ] **Step 3: Verify idempotency**

Run the same notification op again. Expected: it skips the already-sent pt and does not create a second Webhook request.

- [ ] **Step 4: Restart and verify Dagster**

Run: `& .\\server\\scripts\\stop_dagster.ps1; & .\\server\\scripts\\start_dagster.ps1`

Run: `$env:DAGSTER_HOME=(Resolve-Path .\\server\\dagster_home); dagster schedule list --workspace .\\server\\workspace.yaml`

Expected: both `nightly_attribution_0950` and `daily_attribution_dingtalk_1030` are RUNNING, and no import/configuration errors appear in the daemon log.

- [ ] **Step 5: Run final verification**

Run: `pytest -q server/test_attribution_notification.py server/test_notification_report_route.py server/test_attribution_notification_sender.py server/test_dingtalk_schedule.py server/test_schedule_config.py --basetemp E:\\agent\\monitor\\.pytest_tmp_dingtalk_final`

Run: `python -m py_compile server/attribution_notification.py server/app.py server/pipeline/dagster_defs.py`

Run: `git diff --check HEAD~4..HEAD`

Expected: all focused tests PASS, compile exits 0, and diff check exits 0. Do not report the Webhook Secret in the final response.
