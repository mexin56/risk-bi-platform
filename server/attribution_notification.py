"""Daily DingTalk notification helpers for the credit-attribution dashboard."""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import math
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


def _build_risk_points(
    payload: dict[str, Any],
    level_counts: dict[str, int],
    active_hits: list[dict[str, Any]],
    active_misses: list[dict[str, Any]],
) -> list[str]:
    summary = payload.get("summary") or {}
    alerts = [item for item in (payload.get("merged_alerts") or []) if isinstance(item, dict)]
    focus = payload.get("highlight") if isinstance(payload.get("highlight"), dict) else None
    if focus is None and alerts:
        focus = max(
            alerts,
            key=lambda item: (
                int(item.get("level", 0) or 0),
                float(item.get("z_score", 0) or 0),
            ),
        )

    level3 = level_counts["3"]
    if focus and int(focus.get("level", 0) or 0) >= 3:
        windows = "、".join(str(value) for value in (focus.get("hit_windows") or [])) or "当前窗口"
        growth = float(focus.get("growth_factor", 0) or 0)
        z_score = float(focus.get("z_score", 0) or 0)
        point1 = (
            f"高风险预警：当前 Level3 红色规则 {level3} 条；重点路径 **{focus.get('path') or '未命名规则'}** "
            f"在 {focus.get('primary_window_label') or '观察窗口'} 命中 {windows}，增长 {growth:.2f} 倍、z-score {z_score:.2f}，请优先核查。"
        )
    else:
        point1 = f"高风险预警：当前 Level3 红色规则 {level3} 条，暂未发现需要优先升级的 Level3 重点路径。"

    level23 = level_counts["2"] + level_counts["3"]
    total = max(1, int(summary.get("merged_alert_count", len(alerts)) or 0))
    share = level23 / total * 100
    change = float(summary.get("latest_day_change_pct", 0) or 0)
    point2 = (
        f"趋势与结构风险：Level2+Level3 共 {level23} 条，占全部预警 {share:.2f}%；"
        f"最新日申请量较前一日 {'增长' if change >= 0 else '下降'} {abs(change):.2f}%，建议重点排查集中来源和连续命中窗口。"
    )

    if active_hits or active_misses:
        hit_names = "、".join(item["path"] for item in active_hits[:2]) or "无"
        miss_names = "、".join(item["path"] for item in active_misses[:2]) or "无"
        point3 = (
            f"持续跟踪风险：当前仍命中的打标规则 {len(active_hits)} 条（{hit_names}），"
            f"本日未命中，仍在持续跟踪 {len(active_misses)} 条（{miss_names}），请持续关注后续 pt。"
        )
    else:
        point3 = (
            f"通过率风险：最新日件数通过率 {_fmt_pct(summary.get('latest_approval_rate'))}，"
            f"人数通过率 {_fmt_pct(summary.get('latest_cid_approval_rate_pct'))}；请关注两项指标与异常规则是否同步变化。"
        )
    tracked_hit_names = "\u3001".join(item["path"] for item in active_hits[:2]) or "\u65e0"
    tracked_miss_names = "\u3001".join(item["path"] for item in active_misses[:2]) or "\u65e0"
    point3 = (
        f"\u6301\u7eed\u8ddf\u8e2a\u98ce\u9669\uff1a\u5f53\u524d\u4ecd\u547d\u4e2d\u7684\u6253\u6807\u89c4\u5219 {len(active_hits)} \u6761\uff08{tracked_hit_names}\uff09\uff0c"
        f"\u672c\u65e5\u672a\u547d\u4e2d\uff0c\u4ecd\u5728\u6301\u7eed\u8ddf\u8e2a {len(active_misses)} \u6761\uff08{tracked_miss_names}\uff09\uff0c\u8bf7\u6301\u7eed\u5173\u6ce8\u540e\u7eed pt\u3002"
    )
    return [point1, point3]


