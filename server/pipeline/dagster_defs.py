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
    DefaultScheduleStatus,
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
    fund_report_path_is_safe,
    publish_public_image_report,
    report_path_is_safe,
    s3_notifier_from_env,
    write_thumbnail,
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


def _serving_candidates(serving_dir: Path, offset: int = 0) -> list[str]:
    """从 DuckDB 发现已发布结果分区，通知与两个查询系统保持一致。"""
    return serving_assemble.published_partitions(serving_dir, offset)


def _load_serving_payload(
    serving_dir: Path,
    assembler: Any,
    pt: str,
    offset: int = 0,
) -> dict[str, Any] | None:
    """读单个分区快照；文件缺失或损坏时返回 None 而不是让整个日报失败。"""
    try:
        payload = assembler.read_dashboard_snapshot(serving_dir, pt, offset)
    except Exception:
        return None
    return payload if payload is not None else None


NOTIFY_MAX_STALE_DAYS = int(os.getenv("ATTRIBUTION_NOTIFY_MAX_STALE_DAYS", "3"))
# 默认 1 = 只发当天日报，不回放 backlog（避免停机多天后一次性刷屏）。
# 想把停机期间的历史日报补回来，调大到 3 或用 scripts/backfill_notify.py 逐天补发。
NOTIFY_CATCHUP_MAX = int(os.getenv("ATTRIBUTION_NOTIFY_CATCHUP_MAX", "1"))


def expected_notify_pt(today: date | None = None) -> str:
    """日报应该覆盖的分区：昨天。"""
    return ((today or datetime.now().date()) - timedelta(days=1)).strftime("%Y%m%d")


def _pt_age_days(pt: str, anchor: str) -> int | None:
    """pt 落后 anchor(期望分区)的天数；pt 比 anchor 新或格式不对时返回 None。"""
    try:
        target = datetime.strptime(str(pt), "%Y%m%d").date()
        base = datetime.strptime(str(anchor), "%Y%m%d").date()
    except (TypeError, ValueError):
        return None
    return (base - target).days


def _lag_days(pt: str, expected: str) -> int | None:
    """可用于日报的落后天数：0=就是期望分区；None=比期望分区还新/格式不对。"""
    lag = _pt_age_days(pt, expected)
    return lag if lag is not None and lag >= 0 else None


def _upstream_partition_status(service: Any, pt: str) -> bool | None:
    """pt 是否已在上游 MaxCompute 出现；查询失败返回 None(不猜，等着重试)。"""
    try:
        return str(pt) in {str(value) for value in service.refresh_partitions()}
    except Exception:
        return None


def target_notice(plan: dict[str, Any], pt: str) -> str:
    """每个目标分区各自适用的补发提示。

    最新一条用 plan 里的 notice(说明应该覆盖哪个分区)；
    backlog 里的历史分区单独标注，让收件人一眼看出这是补发而不是当天日报。
    """
    targets = [item[0] for item in plan.get("targets") or []]
    if not targets or pt == targets[0]:
        return str(plan.get("notice") or "")
    return f"补发历史分区：`{pt}` 此前未发送（调度停摆或上游延迟导致）。"


