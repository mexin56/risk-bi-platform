"""Daily DingTalk notification helpers for the credit-attribution dashboard."""

from __future__ import annotations

import base64
import hashlib
import hmac
import os
import re
import sqlite3
import time
import urllib.parse
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import requests


DEFAULT_REPORT_DIR = Path(__file__).resolve().parent / "data" / "notification_reports"
REPORT_FILENAME_RE = re.compile(
    r"^credit_attribution_[A-Za-z0-9_-]+_\d{8}_\d{6}(?:_\d+)?\.png$"
)


def _status_label(status: int) -> str:
    return {1: "已上策略", 2: "持续观察"}.get(int(status), "未知状态")


def _compact_rule(item: dict[str, Any]) -> dict[str, Any]:
    status = int(item.get("status", 0))
    return {
        "path": str(item.get("path") or item.get("canonical_path") or "未命名规则"),
        "level": int(item.get("level") or 0),
        "level_label": str(item.get("level_label") or "未命中"),
        "status": status,
        "status_label": _status_label(status),
        "tracking_start_pt": item.get("tracking_start_pt"),
        "hit_windows": [str(value) for value in (item.get("hit_windows") or [])],
    }


def build_digest(
    payload: dict[str, Any],
    *,
    report_url: str | None = None,
    page_url: str | None = None,
) -> dict[str, Any]:
    meta = payload.get("meta") or {}
    summary = payload.get("summary") or {}
    alerts = [item for item in (payload.get("merged_alerts") or []) if isinstance(item, dict)]
    level_counts = {
        "1": int(summary.get("level1_count", 0) or 0),
        "2": int(summary.get("level2_count", 0) or 0),
        "3": int(summary.get("level3_count", 0) or 0),
    }
    tracked = [item for item in alerts if int(item.get("status", 0) or 0) in (1, 2)]
    active_hits = [_compact_rule(item) for item in tracked if not item.get("is_tracked_only")]
    active_misses = [_compact_rule(item) for item in tracked if item.get("is_tracked_only")]
    active_hits.sort(key=lambda item: (-int(item["level"]), str(item["path"])))
    active_misses.sort(key=lambda item: str(item["path"]))
    return {
        "partition": str(meta.get("partition") or "未知 pt"),
        "generated_at": str(meta.get("generated_at") or ""),
        "alert_total": int(summary.get("merged_alert_count", len(alerts)) or 0),
        "level_counts": level_counts,
        "latest_application_count": int(summary.get("latest_application_count", 0) or 0),
        "latest_approval_rate": summary.get("latest_approval_rate"),
        "latest_cid_approval_rate_pct": summary.get("latest_cid_approval_rate_pct"),
        "active_hits": active_hits,
        "active_misses": active_misses,
        "report_url": report_url,
        "page_url": page_url,
    }


def _fmt_pct(value: Any) -> str:
    if value is None or value == "":
        return "—"
    try:
        return f"{float(value):.2f}%"
    except (TypeError, ValueError):
        return str(value)


def format_markdown(digest: dict[str, Any]) -> str:
    counts = digest["level_counts"]
    lines = [
        "### 授信归因日报",
        "",
        f"数据分区：`{digest['partition']}`",
        f"预警规则：{digest['alert_total']} 条（Level1：{counts['1']}，Level2：{counts['2']}，Level3：{counts['3']}）",
        f"最新日申请量：{digest['latest_application_count']}，件数通过率：{_fmt_pct(digest['latest_approval_rate'])}，人数通过率：{_fmt_pct(digest['latest_cid_approval_rate_pct'])}",
        "",
        "#### 持续跟踪且当前仍命中",
    ]
    hits = digest.get("active_hits") or []
    if hits:
        for item in hits:
            windows = "、".join(item["hit_windows"]) or "当前窗口"
            lines.append(
                f"- `{item['path']}`：{item['status_label']}，{item['level_label']}，命中 {windows}；请持续关注。"
            )
    else:
        lines.append("- 当前没有持续跟踪且仍命中的规则。")

    lines.extend(["", "#### 持续跟踪但本日未命中"])
    misses = digest.get("active_misses") or []
    if misses:
        for item in misses:
            lines.append(
                f"- `{item['path']}`：{item['status_label']}，本日未命中，仍在持续跟踪（起始 pt：{item['tracking_start_pt'] or '未知'}）。"
            )
    else:
        lines.append("- 无。")

    report_url = digest.get("report_url")
    page_url = digest.get("page_url")
    if report_url:
        lines.extend(["", f"![授信归因完整截图]({report_url})", f"[打开完整截图]({report_url})"])
    if page_url:
        lines.append(f"[打开授信归因页面]({page_url})")
    return "\n".join(lines)


