"""日报可靠性改造的回归测试。

覆盖三件事：
  1. 上游缺分区 / 调度停机时，日报不再静默断更（plan_notification 自愈选择 + 补发提示）；
  2. 发送台账可以被巡检脚本只读查询（recorded/latest_sent/pending）；
  3. 守护配置到位：dagster 有 webserver 探针、15:00 缺口巡检 timer 已随仓库交付。
"""

from datetime import date
from pathlib import Path

import pytest

from attribution_notification import (
    CREDIT_TITLE,
    FUND_TITLE,
    NotificationLedger,
    format_markdown,
)
from pipeline.dagster_defs import (
    _upstream_partition_status,
    expected_notify_pt,
    plan_notification,
    target_notice,
)
from scripts.notify_watchdog import build_alert_markdown

SERVER_DIR = Path(__file__).resolve().parent
REPO_ROOT = SERVER_DIR.parent

TODAY = date(2026, 10, 10)
YESTERDAY = "20261009"  # expected_notify_pt(TODAY)


def _ledger(tmp_path: Path, *pts: str) -> NotificationLedger:
    ledger = NotificationLedger(tmp_path / "ledger.sqlite3")
    for pt in pts:
        ledger.claim(pt)
        ledger.mark_sent(pt, f"{pt}.png")
    return ledger


def _payload_loader(available: set[str]):
    def load(pt: str):
        return {"pt": pt} if pt in available else None

    return load


def test_expected_notify_pt_is_yesterday():
    assert expected_notify_pt(TODAY) == YESTERDAY


def test_plan_sends_yesterday_when_snapshot_available(tmp_path):
    plan = plan_notification(
        candidates=[YESTERDAY, "20261008"],
        load_payload=_payload_loader({YESTERDAY, "20261008"}),
        ledger=_ledger(tmp_path, "20261008"),
        today=TODAY,
    )
    assert plan["status"] == "plan"
    assert [pt for pt, _ in plan["targets"]] == [YESTERDAY]
    assert plan["notice"] == ""


def test_plan_ignores_snapshot_newer_than_yesterday(tmp_path):
    """当天按需计算的半天快照不能当日报发出去。"""
    plan = plan_notification(
        candidates=["20261010", YESTERDAY],
        load_payload=_payload_loader({"20261010", YESTERDAY}),
        ledger=_ledger(tmp_path),
        today=TODAY,
    )
    assert [pt for pt, _ in plan["targets"]] == [YESTERDAY]


def test_plan_reports_already_sent_instead_of_retrying(tmp_path):
    plan = plan_notification(
        candidates=[YESTERDAY],
        load_payload=_payload_loader({YESTERDAY}),
        ledger=_ledger(tmp_path, YESTERDAY),
        today=TODAY,
    )
    assert plan["status"] == "already_sent"
    assert plan["targets"] == []


def test_plan_waits_when_no_snapshot_published_at_all(tmp_path):
    """连旧快照都没有(14:00 计算还没跑完/全挂了)：等待而不是发空气。"""
    plan = plan_notification(
        candidates=[],
        load_payload=_payload_loader(set()),
        ledger=_ledger(tmp_path),
        today=TODAY,
    )
    assert plan["status"] == "waiting"
    assert plan["targets"] == []


def test_plan_waits_when_yesterday_snapshot_exists_but_send_failed(tmp_path):
    plan = plan_notification(
        candidates=[YESTERDAY],
        load_payload=_payload_loader(set()),  # 快照文件损坏/读不出来
        ledger=_ledger(tmp_path),
        today=TODAY,
    )
    assert plan["status"] == "waiting"
    assert plan["targets"] == []


def test_plan_falls_back_to_catch_up_with_notice(tmp_path):
    """上游缺了昨天分区：发最新的旧快照，并在正文里标注这是补发。"""
    plan = plan_notification(
        candidates=["20261008", "20261006"],
        load_payload=_payload_loader({"20261008", "20261006"}),
        ledger=_ledger(tmp_path),
        today=TODAY,
        catch_up_max=1,
    )
    assert plan["status"] == "plan"
    assert [pt for pt, _ in plan["targets"]] == ["20261008"]
    assert "补发" in plan["notice"]
    assert YESTERDAY in plan["notice"]


def test_plan_caps_backlog_burst(tmp_path):
    plan = plan_notification(
        candidates=[YESTERDAY, "20261008", "20261007", "20261006", "20261005"],
        load_payload=_payload_loader({"20261008", "20261007", "20261006", "20261005", YESTERDAY}),
        ledger=_ledger(tmp_path),
        today=TODAY,
        catch_up_max=3,
    )
    assert [pt for pt, _ in plan["targets"]] == [YESTERDAY, "20261008", "20261007"]