def _build_level3_risk_points(
    payload: dict[str, Any],
    level_counts: dict[str, int],
) -> list[str]:
    alerts = [item for item in (payload.get("merged_alerts") or []) if isinstance(item, dict)]
    highlight = payload.get("highlight")
    if not isinstance(highlight, dict) or int(highlight.get("level", 0) or 0) < 3:
        l3_alerts = [item for item in alerts if int(item.get("level", 0) or 0) >= 3]
        highlight = max(
            l3_alerts,
            key=lambda item: float(item.get("z_score", 0) or 0),
            default=None,
        )
    path = (highlight or {}).get("path") if isinstance(highlight, dict) else None
    return [f"重点路径：{path or '当前无 Level3 重点路径'}\n请优先核查"]


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
    digest = {
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
    digest["risk_points"] = _build_risk_points(payload, level_counts, active_hits, active_misses)
    return digest


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
        "# 授信归因日报",
        "",
        f"数据分区：`{digest['partition']}`",
        "",
    ]
    for index, point in enumerate(digest.get("risk_points") or [], start=1):
        point_lines = str(point).splitlines()
        if point_lines:
            lines.append(f"{index}. {point_lines[0]}")
            lines.extend(point_lines[1:])
            lines.append("")

    report_url = digest.get("report_url")
    page_url = digest.get("page_url")
    links = []
    if report_url:
        links.append(f"[查看原图]({report_url})")
    if page_url:
        links.append(f"[查看明细]({page_url})")
    if links:
        lines.extend(["", f"3、{'　　'.join(links)}"])
    return "\n".join(lines)


def format_s3_summary_markdown(
    digest: dict[str, Any],
    *,
    image_url: str,
    page_url: str | None = None,
) -> str:
    """Format the text follow-up with public original-image and detail links."""
    summary = format_markdown({**digest, "report_url": None, "page_url": None})
    links = []
    if image_url:
        links.append(f"[查看原图]({image_url})")
    if page_url:
        links.append(f"[查看明细]({page_url})")
    if not links:
        return summary
    return summary + "\n\n" + f"3、{'　　'.join(links)}"


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