class DingTalkNotifier:
    def __init__(self, webhook_url: str | None = None, secret: str | None = None) -> None:
        self.webhook_url = (webhook_url if webhook_url is not None else os.getenv("DINGTALK_WEBHOOK_URL", "")).strip()
        self.secret = (secret if secret is not None else os.getenv("DINGTALK_SECRET", "")).strip()

    def build_signed_url(self, timestamp_ms: int | None = None) -> str:
        if not self.webhook_url:
            raise ValueError("DINGTALK_WEBHOOK_URL 未配置")
        if not self.secret:
            return self.webhook_url
        timestamp = str(timestamp_ms if timestamp_ms is not None else round(time.time() * 1000))
        string_to_sign = f"{timestamp}\n{self.secret}".encode("utf-8")
        digest = hmac.new(self.secret.encode("utf-8"), string_to_sign, hashlib.sha256).digest()
        sign = urllib.parse.quote_plus(base64.b64encode(digest))
        separator = "&" if "?" in self.webhook_url else "?"
        return f"{self.webhook_url}{separator}timestamp={timestamp}&sign={sign}"

    def send_markdown(self, markdown: str, *, title: str = "授信归因日报") -> dict[str, Any]:
        response = requests.post(
            self.build_signed_url(),
            headers={"Content-Type": "application/json"},
            json={"msgtype": "markdown", "markdown": {"title": title, "text": markdown}},
            timeout=15,
        )
        response.raise_for_status()
        result = response.json()
        if result.get("errcode") != 0:
            raise RuntimeError(f"钉钉发送失败：{result}")
        return result


def report_path_is_safe(report_dir: Path, filename: str) -> Path:
    if not REPORT_FILENAME_RE.fullmatch(str(filename)):
        raise ValueError("非法报告文件名")
    root = Path(report_dir).resolve()
    candidate = (root / filename).resolve()
    if candidate.parent != root:
        raise ValueError("报告路径越界")
    return candidate


def save_report_png(
    report_dir: Path,
    pt: str,
    content: bytes,
    now: datetime | None = None,
) -> Path:
    normalized_pt = str(pt).strip()
    if not re.fullmatch(r"[A-Za-z0-9_-]+", normalized_pt):
        raise ValueError("非法 pt")
    moment = now or datetime.now(timezone.utc)
    filename = f"credit_attribution_{normalized_pt}_{moment.strftime('%Y%m%d_%H%M%S')}.png"
    target = report_path_is_safe(Path(report_dir), filename)
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary = target.with_suffix(".png.tmp")
    temporary.write_bytes(content)
    os.replace(temporary, target)
    return target


def capture_attribution_page(
    web_url: str,
    username: str,
    password: str,
    output_path: Path,
    timeout_ms: int = 120_000,
) -> Path:
    from playwright.sync_api import sync_playwright

    output_path.parent.mkdir(parents=True, exist_ok=True)
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        try:
            page = browser.new_page(viewport={"width": 1440, "height": 1000}, device_scale_factor=1)
            page.goto(web_url, wait_until="domcontentloaded", timeout=timeout_ms)
            username_input = page.locator("input[autocomplete='username']")
            if username_input.count() > 0:
                if not username or not password:
                    raise ValueError("截图页面需要登录，但未配置 ATTRIBUTION_NOTIFY_USERNAME/PASSWORD")
                username_input.fill(username)
                page.locator("input[autocomplete='current-password']").fill(password)
                page.locator("form").press("Enter")
            page.wait_for_selector("text=授信归因", timeout=timeout_ms)
            page.screenshot(path=str(output_path), full_page=True)
        finally:
            browser.close()
    return output_path


class NotificationLedger:
    def __init__(self, path: Path) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with sqlite3.connect(str(self.path)) as connection:
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS attribution_dingtalk_notification (
                    pt TEXT PRIMARY KEY,
                    status TEXT NOT NULL,
                    claimed_at TEXT NOT NULL,
                    sent_at TEXT,
                    report_name TEXT
                )
                """
            )

    def claim(self, pt: str) -> bool:
        claimed_at = datetime.now(timezone.utc).isoformat(timespec="seconds")
        with sqlite3.connect(str(self.path)) as connection:
            cursor = connection.execute(
                "INSERT OR IGNORE INTO attribution_dingtalk_notification (pt, status, claimed_at) VALUES (?, 'pending', ?)",
                [str(pt), claimed_at],
            )
            return cursor.rowcount == 1

    def mark_sent(self, pt: str, report_name: str) -> None:
        sent_at = datetime.now(timezone.utc).isoformat(timespec="seconds")
        with sqlite3.connect(str(self.path)) as connection:
            connection.execute(
                "UPDATE attribution_dingtalk_notification SET status = 'sent', sent_at = ?, report_name = ? WHERE pt = ?",
                [sent_at, str(report_name), str(pt)],
            )

    def release(self, pt: str) -> None:
        with sqlite3.connect(str(self.path)) as connection:
            connection.execute(
                "DELETE FROM attribution_dingtalk_notification WHERE pt = ? AND status = 'pending'",
                [str(pt)],
            )
