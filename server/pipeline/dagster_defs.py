"""授信归因夜间调度(Dagster)。

上游 MaxCompute 数据每日 09:00 前产出;本作业 09:30(Asia/Shanghai)执行:

    resolve_target_partition  # 校验最新 pt 就绪(未就绪自动重试,最多 3 次×20min)
        └→ publish_attribution  # 复用 pipeline.cli.compute_and_publish
                                 # (MaxCompute 聚合 + 路径趋势批量预计算 + DuckDB/快照发布)

组件:
- job:     nightly_attribution_job(in-process 执行,Windows 规避 spawn 兼容问题)
- schedule: nightly_attribution_0930(cron "30 9 * * *")
- sensor:  nightly_attribution_failure_sensor(失败告警钩子,当前仅记 ERROR 日志)

本地校验(在 server/ 目录):
    dagster job execute --python-module pipeline.dagster_defs   # 立即跑一次
    dagster schedule list --python-module pipeline.dagster_defs # 查看下次触发时间

启动守护进程见 scripts/start_dagster.ps1(daemon + webserver,UI: 127.0.0.1:3001)。
"""

# 注意: 本模块不能加 from __future__ import annotations ——
# 字符串化注解会让 dagster 的 context 类型校验失败(DagsterInvalidDefinitionError)
import sys
from datetime import datetime, timedelta
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
from pipeline.cli import compute_and_publish  # noqa: E402


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
    yesterday = int((now - timedelta(days=1)).strftime("%Y%m%d"))
    latest_num = int(latest)

    if latest_num < yesterday:
        context.log.warning(f"最新分区 {latest} 落后超过一天(今天 {today}),等待上游...")
        raise RetryRequested(
            max_retries=3,
            seconds_to_wait=20 * 60,
            description=f"latest pt={latest} 落后超过一天",
        )
    if latest_num < today:
        context.log.warning(f"今日分区尚未出现,fallback 使用最新分区 {latest}")
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


nightly_schedule = ScheduleDefinition(
    job=nightly_attribution_job,
    cron_schedule="30 9 * * *",  # 每天 09:30,上游 09:00 出数之后
    execution_timezone="Asia/Shanghai",
    name="nightly_attribution_0930",
)


@run_status_sensor(
    run_status=DagsterRunStatus.FAILURE,
    monitored_jobs=[nightly_attribution_job],
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
    jobs=[nightly_attribution_job],
    schedules=[nightly_schedule],
    sensors=[nightly_attribution_failure_sensor],
)