def plan_notification(
    *,
    candidates: list[str],
    load_payload,
    ledger: NotificationLedger,
    today: date,
    override: str | None = None,
    catch_up_max: int = NOTIFY_CATCHUP_MAX,
    max_stale_days: int = NOTIFY_MAX_STALE_DAYS,
    allow_catch_up: bool = True,
) -> dict[str, Any]:
    """决定这次日报发哪个分区。

    以前只在 pt == 昨天 时才发：上游某天缺分区、或调度停一天，日报就静默断更
    (10/02~10/07 连续 6 天没发就是这么来的)。现在改成：
      1. 有昨天分区就发昨天(正常路径)；
      2. 没有昨天分区就发"最新且未发过"的昨天及更早快照，正文里带补发提示；
      3. 落后超过 max_stale_days 天就不发，交给缺口巡检告警，
         避免把陈旧数据当日报发出去误导判断。

    pt 晚于昨天的快照(今天/未来，当天数据不完整，由页面按需计算产生)一律不参与，
    否则 14:20 会把半天数据当日报发出去。
    backlog(daemon 停机多天)时一次最多补 catch_up_max 条，防止刷屏。

    allow_catch_up=False 用于"先等等看"的场景：调用方(发送逻辑)会先确认上游到底
    有没有昨天分区，只有确认上游也没有，才允许拿旧快照补发——否则 14:00 计算还在跑、
    或者上游只是晚到的时候，不应该先把前天的日报发出去。

    返回 status: plan / already_sent / waiting / stale / missing_snapshot，
    调用方据此决定发、重试还是跳过。
    """
    expected = expected_notify_pt(today)
    if override:
        pt = str(override).strip()
        payload = load_payload(pt)
        if payload is None:
            return {
                "status": "missing_snapshot",
                "targets": [],
                "notice": "",
                "reason": f"指定分区 pt={pt} 没有可用快照",
            }
        return {"status": "plan", "targets": [(pt, payload)], "notice": "", "reason": ""}

    recorded = ledger.recorded_pts() - ledger.expired_pending_pts()
    eligible = [pt for pt in candidates if _lag_days(pt, expected) is not None]
    usable: list[tuple[str, dict[str, Any]]] = []
    for pt in eligible:
        if pt in recorded:
            continue
        payload = load_payload(pt)
        if payload is not None:
            usable.append((pt, payload))

    if not usable:
        if expected in recorded and ledger.is_sent(expected):
            return {
                "status": "already_sent",
                "targets": [],
                "notice": "",
                "reason": f"pt={expected} 今日已发送",
            }
        return {
            "status": "waiting",
            "targets": [],
            "notice": "",
            "reason": (
                f"pt={expected} 已发布但尚未发送成功，稍后重试"
                if expected in eligible
                else f"没有 pt<={expected} 的可用快照(昨天分区可能尚未发布)"
            ),
        }

    newest_pt, newest_payload = usable[0]
    if newest_pt != expected and not allow_catch_up:
        # 上游分区状态还没确认：等昨天分区发布，不要抢跑发旧数据
        return {
            "status": "waiting",
            "targets": [],
            "notice": "",
            "reason": f"最新可用快照 pt={newest_pt} 还不是期望分区 {expected}，等待昨天分区发布",
        }
    lag = _lag_days(newest_pt, expected)
    if lag is not None and lag > max_stale_days:
        return {
            "status": "stale",
            "targets": [],
            "notice": "",
            "reason": (
                f"最新可用快照 pt={newest_pt} 落后期望分区 {expected} 达 {lag} 天，"
                f"超过补发阈值 {max_stale_days} 天"
            ),
        }

    notice = ""
    if newest_pt != expected:
        notice = (
            f"补发：最新可用数据分区为 `{newest_pt}`，日报应覆盖 `{expected}`。"
            "请关注上游数据缺失或调度停摆。"
        )
    targets = [(newest_pt, newest_payload)] + usable[1 : max(1, int(catch_up_max))]
    return {"status": "plan", "targets": targets, "notice": notice, "reason": ""}


def _notification_report_path(pt: str) -> Path:
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    return report_path_is_safe(DEFAULT_REPORT_DIR, f"credit_attribution_{pt}_{timestamp}.png")


def _fund_notification_report_path(pt: str) -> Path:
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    return fund_report_path_is_safe(DEFAULT_REPORT_DIR, f"{FUND_REPORT_PREFIX}_{pt}_{timestamp}.png")


def _report_image_url(
    public_base: str,
    report_path: Path | None,
    api_prefix: str,
    *,
    thumbnail: Path | None = None,
) -> str | None:
    """Build the DingTalk image link; prefer the JPEG thumbnail over the full PNG."""
    if not public_base or report_path is None:
        return None
    has_thumbnail = thumbnail is not None and Path(thumbnail).is_file()
    suffix = "/thumbnail" if has_thumbnail else ""
    return f"{public_base}/api/{api_prefix}/notification-reports/{report_path.name}{suffix}"


