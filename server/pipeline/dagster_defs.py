"""风险监控每日调度(Dagster)。

上游 MaxCompute 数据每日检查;本作业 14:00(Asia/Shanghai)执行:

    resolve_target_partition  # 校验最新 pt 就绪(未就绪自动重试,最多 3 次×20min)
        └→ publish_attribution  # 复用 pipeline.cli.compute_and_publish
                                 # (MaxCompute 聚合 + 路径趋势批量预计算 + DuckDB/快照发布)

组件:
- job:     nightly_attribution_job(in-process 执行,Windows 规避 spawn 兼容问题)
- schedule: nightly_attribution_1400(cron "00 14 * * *")
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
from datetime import date, datetime, timedelta, timezone
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
    FUND_REPORT_PREFIX,
    DingTalkNotifier,
    NotificationLedger,
    attach_tracked_only_rules,
    build_digest,
    build_fund_digest,
    capture_attribution_page,
    capture_fund_page,
    format_fund_markdown,
    format_markdown,
    format_s3_fund_summary_markdown,
    format_s3_summary_markdown,
    report_path_is_safe,
    s3_notifier_from_env,
)
from pipeline import SERVING_DIR  # noqa: E402
from pipeline import assemble as serving_assemble  # noqa: E402
from pipeline.cli import compute_and_publish  # noqa: E402
from fund_service import FundAttributionService, _run_sql_rows  # noqa: E402
from fund_pipeline.cli import compute_and_publish as compute_and_publish_fund  # noqa: E402
from fund_pipeline import SERVING_DIR as FUND_SERVING_DIR  # noqa: E402
from fund_pipeline import assemble as fund_serving_assemble  # noqa: E402


NOTIFICATION_LEDGER_PATH = SERVER_DIR / "data" / "attribution_dingtalk_notifications.sqlite3"
FUND_NOTIFICATION_LEDGER_PATH = SERVER_DIR / "data" / "fund_attribution_dingtalk_notifications.sqlite3"


def select_ready_partition(partitions: list[str], *, today: date) -> str | None:
    """Return yesterday's partition only when that exact upstream partition exists."""
    target = (today - timedelta(days=1)).strftime("%Y%m%d")
    candidates = sorted(
        {str(partition) for partition in partitions if str(partition).isdigit()},
        reverse=True,
    )
    if target not in candidates:
        return None
    return target


def _service() -> AttributionService:
    load_local_env()
    return AttributionService()


@op(
    description="校验上游最新 pt 分区就绪并确定目标分区",
    retry_policy=RetryPolicy(max_retries=3, delay=20 * 60),
)
def resolve_target_partition(context) -> str:
    """14:00 检查上游;若昨天分区尚未出现则等待重试(最多约 1 小时)。

    接受 latest >= 今天-1:兼容"当天产出当天分区"与"次日凌晨补昨日分区"
    两种上游命名习惯。重试耗尽仍不满足 → 判定失败并告警，不发布旧分区。
    """
    service = _service()
    partitions = service.refresh_partitions()
    if not partitions:
        raise Failure(description="MaxCompute 目标表没有任何可用 pt 分区")

    ready = select_ready_partition(partitions, today=datetime.now().date())
    if ready is None:
        latest = max(partitions)
        context.log.warning("上游昨天分区尚未出现，当前最新 pt=%s，20 分钟后重试", latest)
        raise RetryRequested(seconds_to_wait=20 * 60)
    context.log.info("上游就绪:目标分区 %s", ready)
    return ready


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


@op(
    description="检查资金归集上游昨天分区是否就绪",
    retry_policy=RetryPolicy(max_retries=3, delay=20 * 60),
)
def resolve_fund_target_partition(context) -> str:
    service = FundAttributionService()
    partitions = service.refresh_partitions()
    if not partitions:
        raise Failure(description="资金归集 MaxCompute 目标表没有任何可用 pt 分区")

    ready = select_ready_partition(partitions, today=datetime.now().date())
    if ready is None:
        latest = max(partitions)
        context.log.warning("资金归集上游昨天分区尚未出现，当前最新 pt=%s，20 分钟后重试", latest)
        raise RetryRequested(seconds_to_wait=20 * 60)
    context.log.info("资金归集上游就绪:目标分区 %s", ready)
    return ready


