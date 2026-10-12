from datetime import datetime, timezone
from pathlib import Path

import io

import pytest
from fastapi.testclient import TestClient
from PIL import Image

from attribution_notification import (
    FUND_REPORT_FILENAME_RE,
    fund_report_path_is_safe,
    report_path_is_safe,
    resolve_report_image,
    save_fund_report_png,
    save_report_png,
    thumbnail_filename,
    thumbnail_path_is_safe,
    write_thumbnail,
)


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


def _write_wide_png(path: Path, size: tuple[int, int] = (1200, 2000)) -> Path:
    Image.new("RGB", size, (240, 248, 246)).save(path, format="PNG")
    return path


def test_thumbnail_is_a_downscaled_jpeg_next_to_the_full_screenshot(tmp_path: Path):
    report = _write_wide_png(tmp_path / "credit_attribution_20260928_20260929_060000.png")

    thumbnail = write_thumbnail(report, width=900, quality=85)

    assert thumbnail == tmp_path / "thumb" / "credit_attribution_20260928_20260929_060000.jpg"
    with Image.open(thumbnail) as image:
        assert image.size == (900, 1500)
        assert image.format == "JPEG"
    assert thumbnail.stat().st_size < report.stat().st_size


def test_thumbnail_is_skipped_when_disabled_or_already_small(tmp_path: Path, monkeypatch):
    report = _write_wide_png(tmp_path / "credit_attribution_20260928_20260929_060000.png")

    assert write_thumbnail(report, width=0) is None
    assert not (tmp_path / "thumb").exists()

    small = _write_wide_png(tmp_path / "credit_attribution_20260928_20260929_060001.png", (800, 600))
    assert write_thumbnail(small, width=900) is None


def test_thumbnail_width_can_be_configured_by_env(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("ATTRIBUTION_NOTIFY_THUMBNAIL_WIDTH", "640")
    monkeypatch.setenv("ATTRIBUTION_NOTIFY_THUMBNAIL_QUALITY", "70")
    report = _write_wide_png(tmp_path / "fund_attribution_20260928_20260929_060000.png")

    thumbnail = write_thumbnail(report)

    assert thumbnail.name == thumbnail_filename(report.name)
    with Image.open(thumbnail) as image:
        assert image.size == (640, 1067)


def test_thumbnail_path_validation_matches_the_report_rules(tmp_path: Path):
    name = "fund_attribution_20260928_20260929_060000.png"

    assert thumbnail_path_is_safe(
        tmp_path, name, pattern=FUND_REPORT_FILENAME_RE
    ).parent == (tmp_path / "thumb").resolve()
    assert thumbnail_filename(name) == "fund_attribution_20260928_20260929_060000.jpg"
    with pytest.raises(ValueError):
        thumbnail_path_is_safe(tmp_path, "../secret.png")
    with pytest.raises(ValueError):
        thumbnail_path_is_safe(
            tmp_path, "credit_attribution_20260928_20260929_060000.png", pattern=FUND_REPORT_FILENAME_RE
        )


def test_resolve_report_image_prefers_thumbnail_and_falls_back_to_png(tmp_path: Path):
    report = _write_wide_png(tmp_path / "credit_attribution_20260928_20260929_060000.png")

    resolved = resolve_report_image(tmp_path, report.name)
    assert resolved == (tmp_path / "credit_attribution_20260928_20260929_060000.png", "image/png")

    write_thumbnail(report, width=600)
    resolved = resolve_report_image(tmp_path, report.name)
    assert resolved[0].parent == (tmp_path / "thumb").resolve()
    assert resolved[1] == "image/jpeg"
    assert resolve_report_image(tmp_path, "credit_attribution_20260928_20260929_060099.png") is None


def test_fund_thumbnail_route_serves_the_jpeg(monkeypatch, tmp_path: Path):
    import app as attribution_app

    report = save_fund_report_png(
        tmp_path,
        "20260928",
        b"png",
        datetime(2026, 9, 29, 6, 0, 0, tzinfo=timezone.utc),
    )
    report.write_bytes(_write_wide_png(tmp_path / report.name).read_bytes())
    write_thumbnail(report, width=480)
    monkeypatch.setattr(attribution_app, "NOTIFICATION_REPORT_DIR", tmp_path)
    client = TestClient(attribution_app.app)

    response = client.get(f"/api/fund-attribution/notification-reports/{report.name}/thumbnail")

    assert response.status_code == 200
    assert response.headers["content-type"] == "image/jpeg"
    with Image.open(io.BytesIO(response.content)) as image:
        assert image.size == (480, 800)
    # 没有缩略图时退回整图，不会 404
    other = save_fund_report_png(
        tmp_path, "20260927", b"png", datetime(2026, 9, 28, 6, 0, 0, tzinfo=timezone.utc)
    )
    fallback = client.get(f"/api/fund-attribution/notification-reports/{other.name}/thumbnail")
    assert fallback.status_code == 200
    assert fallback.content == b"png"


def test_fund_report_api_rejects_credit_report_names(tmp_path: Path):
    with pytest.raises(ValueError):
        fund_report_path_is_safe(tmp_path, "credit_attribution_20260928_20260929_060000.png")
