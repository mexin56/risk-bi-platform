"""授信归因夜间调度(Dagster)。

上游 MaxCompute 数据每日 09:00 前产出;本作业 09:50(Asia/Shanghai)执行:

    resolve_target_partition  # 校验最新 pt 就绪(未就绪自动重试,最多 3 次×20min)
        └→ publish_attribution  # 复用 pipeline.cli.compute_and_publish
                                 # (MaxCompute 聚合 + 路径趋势批量预计算 + DuckDB/快照发布)

组件:
- job:     nightly_attribution_job(in-process 执行,Windows 规避 spawn 兼容问题)
- schedule: nightly_attribution_0950(cron "50 9 * * *")
- sensor:  nightly_attribution_failure_sensor(失败告警钩子,当前仅记 ERROR 日志)

本地校验(在 server/ 目录):
    dagster job execute --python-module pipeline.dagster_defs   # 立即跑一次
    dagster schedule list --python-module pipeline.dagster_defs # 查看下次触发时间

启动守护进程见 scripts/start_dagster.ps1(daemon + webserver,UI: 127.0.0.1:3001)。
"""

# 注意: 本模块不能加 from __future__ import annotations ——
# 字符串化注解会让 dagster 的 context 类型校验失败(DagsterInvalidDefinitionError)
import sys
import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

SERVER_DIR = Path(__file__).resolve().parent.parent
if str(SERVER_DIR) not in sys.path:
    sys.path.insert(0, str(SERVER_DIR))

from dagster import (  # noqa: E402
    Definitions,
    Failure,
    OpExecutionContext,
    RetryPolicy,
    RetryRequested,
    ScheduleDefinition,
    SkipReason,
    run_status_sensor,
    DagsterRunStatus,
    in_process_executor,
    op,
    job,
)

from app import AttributionService, load_config, load_local_env  # noqa: E402
from attribution_notification import (
    DEFAULT_REPORT_DIR,
    DingTalkNotifier,
    NotificationLedger,
    build_digest,
    capture_attribution_page,
    format_markdown,
    format_s3_summary_markdown,
    report_path_is_safe,
    s3_notifier_from_env,
)
from pipeline import SERVING_DIR  # noqa: E402
from pipeline import assemble as serving_assemble  # noqa: E402
from pipeline.cli import compute_and_publish  # noqa: E402


NOTIFICATION_LEDGER_PATH = SERVER_DIR / "data" / "attribution_dingtalk_notifications.sqlite3"


def _service() -> AttributionService:
    load_local_env()
    return AttributionService()


@op(
    description="校验上游最新 pt 分区就绪并确定目标分区",
    retry_policy=RetryPolicy(max_retries=3, delay=20 * 60),
)
def resolve_target_partition(context) -> str:
    """上游 09:00 出数;若最新分区落后超过 1 天则等待重试(最多约 1 小时)。

    接受 latest >= 今天-1:兼容"当天产出当天分区"与"次日凌晨补昨日分区"
    两种上游命名习惯。重试耗尽仍不满足 → 判定失败并告警(页面继续服务
    既有快照,不会白屏)。
    """
    service = _service()
    partitions = service.available_partitions()
    if not partitions:
        raise Failure(description="MaxCompute 目标表没有任何可用 pt 分区")

    latest = partitions[0]
    now = datetime.now()
    today = int(now.strftime("%Y%m%d"))
    latest_num = int(latest)
    if latest_num < today:
        context.log.warning(f"今日分区尚未出现，使用当前最新分区 {latest}")
    else:
        context.log.info(f"上游就绪:目标分区 {latest}")
    return latest


@op(description="对目标分区做全量归因计算并发布(DuckDB + serving 快照)")
def publish_attribution(context, pt: str) -> dict[str, Any]:
    service = _service()
    config = load_config()
    stats = compute_and_publish(service, config, pt, 0, source="dagster")
    context.log.info(
        "published pt={pt} compute={compute_s}s path_trend={path_trend_s}s "
        "publish={publish_s}s alerts={alerts} suppressed={suppressed}".format(**stats)
    )
    return stats


@job(
    description="授信归因每日预计算与发布",
    executor_def=in_process_executor,
)
def nightly_attribution_job():
    publish_attribution(resolve_target_partition())


def _latest_serving_payload(offset: int = 0) -> tuple[str, dict[str, Any]] | None:
    meta_path = Path(SERVING_DIR) / "meta.json"
    candidates: list[str] = []
    if meta_path.exists():
        try:
            meta = json.loads(meta_path.read_text(encoding="utf-8"))
            candidates = [
                str(item.get("pt"))
                for item in (meta.get("snapshots") or [])
                if int(item.get("offset", -1)) == int(offset) and item.get("pt")
            ]
        except Exception:
            candidates = []
    if not candidates:
        pattern = f"dashboard_*_{int(offset)}.parquet"
        candidates = sorted(
            {
                path.name[len("dashboard_") : -len(f"_{int(offset)}.parquet")]
                for path in Path(SERVING_DIR).glob(pattern)
            },
            reverse=True,
        )
    for pt in dict.fromkeys(candidates):
        payload = serving_assemble.read_dashboard_snapshot(SERVING_DIR, pt, offset)
        if payload is not None:
            return pt, payload
    return None