class S3PngDingTalkNotifier:
    """Upload a PNG report to S3 and send its public URL through DingTalk."""

    def __init__(
        self,
        *,
        bucket: str,
        region: str,
        prefix: str,
        webhook_url: str,
        webhook_secret: str,
        public_base_url: str | None = None,
        s3_client: Any | None = None,
        session: Any | None = None,
        timeout: int = 30,
    ) -> None:
        self.bucket = bucket.strip()
        self.region = region.strip()
        self.prefix = prefix.strip().strip("/")
        self.webhook_url = webhook_url.strip()
        self.webhook_secret = webhook_secret.strip()
        self.public_base_url = (public_base_url or "").strip().rstrip("/")
        self.s3_client = s3_client
        self.session = session or requests.Session()
        self.timeout = timeout
        missing = [
            name
            for name, value in (
                ("bucket", self.bucket),
                ("region", self.region),
                ("webhook_url", self.webhook_url),
            )
            if not value
        ]
        if missing:
            raise ValueError(f"S3/转换服务配置缺失: {', '.join(missing)}")

    def _get_s3_client(self) -> Any:
        if self.s3_client is None:
            try:
                import boto3
            except ImportError as exc:
                raise RuntimeError("S3 推送需要安装 boto3") from exc
            self.s3_client = boto3.client("s3", region_name=self.region)
        return self.s3_client

    def upload(self, png_path: Path, pt: str) -> dict[str, str]:
        normalized_pt = str(pt).strip()
        if not re.fullmatch(r"[A-Za-z0-9_-]+", normalized_pt):
            raise ValueError("非法 pt")
        source = Path(png_path)
        if source.suffix.lower() != ".png" or not source.is_file():
            raise ValueError("PNG 截图文件不存在或格式不正确")
        filename = f"credit_attribution_{normalized_pt}.png"
        object_name = f"{self.prefix}/{filename}" if self.prefix else filename
        self._get_s3_client().upload_file(
                str(source),
                self.bucket,
                object_name,
                ExtraArgs={"ContentType": "image/png", "ACL": "public-read"},
            )
        image_url = self._public_url(object_name)
        return {"object_name": object_name, "image_url": image_url}

    def publish(self, png_path: Path, pt: str) -> dict[str, Any]:
        """Upload a PNG and send it as a DingTalk image message."""
        uploaded = self.upload(png_path, pt)
        response = self.session.post(
            self._signed_webhook_url(),
            json={"msgtype": "image", "image": {"picURL": uploaded["image_url"]}},
            headers={"Content-Type": "application/json"},
            timeout=self.timeout,
        )
        response.raise_for_status()
        result = response.json()
        if "errcode" in result and str(result["errcode"]) != "0":
            raise RuntimeError(f"钉钉图片消息发送失败: {result}")
        if "success" in result and result["success"] is False:
            raise RuntimeError(f"钉钉图片消息发送失败: {result}")
        return {**uploaded, "response": result}

    def _public_url(self, object_name: str) -> str:
        if self.public_base_url:
            return f"{self.public_base_url}/{urllib.parse.quote(object_name, safe='/')}"
        return f"https://{self.bucket}.s3.{self.region}.amazonaws.com/{urllib.parse.quote(object_name, safe='/')}"

    def _signed_webhook_url(self) -> str:
        if not self.webhook_secret:
            return self.webhook_url
        timestamp = str(round(time.time() * 1000))
        string_to_sign = f"{timestamp}\n{self.webhook_secret}".encode("utf-8")
        digest = hmac.new(
            self.webhook_secret.encode("utf-8"), string_to_sign, hashlib.sha256
        ).digest()
        separator = "&" if "?" in self.webhook_url else "?"
        sign = urllib.parse.quote_plus(base64.b64encode(digest))
        return f"{self.webhook_url}{separator}timestamp={timestamp}&sign={sign}"

    def send_markdown(self, markdown: str, *, title: str = "授信归因日报") -> dict[str, Any]:
        response = self.session.post(
            self._signed_webhook_url(),
            json={"msgtype": "markdown", "markdown": {"title": title, "text": markdown}},
            headers={"Content-Type": "application/json"},
            timeout=self.timeout,
        )
        response.raise_for_status()
        result = response.json()
        if "errcode" in result and str(result["errcode"]) != "0":
            raise RuntimeError(f"钉钉总结消息发送失败: {result}")
        if "success" in result and result["success"] is False:
            raise RuntimeError(f"钉钉总结消息发送失败: {result}")
        return result


