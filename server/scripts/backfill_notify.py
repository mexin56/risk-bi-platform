#!/usr/bin/env python
"""指定分区的补发：上游补数后把某一天的归因算出来并补发日报。

场景：上游某个 pt 分区缺失(例如 20261007)，平台侧算不出来；等数仓把分区补上之后，
一条命令把"计算 + 发布 + 钉钉日报"补齐：

    python server/scripts/backfill_notify.py --pt 20261007
    python server/scripts/backfill_notify.py --pt 20261007 --skip-compute   # 只补发日报
    python server/scripts/backfill_notify.py --pt 20261007 --credit-only     # 只补授信归因

行为：
  1. 先校验 pt 是否已在 MaxCompute 出现；没有就直接退出(不做无谓计算)；
  2. 若本地 serving 里还没有该分区的快照，跑一次 compute_and_publish；
  3. 调用和调度完全相同的发送函数补发，台账按 pt 去重，重复执行不会重发。

发送前检查（不会计算、占用发送台账或发送消息）：
    python server/scripts/backfill_notify.py --pt 20261010 --check-only
"""

from __future__ import annotations

import argparse
import sys
from datetime import datetime
from pathlib import Path

SERVER_DIR = Path(__file__).resolve().parent.parent
if str(SERVER_DIR) not in sys.path:
    sys.path.insert(0, str(SERVER_DIR))

from app import load_local_env  # noqa: E402
from attribution_notification import DingTalkNotifier, NotificationLedger, s3_notifier_from_env  # noqa: E402
from fund_service import FundAttributionService, _run_sql_rows  # noqa: E402
from fund_pipeline.cli import compute_and_publish as compute_and_publish_fund  # noqa: E402
from pipeline.dagster_defs import (  # noqa: E402
    FUND_NOTIFICATION_LEDGER_PATH,
    FUND_SERVING_DIR,
    NOTIFICATION_LEDGER_PATH,
    SERVING_DIR,
    _load_serving_payload,
    _service,
    _serving_candidates,
    _send_credit_daily,
    _send_fund_daily,
)
from pipeline.cli import compute_and_publish  # noqa: E402
from fund_pipeline import assemble as fund_serving_assemble  # noqa: E402
from pipeline import assemble as serving_assemble  # noqa: E402


class _PrintLogger:
    """把 %s 占位的 dagster 日志格式转成 stdout，脚本与 op 共用发送逻辑。"""

    def info(self, message, *args):
        print(f"[backfill] {message % args if args else message}")

    warning = info

    def exception(self, message, *args, **kwargs):
        print(f"[backfill][error] {message % args if args else message}", file=sys.stderr)


def has_partition(service, pt: str) -> bool:
    try:
        return str(pt) in {str(value) for value in service.refresh_partitions()}
    except Exception as exc:
        print(f"[backfill] 分区校验失败: {exc}", file=sys.stderr)
        return False


def ensure_credit_snapshot(pt: str, *, skip_compute: bool) -> None:
    if _load_serving_payload(SERVING_DIR, serving_assemble, pt) is not None:
        print(f"[backfill] 授信归因快照已存在，跳过计算 pt={pt}")
        return
    if skip_compute:
        raise SystemExit(f"[backfill] --skip-compute 但本地没有 pt={pt} 的授信归因快照")
    service = _service()
    if not has_partition(service, pt):
        raise SystemExit(f"[backfill] 上游还没有 pt={pt} 分区，无法计算；请先找数仓补数")
    stats = compute_and_publish(service, _credit_config(), pt, 0, source="backfill")
    print(f"[backfill] 授信归因计算完成 pt={pt} stats={stats}")


def ensure_fund_snapshot(pt: str, *, skip_compute: bool) -> None:
    if _load_serving_payload(FUND_SERVING_DIR, fund_serving_assemble, pt) is not None:
        print(f"[backfill] 资金归集快照已存在，跳过计算 pt={pt}")
        return
    if skip_compute:
        raise SystemExit(f"[backfill] --skip-compute 但本地没有 pt={pt} 的资金归集快照")
    service = FundAttributionService()
    if not has_partition(service, pt):
        raise SystemExit(f"[backfill] 上游还没有 pt={pt} 分区，无法计算；请先找数仓补数")
    stats = compute_and_publish_fund(
        config=service.config,
        table=service.table_name,
        partition=pt,
        offset=0,
        query_rows=_run_sql_rows,
        source="backfill",
    )
    print(f"[backfill] 资金归集计算完成 pt={pt} stats={stats}")