def test_plan_refuses_to_send_stale_snapshot(tmp_path):
    plan = plan_notification(
        candidates=["20260930"],
        load_payload=_payload_loader({"20260930"}),
        ledger=_ledger(tmp_path),
        today=TODAY,
        max_stale_days=3,
    )
    assert plan["status"] == "stale"
    assert plan["targets"] == []
    assert "补发阈值" in plan["reason"]


def test_plan_override_targets_explicit_partition(tmp_path):
    plan = plan_notification(
        candidates=[YESTERDAY],
        load_payload=_payload_loader({YESTERDAY, "20261007"}),
        ledger=_ledger(tmp_path),
        today=TODAY,
        override="20261007",
    )
    assert plan["status"] == "plan"
    assert [pt for pt, _ in plan["targets"]] == ["20261007"]


def test_plan_override_reports_missing_snapshot(tmp_path):
    plan = plan_notification(
        candidates=[YESTERDAY],
        load_payload=_payload_loader({YESTERDAY}),
        ledger=_ledger(tmp_path),
        today=TODAY,
        override="20261007",
    )
    assert plan["status"] == "missing_snapshot"
    assert plan["targets"] == []


def test_ledger_exposes_recorded_and_pending_state(tmp_path):
    ledger = NotificationLedger(tmp_path / "ledger.sqlite3")
    assert ledger.recorded_pts() == set()
    assert ledger.latest_sent_pt() is None
    ledger.claim("20261008")
    ledger.mark_sent("20261008", "credit.png")
    ledger.claim("20261009")  # 模拟发送中断
    assert ledger.recorded_pts() == {"20261008", "20261009"}
    assert ledger.latest_sent_pt() == "20261008"
    assert ledger.pending_pts() == ["20261009"]


def test_markdown_renders_catch_up_notice():
    digest = {
        "partition": "20261008",
        "risk_points": ["Level3 红色 1 条"],
        "notice": f"补发：最新可用数据分区为 `20261008`，日报应覆盖 `{YESTERDAY}`。",
    }
    text = format_markdown(digest)
    assert "⚠️" in text
    assert "补发" in text
    assert text.index("数据分区") < text.index("⚠️")


def test_plan_refuses_catch_up_when_upstream_state_unknown(tmp_path):
    """上游分区状态没确认前不能抢跑发旧数据(14:00 可能还在算)。"""
    plan = plan_notification(
        candidates=["20261008"],
        load_payload=_payload_loader({"20261008"}),
        ledger=_ledger(tmp_path),
        today=TODAY,
        allow_catch_up=False,
    )
    assert plan["status"] == "waiting"
    assert plan["targets"] == []


def test_plan_allows_catch_up_when_upstream_really_lacks_the_day(tmp_path):
    plan = plan_notification(
        candidates=["20261008"],
        load_payload=_payload_loader({"20261008"}),
        ledger=_ledger(tmp_path),
        today=TODAY,
        allow_catch_up=True,
    )
    assert plan["status"] == "plan"
    assert [pt for pt, _ in plan["targets"]] == ["20261008"]
    assert "补发" in plan["notice"]


def test_upstream_partition_status_does_not_guess_on_error():
    class Broken:
        def refresh_partitions(self):
            raise RuntimeError("odps timeout")

    assert _upstream_partition_status(Broken(), "20261009") is None


def test_upstream_partition_status_reads_partition_list():
    class Fake:
        def refresh_partitions(self):
            return ["20261009", "20261008"]

    assert _upstream_partition_status(Fake(), "20261009") is True
    assert _upstream_partition_status(Fake(), "20261007") is False


def test_target_notice_labels_backlog_messages(tmp_path):
    plan = plan_notification(
        candidates=[YESTERDAY, "20261008"],
        load_payload=_payload_loader({YESTERDAY, "20261008"}),
        ledger=_ledger(tmp_path),
        today=TODAY,
        catch_up_max=3,
    )
    assert target_notice(plan, YESTERDAY) == ""
    assert "补发历史分区" in target_notice(plan, "20261008")
    assert "20261008" in target_notice(plan, "20261008")


def test_watchdog_inspect_flags_missing_reports(tmp_path):
    import scripts.notify_watchdog as watchdog

    ledger_path = tmp_path / "credit.sqlite3"
    _ledger(tmp_path, "20261008")
    report = watchdog.inspect(CREDIT_TITLE, ledger_path)
    assert report["missing"] is True
    assert report["expected"] == YESTERDAY

    ledger_path.write_bytes(ledger_path.read_bytes())  # 保持文件存在
    sent_ledger = tmp_path / "sent.sqlite3"
    ledger = NotificationLedger(sent_ledger)
    ledger.claim(YESTERDAY)
    ledger.mark_sent(YESTERDAY, "credit.png")
    assert watchdog.inspect(CREDIT_TITLE, sent_ledger)["missing"] is False


