#!/usr/bin/env python
"""日报缺口巡检：授信归因 / 资金归集钉钉日报没发出来时，主动发告警到同一个群。

背景：10/02~10/07 连续 6 天日报没发，没有任何告警，是靠人工发现"群里没消息"。
现在两个层级都补上：
  1) 调度侧：notify op 会补发"最新未发送"的昨天及更早快照（见 pipeline/dagster_defs.plan_notification）；
  2) 巡检侧：本脚本每天 15:00 查一次发送台账，发现缺口就自己发钉钉告警。

判定口径（避免误报）：
  - 期望分区 = 昨天。台账里没有覆盖该分区的记录(也没更新的已发 pt) → 缺失。
  - 上游缺分区后已经发过补发消息时台账会记 expected_pt，不重复告警
    (补发消息正文里的 ⚠️ 已经提示了)。
  - 期望分区还没到 15:00 且台账为空/很旧 → 报"缺失"，因为日报本来就该 14:20 发。
  - 只在 --check-only 下用退出码表达结果(0 正常 / 2 有缺口 / 3 巡检自身出错)，
    正常发告警时退出码 0(告警已送达)，避免 systemd 把"告警成功"记成失败。

用法：
    python server/scripts/notify_watchdog.py              # 检查并按需发告警
    python server/scripts/notify_watchdog.py --check-only # 只检查，不发消息
"""

from __future__ import annotations

import argparse
import os
import sys
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

SERVER_DIR = Path(__file__).resolve().parent.parent
if str(SERVER_DIR) not in sys.path:
    sys.path.insert(0, str(SERVER_DIR))

from app import load_local_env  # noqa: E402
from attribution_notification import (  # noqa: E402
    CREDIT_TITLE,
    FUND_TITLE,
    DingTalkNotifier,
    NotificationLedger,
)

LEDGER_PATHS = {
    CREDIT_TITLE: SERVER_DIR / "data" / "attribution_dingtalk_notifications.sqlite3",
    FUND_TITLE: SERVER_DIR / "data" / "fund_attribution_dingtalk_notifications.sqlite3",
}
ALERT_TITLE = "归因日报缺失告警"
# 14:20 才是日报发送时间，15:00 巡检时"昨天"必然已经该发了；留 0 天余量。
EXPECTED_LAG_DAYS = int(os.getenv("NOTIFY_WATCHDOG_LAG_DAYS", "0"))


def expected_pt(now: datetime | None = None) -> str:
    reference = now or datetime.now()
    return (reference.date() - timedelta(days=EXPECTED_LAG_DAYS) - timedelta(days=1)).strftime("%Y%m%d")


def inspect(title: str, ledger_path: Path) -> dict[str, Any]:
    """判断某一份日报今天算不算已送达。

    两种口径取"或"：
      1. 台账里显式记了 expected_pt = 昨天（正常发送或补发都算送达）；
      2. 兼容老台账：最近成功发送的 pt >= 昨天。
    这样"上游缺分区后发过补发消息"不会天天重复告警，而真没发出来一定会报。
    """
    ledger = NotificationLedger(ledger_path)
    latest_sent = ledger.latest_sent_pt()
    pending = ledger.pending_pts()
    expected = expected_pt()
    covered = expected in ledger.covered_expected_pts() or bool(
        latest_sent and str(latest_sent) >= expected
    )
    return {
        "title": title,
        "expected": expected,
        "latest_sent": latest_sent,
        "pending": pending,
        "covered": covered,
        "missing": not covered,
    }


def _pt_delta_days(latest_sent: str | None, expected: str) -> int | None:
    if not latest_sent:
        return None
    try:
        return (
            datetime.strptime(expected, "%Y%m%d") - datetime.strptime(str(latest_sent), "%Y%m%d")
        ).days
    except (TypeError, ValueError):
        return None


def build_alert_markdown(reports: list[dict[str, Any]]) -> str:
    lines = [
        f"# {ALERT_TITLE}",
        "",
        f"巡检时间：`{datetime.now().strftime('%Y-%m-%d %H:%M')}`　期望日报分区：`{reports[0]['expected']}`",
        "",
    ]
    for index, report in enumerate(reports, start=1):
        latest = report["latest_sent"] or "无记录"
        delta = _pt_delta_days(report["latest_sent"], report["expected"])
        lag_text = f"，落后 {delta} 天" if delta else ""
        pending_text = f"，残留 pending：{', '.join(report['pending'])}" if report["pending"] else ""
        lines.append(f"{index}. {report['title']}：最近成功 `{latest}`{lag_text}{pending_text}")
    lines.extend(
        [
            "",
            "可能原因：上游分区缺失 / dagster-daemon 未运行 / 截图或钉钉接口报错。",
            "自查：`systemctl status risk-bi-dagster`、`journalctl -u risk-bi-dagster -n 200`；",
            "补发：`python server/scripts/backfill_notify.py --pt <分区>`。",
        ]
    )
    return "\n".join(lines)


def run(*, check_only: bool = False) -> int:
    load_local_env()
    reports = [inspect(title, path) for title, path in LEDGER_PATHS.items()]
    missing = [report for report in reports if report["missing"]]
    for report in reports:
        state = "缺失" if report["missing"] else "正常"
        print(
            f"[watchdog] {report['title']}: {state} "
            f"(期望 pt={report['expected']}, 最近成功 pt={report['latest_sent'] or '无'})"
        )
    if not missing:
        return 0
    markdown = build_alert_markdown(reports)
    if check_only:
        print(markdown)
        return 2
    try:
        response = DingTalkNotifier().send_markdown(markdown, title=ALERT_TITLE)
    except Exception as exc:  # 告警发不出去是最糟的情况，必须留在 journal 里
        print(f"[watchdog] 告警发送失败: {exc}", file=sys.stderr)
        return 3
    print(f"[watchdog] 缺失告警已发送: {response}")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="授信归因/资金归集日报缺口巡检")
    parser.add_argument(
        "--check-only",
        action="store_true",
        help="只检查并发退出码，不发送钉钉消息(0 正常 / 2 有缺口)",
    )
    args = parser.parse_args()
    return run(check_only=args.check_only)


if __name__ == "__main__":
    raise SystemExit(main())