def _credit_config() -> dict:
    from app import load_config

    return load_config()


def check_delivery_readiness(pt: str, *, credit: bool, fund: bool) -> None:
    """Read published snapshots and configuration without claiming or sending."""
    notifier = DingTalkNotifier()
    image_adapter = s3_notifier_from_env()
    print(f"[check] notification target={notifier.target_env}; credentials configured; "
          f"public image adapter={'configured' if image_adapter is not None else 'not configured'}")
    sources = []
    if credit:
        sources.append(('授信归因', NOTIFICATION_LEDGER_PATH, SERVING_DIR, serving_assemble))
    if fund:
        sources.append(('资金归集', FUND_NOTIFICATION_LEDGER_PATH, FUND_SERVING_DIR, fund_serving_assemble))
    for name, ledger_path, serving_dir, assemble in sources:
        ledger = NotificationLedger(ledger_path, initialize=False)
        if ledger.is_sent(pt):
            print(f"[check] {name} pt={pt} 已发送成功，重复运行将跳过")
            continue
        expired = ledger.expired_pending_pts()
        if pt in ledger.pending_pts() and pt not in expired:
            raise RuntimeError(f'{name} pt={pt} 存在发送中记录，尚未确认成功')
        if pt in expired:
            print(f"[check] {name} pt={pt} 有过期发送占用，正常发送时可重新认领")
        payload = _load_serving_payload(serving_dir, assemble, pt)
        if payload is None:
            raise RuntimeError(f'{name} pt={pt} 缺少已发布业务快照')
        print(f"[check] {name} pt={pt} 快照可读取；未发送，无发送中占用；可进入发送阶段")


def require_delivery(ledger: NotificationLedger, pt: str) -> None:
    if not ledger.is_sent(pt):
        raise RuntimeError(f'pt={pt} 没有成功发送记录；本次任务不能标记成功')


def main() -> int:
    parser = argparse.ArgumentParser(description="指定分区的归因计算与日报补发")
    parser.add_argument("--pt", required=True, help="要补的分区，如 20261007")
    parser.add_argument("--skip-compute", action="store_true", help="只用现有快照补发，不重算")
    parser.add_argument("--credit-only", action="store_true", help="只补授信归因")
    parser.add_argument("--fund-only", action="store_true", help="只补资金归集")
    parser.add_argument("--check-only", action="store_true", help="只检查已发布快照与发送配置，不计算或发送")
    args = parser.parse_args()

    if args.credit_only and args.fund_only:
        raise SystemExit("[backfill] --credit-only 与 --fund-only 不能同时使用")

    pt = args.pt.strip()
    if len(pt) != 8 or not pt.isdigit():
        raise SystemExit('pt 必须为 YYYYMMDD 日期')
    datetime.strptime(pt, '%Y%m%d')
    load_local_env()
    if args.check_only:
        check_delivery_readiness(pt, credit=not args.fund_only, fund=not args.credit_only)
        return 0
    log = _PrintLogger()
    print(f"[backfill] 开始补发 pt={pt} 时间={datetime.now().isoformat(timespec='seconds')}")

    if not args.fund_only:
        credit_ledger = NotificationLedger(NOTIFICATION_LEDGER_PATH)
        if credit_ledger.is_sent(pt):
            print(f"[backfill] 授信归因 pt={pt} 已发送成功，跳过")
        else:
            ensure_credit_snapshot(pt, skip_compute=args.skip_compute)
            result = _send_credit_daily(log=log, override=pt)
            require_delivery(credit_ledger, pt)
            print(f"[backfill] 授信归因补发结果: {result}")

    if not args.credit_only:
        fund_ledger = NotificationLedger(FUND_NOTIFICATION_LEDGER_PATH)
        if fund_ledger.is_sent(pt):
            print(f"[backfill] 资金归集 pt={pt} 已发送成功，跳过")
        else:
            ensure_fund_snapshot(pt, skip_compute=args.skip_compute)
            result = _send_fund_daily(log=log, override=pt)
            require_delivery(fund_ledger, pt)
            print(f"[backfill] 资金归集补发结果: {result}")

    print(f"[backfill] 完成 pt={pt} 时间={datetime.now().isoformat(timespec='seconds')}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