@op(
    description="发送授信归因钉钉日报：优先昨天分区，缺失时补发最新未发送分区",
    retry_policy=RetryPolicy(max_retries=3, delay=20 * 60),
)
def notify_attribution_dingtalk(context, pt: str | None = None) -> dict[str, Any]:
    """pt 为空时自动挑选目标分区；传入 pt 用于上游补数后的指定补发。"""
    return _send_credit_daily(log=context.log, override=pt)


def _send_credit_daily(*, log, override: str | None = None, catch_up: bool = True) -> dict[str, Any]:
    """授信归因日报发送逻辑(op 与补发脚本共用)。"""
    load_local_env()
    ledger = NotificationLedger(NOTIFICATION_LEDGER_PATH)
    expected = expected_notify_pt()
    plan_kwargs = dict(
        candidates=_serving_candidates(SERVING_DIR),
        load_payload=lambda candidate: _load_serving_payload(SERVING_DIR, serving_assemble, candidate),
        ledger=ledger,
        today=datetime.now().date(),
        override=override,
        catch_up_max=NOTIFY_CATCHUP_MAX if catch_up else 1,
    )
    plan = plan_notification(**plan_kwargs, allow_catch_up=False)
    if plan["status"] in {"waiting", "stale"} and not override:
        # 先确认上游到底有没有昨天分区：只是发布延迟就继续等，真没有才补发旧快照。
        if _upstream_partition_status(_service(), expected) is False:
            log.warning(
                "上游没有 pt=%s 分区(不是发布延迟)，改为补发最新可用快照：%s",
                expected,
                plan["reason"],
            )
            plan = plan_notification(**plan_kwargs, allow_catch_up=True)
    if not plan["targets"]:
        if override:
            raise Failure(description=f"授信归因指定分区补发失败：{plan['reason']}")
        if plan["status"] == "already_sent":
            log.info("授信归因日报已发送过，无需重复：%s", plan["reason"])
            return {"status": "already_sent", "pt": expected_notify_pt()}
        log.warning("授信归因暂无可发送日报：%s，20 分钟后重试", plan["reason"])
        raise RetryRequested(seconds_to_wait=20 * 60)

    web_url = os.getenv("ATTRIBUTION_WEB_URL", "").strip()
    public_base = os.getenv("ATTRIBUTION_PUBLIC_BASE_URL", "").strip().rstrip("/")
    s3_notifier = s3_notifier_from_env()
    notifier = DingTalkNotifier()
    results: list[dict[str, Any]] = []

    for target_pt, snapshot in plan["targets"]:
        if not ledger.claim(target_pt):
            if not ledger.is_sent(target_pt):
                log.warning("授信归因 pt=%s 仍有发送中记录，不能视为成功，20 分钟后重试", target_pt)
                raise RetryRequested(seconds_to_wait=20 * 60)
            log.info("pt=%s already sent, skip duplicate notification", target_pt)
            results.append({"status": "already_sent", "pt": target_pt})
            continue

        try:
            payload = _service().with_rule_statuses(snapshot)
            report_path: Path | None = None
            if web_url:
                report_path = _notification_report_path(target_pt)
                try:
                    capture_attribution_page(
                        web_url,
                        os.getenv("ATTRIBUTION_NOTIFY_USERNAME", "").strip(),
                        os.getenv("ATTRIBUTION_NOTIFY_PASSWORD", "").strip(),
                        report_path,
                    )
                except Exception:
                    report_path = None
                    log.exception("生成授信归因完整长截图失败，回退发送文字日报，pt=%s", target_pt)
            else:
                log.warning("未配置 ATTRIBUTION_WEB_URL，回退发送授信归因文字日报，pt=%s", target_pt)

            thumbnail = write_thumbnail(report_path) if report_path is not None else None
            report_url = _report_image_url(
                public_base, report_path, "credit-attribution", thumbnail=thumbnail
            )
            digest = build_digest(payload, report_url=report_url, page_url=web_url)
            notice = target_notice(plan, target_pt)
            if notice:
                digest["notice"] = notice
            markdown = format_markdown(digest)
            if s3_notifier is not None and report_path is not None:
                # 公网对象：钉钉服务端能取图，外网同事也能看到图片本身。
                try:
                    response = publish_public_image_report(
                        s3_notifier,
                        pt=target_pt,
                        image_path=thumbnail or report_path,
                        page_url=web_url,
                        title="授信归因日报",
                        digest=digest,
                        formatter=format_s3_summary_markdown,
                    )
                    delivery_name = response["object_name"]
                except Exception:
                    log.exception("公网图片推送失败，回退本机图片链接，pt=%s", target_pt)
                    response = notifier.send_markdown(markdown)
                    delivery_name = report_path.name
            elif s3_notifier is not None:
                response = s3_notifier.send_markdown(markdown)
                delivery_name = f"credit_attribution_{target_pt}_markdown"
            else:
                response = notifier.send_markdown(markdown)
                delivery_name = (
                    report_path.name if report_path is not None
                    else f"credit_attribution_{target_pt}_markdown"
                )
            ledger.mark_sent(target_pt, delivery_name, expected_pt=expected)
        except Exception:
            ledger.release(target_pt)
            log.exception("发送授信归因钉钉日报失败，pt=%s", target_pt)
            raise

        log.info("授信归因钉钉日报发送成功：pt=%s report=%s", target_pt, report_path or "markdown")
        results.append(
            {
                "status": "sent",
                "pt": target_pt,
                "report_path": str(report_path) if report_path else None,
                "response": response,
            }
        )

    return {
        "status": "sent",
        "pt": results[0]["pt"],
        "notice": plan["notice"],
        "results": results,
    }