@op(description="对目标资金归集分区做计算并发布(DuckDB + serving 快照)")
def publish_fund_attribution(context, pt: str) -> dict[str, Any]:
    service = FundAttributionService()
    stats = compute_and_publish_fund(
        config=service.config,
        table=service.table_name,
        partition=pt,
        offset=0,
        query_rows=_run_sql_rows,
        source="dagster",
    )
    context.log.info(
        "fund published pt=%s alerts=%s path_days=%s run_id=%s",
        stats["pt"],
        stats["alerts"],
        stats["path_days"],
        stats["run_id"],
    )
    return stats


@job(
    description="资金归集每日预计算与发布",
    executor_def=in_process_executor,
)
def daily_fund_attribution_job():
    publish_fund_attribution(resolve_fund_target_partition())


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


def _latest_fund_serving_payload(offset: int = 0) -> tuple[str, dict[str, Any]] | None:
    meta_path = Path(FUND_SERVING_DIR) / "meta.json"
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
                for path in Path(FUND_SERVING_DIR).glob(pattern)
            },
            reverse=True,
        )
    for pt in sorted(dict.fromkeys(candidates), reverse=True):
        payload = fund_serving_assemble.read_dashboard_snapshot(FUND_SERVING_DIR, pt, offset)
        if payload is not None:
            return pt, payload
    return None


def _notification_report_path(pt: str) -> Path:
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    return report_path_is_safe(DEFAULT_REPORT_DIR, f"credit_attribution_{pt}_{timestamp}.png")


def _fund_notification_report_path(pt: str) -> Path:
    from attribution_notification import fund_report_path_is_safe

    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    return fund_report_path_is_safe(DEFAULT_REPORT_DIR, f"{FUND_REPORT_PREFIX}_{pt}_{timestamp}.png")


@op(
    description="读取昨天授信归因快照，优先发送截图并回退发送文字日报",
    retry_policy=RetryPolicy(max_retries=3, delay=20 * 60),
)
def notify_attribution_dingtalk(context) -> dict[str, Any]:
    load_local_env()
    latest = _latest_serving_payload()
    if latest is None:
        context.log.warning("没有可用的授信归因 serving 快照，跳过钉钉日报")
        return {"status": "skipped", "reason": "no_serving_snapshot"}

    pt, payload = latest
    if select_ready_partition([pt], today=datetime.now().date()) is None:
        context.log.warning("授信归因 serving 快照尚未更新到昨天分区(pt=%s)，20 分钟后重试", pt)
        raise RetryRequested(seconds_to_wait=20 * 60)
    payload = _service().with_rule_statuses(payload)
    web_url = os.getenv("ATTRIBUTION_WEB_URL", "").strip()
    public_base = os.getenv("ATTRIBUTION_PUBLIC_BASE_URL", "").strip().rstrip("/")
    s3_notifier = s3_notifier_from_env()
    notifier = DingTalkNotifier()
    ledger = NotificationLedger(NOTIFICATION_LEDGER_PATH)
    has_delivery_channel = s3_notifier is not None or bool(notifier.webhook_url)
    if has_delivery_channel and not ledger.claim(pt):
        context.log.info("pt=%s already sent, skip duplicate notification", pt)
        return {"status": "already_sent", "pt": pt}

    report_path: Path | None = None
    if web_url:
        report_path = _notification_report_path(pt)
        try:
            capture_attribution_page(
                web_url,
                os.getenv("ATTRIBUTION_NOTIFY_USERNAME", "").strip(),
                os.getenv("ATTRIBUTION_NOTIFY_PASSWORD", "").strip(),
                report_path,
            )
        except Exception:
            report_path = None
            context.log.exception("生成授信归因完整长截图失败，回退发送文字日报，pt=%s", pt)
    else:
        context.log.warning("未配置 ATTRIBUTION_WEB_URL，回退发送授信归因文字日报，pt=%s", pt)

    report_url = (
        f"{public_base}/api/credit-attribution/notification-reports/{report_path.name}"
        if public_base and report_path is not None
        else None
    )
    digest = build_digest(payload, report_url=report_url, page_url=web_url)
    markdown = format_markdown(digest)
    try:
        if s3_notifier is not None and report_path is not None:
            response = s3_notifier.upload(report_path, pt)
            summary_markdown = format_s3_summary_markdown(
                digest,
                image_url=response["image_url"],
                page_url=web_url,
            )
            summary_response = s3_notifier.send_markdown(summary_markdown)
            response = {**response, "summary_response": summary_response}
            delivery_name = response["object_name"]
        elif s3_notifier is not None:
            response = s3_notifier.send_markdown(markdown)
            delivery_name = f"credit_attribution_{pt}_markdown"
        else:
            response = notifier.send_markdown(markdown)
            delivery_name = report_path.name if report_path is not None else f"credit_attribution_{pt}_markdown"
        ledger.mark_sent(pt, delivery_name)
    except Exception:
        ledger.release(pt)
        context.log.exception("发送授信归因钉钉日报失败，pt=%s", pt)
        raise
    context.log.info("授信归因钉钉日报发送成功：pt=%s report=%s", pt, report_path or "markdown")
    return {"status": "sent", "pt": pt, "report_path": str(report_path) if report_path else None, "response": response}