def test_ledger_records_which_day_a_message_covers(tmp_path):
    ledger = NotificationLedger(tmp_path / "ledger.sqlite3")
    ledger.claim("20261006")
    ledger.mark_sent("20261006", "fund.png", expected_pt="20261009")
    assert ledger.covered_expected_pts() == {"20261009"}
    assert ledger.latest_sent_pt() == "20261006"


def test_ledger_upgrades_legacy_table_without_expected_column(tmp_path):
    import sqlite3

    path = tmp_path / "legacy.sqlite3"
    with sqlite3.connect(path) as connection:
        connection.execute(
            """
            CREATE TABLE attribution_dingtalk_notification (
                pt TEXT PRIMARY KEY, status TEXT NOT NULL, claimed_at TEXT NOT NULL,
                sent_at TEXT, report_name TEXT
            )
            """
        )
        connection.execute(
            "INSERT INTO attribution_dingtalk_notification VALUES ('20261008','sent','t','t','x.png')"
        )
    ledger = NotificationLedger(path)
    assert ledger.latest_sent_pt() == "20261008"  # 老数据不丢
    assert ledger.covered_expected_pts() == set()


def test_watchdog_does_not_realert_after_a_catch_up_send(tmp_path):
    import scripts.notify_watchdog as watchdog

    ledger_path = tmp_path / "catchup.sqlite3"
    ledger = NotificationLedger(ledger_path)
    ledger.claim("20261006")
    ledger.mark_sent("20261006", "credit.png", expected_pt=watchdog.expected_pt())
    report = watchdog.inspect(CREDIT_TITLE, ledger_path)
    assert report["missing"] is False


def test_watchdog_alert_markdown_lists_both_reports(tmp_path):
    import scripts.notify_watchdog as watchdog

    reports = [
        watchdog.inspect(CREDIT_TITLE, tmp_path / "a.sqlite3"),
        watchdog.inspect(FUND_TITLE, tmp_path / "b.sqlite3"),
    ]
    text = build_alert_markdown(reports)
    assert CREDIT_TITLE in text and FUND_TITLE in text
    assert "无记录" in text


def test_watchdog_run_check_only_reports_gap(tmp_path, monkeypatch, capsys):
    import scripts.notify_watchdog as watchdog

    stale = tmp_path / "stale.sqlite3"
    _ledger(tmp_path, "20261008")
    empty = tmp_path / "empty.sqlite3"
    NotificationLedger(empty)
    monkeypatch.setattr(
        watchdog, "LEDGER_PATHS", {CREDIT_TITLE: stale, FUND_TITLE: empty}
    )
    assert watchdog.run(check_only=True) == 2
    assert "缺失" in capsys.readouterr().out


def test_watchdog_run_is_silent_when_ledger_is_current(tmp_path, monkeypatch, capsys):
    import scripts.notify_watchdog as watchdog

    sent = tmp_path / "sent.sqlite3"
    ledger = NotificationLedger(sent)
    ledger.claim(YESTERDAY)
    ledger.mark_sent(YESTERDAY, "credit.png")
    monkeypatch.setattr(watchdog, "LEDGER_PATHS", {CREDIT_TITLE: sent})
    assert watchdog.run(check_only=True) == 0
    assert "正常" in capsys.readouterr().out


@pytest.mark.parametrize(
    "relative, needle",
    [
        ("deploy/systemd/risk-bi-dagster-webserver.service", "dagster-webserver -h 127.0.0.1 -p 3001"),
        ("deploy/systemd/risk-bi-notify-watchdog.service", "scripts/notify_watchdog.py"),
        ("deploy/systemd/risk-bi-notify-watchdog.timer", "OnCalendar=*-*-* 15:00:00"),
        ("deploy/systemd/risk-bi-notify-watchdog.timer", "Persistent=true"),
    ],
)
def test_deploy_units_are_shipped(relative, needle):
    assert needle in (REPO_ROOT / relative).read_text(encoding="utf-8")


def test_watchdog_recovery_is_wired_into_healthcheck_script():
    script = Path("/usr/local/bin/service-healthcheck.sh")
    if not script.exists():  # 非部署机(开发/CI)跳过
        pytest.skip("service-healthcheck.sh 只存在于部署机")
    text = script.read_text(encoding="utf-8")
    assert "risk-bi-dagster|active://risk-bi-dagster" in text
    assert "risk-bi-dagster-webserver|http://127.0.0.1:3001/server_info" in text