def s3_notifier_from_env() -> S3PngDingTalkNotifier | None:
    """Build the S3 PNG delivery adapter only when its configuration exists."""
    settings = {
        "bucket": os.getenv("DINGTALK_S3_BUCKET", ""),
        "region": os.getenv("DINGTALK_S3_REGION", "eu-west-1"),
        "prefix": os.getenv("DINGTALK_S3_PREFIX", "credit_attribution"),
        "webhook_url": os.getenv("DINGTALK_WEBHOOK_URL", ""),
        "webhook_secret": os.getenv("DINGTALK_SECRET", ""),
        "public_base_url": os.getenv("DINGTALK_S3_PUBLIC_BASE_URL", ""),
    }
    required = ("bucket", "webhook_url")
    if not all(str(settings[name]).strip() for name in required):
        return None
    return S3PngDingTalkNotifier(**settings)


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
        browser = playwright.chromium.launch(**browser_launch_options())
        try:
            page = browser.new_page(viewport={"width": 1440, "height": 1000}, device_scale_factor=1)
            page.add_init_script(theme_init_script(os.getenv("ATTRIBUTION_NOTIFY_THEME", "teal").strip() or "teal"))
            page.goto(web_url, wait_until="domcontentloaded", timeout=timeout_ms)
            username_input = page.locator(login_username_selector())
            if username_input.count() > 0:
                if not username or not password:
                    raise ValueError("截图页面需要登录，但未配置 ATTRIBUTION_NOTIFY_USERNAME/PASSWORD")
                username_input.fill(username)
                page.locator(login_password_selector()).fill(password)
                page.locator(login_submit_selector()).click()
            page.wait_for_selector(attribution_ready_selector(), state="attached", timeout=timeout_ms)
            trend = page.locator(attribution_trend_selector())
            trend.wait_for(state="attached", timeout=timeout_ms)
            page.wait_for_function(
                trend_ready_expression(),
                arg=attribution_trend_selector(),
                timeout=timeout_ms,
            )
            content = page.locator(attribution_content_selector())
            # The application uses a fixed-height <main> with its own scrollbar.
            # A normal full_page screenshot only captures document.body, so the
            # lower trend chart would otherwise be outside the captured bitmap.
            page.evaluate(flatten_scroll_container())
            page.wait_for_timeout(300)
            content_box = content.bounding_box()
            if content_box is None:
                raise RuntimeError("授信归因内容区没有可截图边界")
            page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
            page.wait_for_timeout(300)
            page.evaluate("window.scrollTo(0, 0)")
            page.wait_for_timeout(300)
            full_page_path = output_path.with_suffix(".full.png")
            page.screenshot(path=str(full_page_path), full_page=True)
            from PIL import Image

            with Image.open(full_page_path) as image:
                image.crop(content_crop_box(content_box)).save(output_path, format="PNG")
            full_page_path.unlink(missing_ok=True)
        finally:
            browser.close()
    return output_path


def browser_launch_options() -> dict[str, Any]:
    options: dict[str, Any] = {"headless": True}
    executable = os.getenv("ATTRIBUTION_BROWSER_EXECUTABLE_PATH", "").strip()
    if executable:
        options["executable_path"] = executable
    return options


def login_submit_selector() -> str:
    return "button[type='submit']"


def login_username_selector() -> str:
    return "input[autocomplete='username'], input[placeholder='请输入用户名']"


def login_password_selector() -> str:
    return "input[autocomplete='current-password'], input[placeholder='请输入密码']"


def attribution_ready_selector() -> str:
    return attribution_content_selector()


def attribution_content_selector() -> str:
    return "[data-testid='credit-attribution-content']"


def attribution_trend_selector() -> str:
    return "[data-testid='credit-attribution-trend-chart']"


def trend_ready_expression() -> str:
    return "selector => Boolean(document.querySelector(selector)?.querySelector('canvas'))"


def flatten_scroll_container() -> str:
    """Return the JS used to expose the app's internal scroll content."""
    return """
        () => {
            const main = document.querySelector('main');
            let element = main;
            while (element && element !== document.body) {
                element.style.overflow = 'visible';
                element.style.height = 'auto';
                element.style.minHeight = '0';
                element.style.maxHeight = 'none';
                element = element.parentElement;
            }
            document.documentElement.style.height = 'auto';
            document.body.style.height = 'auto';
            document.body.style.overflow = 'visible';
        }
    """


def theme_init_script(theme_key: str) -> str:
    """Return a safe init script that selects the notification screenshot theme."""
    encoded = json.dumps(str(theme_key).strip() or "teal")
    return f"localStorage.setItem('rc-bi-theme', {encoded});"


def content_crop_box(box: dict[str, float]) -> tuple[int, int, int, int]:
    left = math.floor(float(box["x"]))
    top = math.floor(float(box["y"]))
    right = math.ceil(float(box["x"]) + float(box["width"]))
    bottom = math.ceil(float(box["y"]) + float(box["height"]))
    return left, top, right, bottom


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