@op(
    description="读取昨天资金归集快照，截图并发送钉钉日报（模板与授信归因一致）",
    retry_policy=RetryPolicy(max_retries=3, delay=20 * 60),
)
def notify_fund_dingtalk(context) -> dict[str, Any]:
    load_local_env()
    latest = _latest_fund_serving_payload()
    if latest is None:
        context.log.warning("没有可用的资金归集 serving 快照，跳过钉钉日报")
        return {"status": "skipped", "reason": "no_fund_serving_snapshot"}

    pt, payload = latest
    if select_ready_partition([pt], today=datetime.now().date()) is None:
        context.log.warning("资金归集 serving 快照尚未更新到昨天分区(pt=%s)，20 分钟后重试", pt)
        raise RetryRequested(seconds_to_wait=20 * 60)

    s3_notifier = s3_notifier_from_env(
        filename_prefix=FUND_REPORT_PREFIX,
        object_prefix=os.getenv("DINGTALK_S3_FUND_PREFIX"),
    )
    notifier = DingTalkNotifier()
    ledger = NotificationLedger(FUND_NOTIFICATION_LEDGER_PATH)
    if not ledger.claim(pt):
        context.log.info("fund pt=%s already sent, skip duplicate notification", pt)
        return {"status": "already_sent", "pt": pt}

    try:
        service = FundAttributionService()
        payload = attach_tracked_only_rules(
            service.with_rule_statuses(payload), service.active_tracked_rules()
        )
        page_url = os.getenv("ATTRIBUTION_FUND_WEB_URL", "").strip() or None
        public_base = os.getenv("ATTRIBUTION_PUBLIC_BASE_URL", "").strip().rstrip("/")
        report_path: Path | None = None
        if page_url:
            report_path = _fund_notification_report_path(pt)
            try:
                capture_fund_page(
                    page_url,
                    os.getenv("ATTRIBUTION_NOTIFY_USERNAME", "").strip(),
                    os.getenv("ATTRIBUTION_NOTIFY_PASSWORD", "").strip(),
                    report_path,
                )
            except Exception:
                report_path = None
                context.log.exception("生成资金归集完整长截图失败，回退发送文字日报，pt=%s", pt)
        else:
            context.log.warning("未配置 ATTRIBUTION_FUND_WEB_URL，资金归集日报只发送文字摘要，pt=%s", pt)

        report_url = (
            f"{public_base}/api/fund-attribution/notification-reports/{report_path.name}"
            if public_base and report_path is not None
            else None
        )
        digest = build_fund_digest(payload, report_url=report_url, page_url=page_url)
        if s3_notifier is not None and report_path is not None:
            uploaded = s3_notifier.upload(report_path, pt)
            markdown = format_s3_fund_summary_markdown(
                digest,
                image_url=uploaded["image_url"],
                page_url=page_url,
            )
            response = s3_notifier.send_markdown(markdown, title="资金归集日报")
            delivery_name = uploaded["object_name"]
        else:
            response = notifier.send_markdown(
                format_fund_markdown(digest), title="资金归集日报"
            )
            delivery_name = (
                report_path.name if report_path is not None else f"fund_attribution_{pt}_markdown"
            )
        ledger.mark_sent(pt, delivery_name)
    except Exception:
        ledger.release(pt)
        context.log.exception("发送资金归集钉钉日报失败，pt=%s", pt)
        raise

    context.log.info("资金归集钉钉日报发送成功：pt=%s", pt)
    return {"status": "sent", "pt": pt, "response": response}


@job(
    description="授信归因每日 14:20 截图和预警摘要通知",
    executor_def=in_process_executor,
)
def daily_attribution_dingtalk_job():
    notify_attribution_dingtalk()


