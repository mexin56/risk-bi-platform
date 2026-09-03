from datetime import datetime, timezone
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from attribution_notification import report_path_is_safe, save_report_png


def test_report_filename_contains_pt_and_is_saved_under_report_dir(tmp_path: Path):
    path = save_report_png(
        tmp_path,
        "20260901",
        b"png",
        datetime(2026, 9, 3, tzinfo=timezone.utc),
    )
    assert path.parent == tmp_path
    assert "20260901" in path.name
    assert path.suffix == ".png"
    assert path.read_bytes() == b"png"


def test_report_path_rejects_traversal(tmp_path: Path):
    with pytest.raises(ValueError):
        report_path_is_safe(tmp_path, "..\\secret.png")


def test_report_api_serves_png_from_the_report_directory(monkeypatch, tmp_path: Path):
    import app as attribution_app

    report = save_report_png(
        tmp_path,
        "20260901",
        b"png",
        datetime(2026, 9, 3, 12, 34, 56, tzinfo=timezone.utc),
    )
    monkeypatch.setattr(attribution_app, "NOTIFICATION_REPORT_DIR", tmp_path)

    response = TestClient(attribution_app.app).get(
        f"/api/credit-attribution/notification-reports/{report.name}"
    )

    assert response.status_code == 200
    assert response.content == b"png"
