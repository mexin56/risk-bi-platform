from pathlib import Path

from attribution_notification import NotificationLedger


def test_notification_ledger_claims_a_pt_once(tmp_path: Path):
    ledger = NotificationLedger(tmp_path / "ledger.sqlite3")
    assert ledger.claim("20260901") is True
    assert ledger.claim("20260901") is False


def test_notification_ledger_releases_failed_claim(tmp_path: Path):
    ledger = NotificationLedger(tmp_path / "ledger.sqlite3")
    assert ledger.claim("20260901") is True
    ledger.release("20260901")
    assert ledger.claim("20260901") is True