@job(
    description="资金归集每日 14:20 预警摘要通知",
    executor_def=in_process_executor,
)
def daily_fund_attribution_dingtalk_job():
    notify_fund_dingtalk()


nightly_schedule = ScheduleDefinition(
    job=nightly_attribution_job,
    cron_schedule="00 14 * * *",  # 每天 14:00,检查昨天分区后再发布
    execution_timezone="Asia/Shanghai",
    name="nightly_attribution_1400",
)


fund_schedule = ScheduleDefinition(
    job=daily_fund_attribution_job,
    cron_schedule="00 14 * * *",  # 每天 14:00,检查昨天分区后再发布
    execution_timezone="Asia/Shanghai",
    name="daily_fund_attribution_1400",
)


dingtalk_schedule = ScheduleDefinition(
    job=daily_attribution_dingtalk_job,
    cron_schedule="20 14 * * *",
    execution_timezone="Asia/Shanghai",
    name="daily_attribution_dingtalk_1420",
)


fund_dingtalk_schedule = ScheduleDefinition(
    job=daily_fund_attribution_dingtalk_job,
    cron_schedule="20 14 * * *",
    execution_timezone="Asia/Shanghai",
    name="daily_fund_attribution_dingtalk_1420",
)


MODEL_MONITOR_CACHE_MAX_AGE_HOURS = float(os.getenv("MODEL_MONITOR_CACHE_MAX_AGE_HOURS", "20"))


@op(
    description="预计算模型监控默认视图（全部模型分）并写入磁盘缓存，供页面秒开",
    retry_policy=RetryPolicy(max_retries=3, delay=20 * 60),
)
def precompute_model_monitoring(context) -> dict[str, Any]:
    service = _service()
    partitions = service.model_monitoring_partitions()
    if not partitions:
        raise Failure(description="模型监控表没有任何可用 pt 分区")
    latest = select_ready_partition(partitions, today=datetime.now().date())
    if latest is None:
        context.log.warning("模型监控上游昨天分区尚未出现，当前最新 pt=%s，20 分钟后重试", max(partitions))
        raise RetryRequested(seconds_to_wait=20 * 60)
    info = service.model_monitoring_disk_cache_info(latest)
    age_seconds = datetime.now(timezone.utc).timestamp() - float((info or {}).get("generated_at") or 0)
    if info and age_seconds < MODEL_MONITOR_CACHE_MAX_AGE_HOURS * 3600:
        context.log.info("模型监控缓存已新鲜(pt=%s, %.1f 小时前生成)，跳过预计算", latest, age_seconds / 3600)
        # 仍确保标签选项缓存存在（缺失才查一次）
        service.model_monitoring_filters(partition=latest)
        return {"status": "skipped", "pt": latest, "model_count": info.get("model_count")}
    payload = service.model_monitoring(partition=latest, force=True)
    context.log.info(
        "模型监控预计算完成: pt=%s models=%s weekly_rows=%s",
        latest,
        len(payload.get("model_coverage") or []),
        len(payload.get("model_effect_weekly") or []),
    )
    service.model_monitoring_filters(partition=latest, force=True)
    return {"status": "computed", "pt": latest, "model_count": len(payload.get("model_coverage") or [])}


@job(
    description="模型监控夜间预计算（缓存默认全模型分视图）",
    executor_def=in_process_executor,
)
def nightly_model_monitoring_job():
    precompute_model_monitoring()


model_monitoring_schedule = ScheduleDefinition(
    job=nightly_model_monitoring_job,
    cron_schedule="30 14 * * *",  # 每天 14:30,检查昨天分区后再预计算
    execution_timezone="Asia/Shanghai",
    name="nightly_model_monitoring_1430",
)


@run_status_sensor(
    run_status=DagsterRunStatus.FAILURE,
    monitored_jobs=[
        nightly_attribution_job,
        daily_fund_attribution_job,
        daily_attribution_dingtalk_job,
        daily_fund_attribution_dingtalk_job,
        nightly_model_monitoring_job,
    ],
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
    jobs=[
        nightly_attribution_job,
        daily_fund_attribution_job,
        daily_attribution_dingtalk_job,
        daily_fund_attribution_dingtalk_job,
        nightly_model_monitoring_job,
    ],
    schedules=[
        nightly_schedule,
        fund_schedule,
        dingtalk_schedule,
        fund_dingtalk_schedule,
        model_monitoring_schedule,
    ],
    sensors=[nightly_attribution_failure_sensor],
)