@op(
    description="发送资金归集钉钉日报：优先昨天分区，缺失时补发最新未发送分区",
    retry_policy=RetryPolicy(max_retries=3, delay=20 * 60),
)
def notify_fund_dingtalk(context, pt: str | None = None) -> dict[str, Any]:
    """pt 为空时自动挑选目标分区；传入 pt 用于上游补数后的指定补发。"""
    return _send_fund_daily(log=context.log, override=pt)


def _send_fund_daily(*, log, override: str | None = None, catch_up: bool = True) -> dict[str, Any]:
    """资金归集日报发送逻辑(op 与补发脚本共用)。"""
    load_local_env()
    ledger = NotificationLedger(FUND_NOTIFICATION_LEDGER_PATH)
    expected = expected_notify_pt()
    plan_kwargs = dict(
        candidates=_serving_candidates(FUND_SERVING_DIR),
        load_payload=lambda candidate: _load_serving_payload(
            FUND_SERVING_DIR, fund_serving_assemble, candidate
        ),
        ledger=ledger,
        today=datetime.now().date(),
        override=override,
        catch_up_max=NOTIFY_CATCHUP_MAX if catch_up else 1,
    )
    plan = plan_notification(**plan_kwargs, allow_catch_up=False)
    if plan["status"] in {"waiting", "stale"} and not override:
        if _upstream_partition_status(FundAttributionService(), expected) is False:
            log.warning(
                "资金归集上游没有 pt=%s 分区(不是发布延迟)，改为补发最新可用快照：%s",
                expected,
                plan["reason"],
            )
            plan = plan_notification(**plan_kwargs, allow_catch_up=True)
    if not plan["targets"]:
        if override:
            raise Failure(description=f"资金归集指定分区补发失败：{plan['reason']}")
        if plan["status"] == "already_sent":
            log.info("资金归集日报已发送过，无需重复：%s", plan["reason"])
            return {"status": "already_sent", "pt": expected_notify_pt()}
        log.warning("资金归集暂无可发送日报：%s，20 分钟后重试", plan["reason"])
        raise RetryRequested(seconds_to_wait=20 * 60)

    s3_notifier = s3_notifier_from_env(
        filename_prefix=FUND_REPORT_PREFIX,
        object_prefix=os.getenv("DINGTALK_S3_FUND_PREFIX"),
    )
    notifier = DingTalkNotifier()
    results: list[dict[str, Any]] = []

    for target_pt, snapshot in plan["targets"]:
        if not ledger.claim(target_pt):
            if not ledger.is_sent(target_pt):
                log.warning("资金归集 pt=%s 仍有发送中记录，不能视为成功，20 分钟后重试", target_pt)
                raise RetryRequested(seconds_to_wait=20 * 60)
            log.info("fund pt=%s already sent, skip duplicate notification", target_pt)
            results.append({"status": "already_sent", "pt": target_pt})
            continue

        try:
            service = FundAttributionService()
            payload = attach_tracked_only_rules(
                service.with_rule_statuses(snapshot), service.active_tracked_rules()
            )
            page_url = os.getenv("ATTRIBUTION_FUND_WEB_URL", "").strip() or None
            public_base = os.getenv("ATTRIBUTION_PUBLIC_BASE_URL", "").strip().rstrip("/")
            report_path: Path | None = None
            if page_url:
                report_path = _fund_notification_report_path(target_pt)
                try:
                    capture_fund_page(
                        page_url,
                        os.getenv("ATTRIBUTION_NOTIFY_USERNAME", "").strip(),
                        os.getenv("ATTRIBUTION_NOTIFY_PASSWORD", "").strip(),
                        report_path,
                    )
                except Exception:
                    report_path = None
                    log.exception("生成资金归集完整长截图失败，回退发送文字日报，pt=%s", target_pt)
            else:
                log.warning(
                    "未配置 ATTRIBUTION_FUND_WEB_URL，资金归集日报只发送文字摘要，pt=%s",
                    target_pt,
                )

            thumbnail = write_thumbnail(report_path) if report_path is not None else None
            report_url = _report_image_url(
                public_base, report_path, "fund-attribution", thumbnail=thumbnail
            )
            digest = build_fund_digest(payload, report_url=report_url, page_url=page_url)
            notice = target_notice(plan, target_pt)
            if notice:
                digest["notice"] = notice
            markdown = format_fund_markdown(digest)
            if s3_notifier is not None and report_path is not None:
                # 公网对象：钉钉服务端能取图，外网同事也能看到图片本身。
                try:
                    response = publish_public_image_report(
                        s3_notifier,
                        pt=target_pt,
                        image_path=thumbnail or report_path,
                        page_url=page_url,
                        title="资金归集日报",
                        digest=digest,
                        formatter=format_s3_fund_summary_markdown,
                    )
                    delivery_name = response["object_name"]
                except Exception:
                    log.exception("公网图片推送失败，回退本机图片链接，pt=%s", target_pt)
                    response = notifier.send_markdown(markdown, title="资金归集日报")
                    delivery_name = report_path.name
            else:
                response = notifier.send_markdown(markdown, title="资金归集日报")
                delivery_name = (
                    report_path.name if report_path is not None
                    else f"fund_attribution_{target_pt}_markdown"
                )
            ledger.mark_sent(target_pt, delivery_name, expected_pt=expected)
        except Exception:
            ledger.release(target_pt)
            log.exception("发送资金归集钉钉日报失败，pt=%s", target_pt)
            raise

        log.info("资金归集钉钉日报发送成功：pt=%s", target_pt)
        results.append({"status": "sent", "pt": target_pt, "response": response})

    return {
        "status": "sent",
        "pt": results[0]["pt"],
        "notice": plan["notice"],
        "results": results,
    }


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
    default_status=DefaultScheduleStatus.STOPPED,
)


fund_schedule = ScheduleDefinition(
    job=daily_fund_attribution_job,
    cron_schedule="00 14 * * *",  # 每天 14:00,检查昨天分区后再发布
    execution_timezone="Asia/Shanghai",
    name="daily_fund_attribution_1400",
    default_status=DefaultScheduleStatus.STOPPED,
)


dingtalk_schedule = ScheduleDefinition(
    job=daily_attribution_dingtalk_job,
    cron_schedule="20 14 * * *",
    execution_timezone="Asia/Shanghai",
    name="daily_attribution_dingtalk_1420",
    default_status=DefaultScheduleStatus.STOPPED,
)


fund_dingtalk_schedule = ScheduleDefinition(
    job=daily_fund_attribution_dingtalk_job,
    cron_schedule="20 14 * * *",
    execution_timezone="Asia/Shanghai",
    name="daily_fund_attribution_dingtalk_1420",
    default_status=DefaultScheduleStatus.STOPPED,
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