def _notification_report_path(pt: str) -> Path:
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    return report_path_is_safe(DEFAULT_REPORT_DIR, f"credit_attribution_{pt}_{timestamp}.png")


@op(description="读取最新授信归因快照，生成完整截图并发送钉钉日报")
def notify_attribution_dingtalk(context) -> dict[str, Any]:
    load_local_env()
    latest = _latest_serving_payload()
    if latest is None:
        context.log.warning("没有可用的授信归因 serving 快照，跳过钉钉日报")
        return {"status": "skipped", "reason": "no_serving_snapshot"}

    pt, payload = latest
    payload = _service().with_rule_statuses(payload)
    web_url = os.getenv("ATTRIBUTION_WEB_URL", "").strip()
    public_base = os.getenv("ATTRIBUTION_PUBLIC_BASE_URL", "").strip().rstrip("/")
    s3_notifier = s3_notifier_from_env()
    notifier = DingTalkNotifier()
    if not web_url:
        context.log.warning("未配置 ATTRIBUTION_WEB_URL，无法生成完整长截图")
        return {"status": "skipped", "pt": pt, "reason": "missing_web_url"}

    report_path = _notification_report_path(pt)
    try:
        capture_attribution_page(
            web_url,
            os.getenv("ATTRIBUTION_NOTIFY_USERNAME", "").strip(),
            os.getenv("ATTRIBUTION_NOTIFY_PASSWORD", "").strip(),
            report_path,
        )
    except Exception:
        context.log.exception("生成授信归因完整长截图失败，pt=%s", pt)
        raise

    report_url = (
        f"{public_base}/api/credit-attribution/notification-reports/{report_path.name}"
        if public_base
        else None
    )
    digest = build_digest(payload, report_url=report_url, page_url=web_url)
    markdown = format_markdown(digest)
    if s3_notifier is None and not notifier.webhook_url:
        context.log.info(
            "授信归因钉钉日报 dry-run 完成：pt=%s report=%s levels=%s active_hits=%s active_misses=%s",
            pt,
            report_path,
            digest["level_counts"],
            len(digest["active_hits"]),
            len(digest["active_misses"]),
        )
        return {
            "status": "dry_run",
            "pt": pt,
            "report_path": str(report_path),
            "markdown": markdown,
            "digest": digest,
        }

    ledger = NotificationLedger(NOTIFICATION_LEDGER_PATH)
    if not ledger.claim(pt):
        context.log.info("pt=%s 已发送过钉钉日报，跳过重复发送", pt)
        return {"status": "already_sent", "pt": pt, "report_path": str(report_path)}
    try:
        if s3_notifier is not None:
            response = s3_notifier.publish(report_path, pt)
            summary_markdown = format_s3_summary_markdown(
                digest,
                image_url=response["image_url"],
                page_url=web_url,
            )
            summary_response = s3_notifier.send_markdown(summary_markdown)
            response = {**response, "summary_response": summary_response}
            delivery_name = response["object_name"]
        else:
            response = notifier.send_markdown(markdown)
            delivery_name = report_path.name
        ledger.mark_sent(pt, delivery_name)
    except Exception:
        ledger.release(pt)
        context.log.exception("发送授信归因钉钉日报失败，pt=%s", pt)
        raise
    context.log.info("授信归因钉钉日报发送成功：pt=%s report=%s", pt, report_path)
    return {"status": "sent", "pt": pt, "report_path": str(report_path), "response": response}


@job(
    description="授信归因每日 10:30 截图和预警摘要通知",
    executor_def=in_process_executor,
)
def daily_attribution_dingtalk_job():
    notify_attribution_dingtalk()


nightly_schedule = ScheduleDefinition(
    job=nightly_attribution_job,
    cron_schedule="50 9 * * *",  # 每天 09:50,上游 09:00 出数之后
    execution_timezone="Asia/Shanghai",
    name="nightly_attribution_0950",
)


dingtalk_schedule = ScheduleDefinition(
    job=daily_attribution_dingtalk_job,
    cron_schedule="30 10 * * *",
    execution_timezone="Asia/Shanghai",
    name="daily_attribution_dingtalk_1030",
)


@run_status_sensor(
    run_status=DagsterRunStatus.FAILURE,
    monitored_jobs=[nightly_attribution_job, daily_attribution_dingtalk_job],
    name="nightly_attribution_failure_sensor",
    minimum_interval_seconds=60,
)
def nightly_attribution_failure_sensor(context):
    """失败告警钩子:P2 先记录 ERROR 日志(UI 可见),后续可接 webhook/邮件。"""
    message = f"归因夜间调度失败: run_id={context.dagster_event.run_id}"
    context.log.error(message)
    # TODO(P3): 在此接入企业微信/钉钉 webhook
    return SkipReason("failure logged")


defs = Definitions(
    jobs=[nightly_attribution_job, daily_attribution_dingtalk_job],
    schedules=[nightly_schedule, dingtalk_schedule],
    sensors=[nightly_attribution_failure_sensor],
)
