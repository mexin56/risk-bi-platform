import pytest
from pathlib import Path

from attribution_notification import (
    DingTalkNotifier,
    S3PngDingTalkNotifier,
    build_digest,
    format_markdown,
    s3_notifier_from_env,
    format_s3_summary_markdown,
)


class _FakeS3:
    def __init__(self):
        self.calls = []

    def upload_file(self, filename, bucket, object_name, ExtraArgs=None):
        self.calls.append((filename, bucket, object_name, ExtraArgs))


class _FakeResponse:
    def __init__(self, payload, status_code=200):
        self.payload = payload
        self.status_code = status_code

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError(f"HTTP {self.status_code}")

    def json(self):
        return self.payload


class _FakeSession:
    def __init__(self, response):
        self.response = response
        self.calls = []

    def post(self, url, *, json, headers, timeout):
        self.calls.append((url, json, headers, timeout))
        return self.response


def test_s3_notifier_uploads_png_and_sends_public_image_url():
    s3 = _FakeS3()
    session = _FakeSession(_FakeResponse({"success": True}))
    png_path = next((Path("server/data/notification_reports")).glob("*.png"))
    notifier = S3PngDingTalkNotifier(
        bucket="reports",
        region="eu-west-1",
        prefix="credit-attribution",
        webhook_url="https://oapi.dingtalk.com/robot/send?access_token=token",
        webhook_secret="secret",
        public_base_url="https://cdn.test/reports",
        s3_client=s3,
        session=session,
    )

    result = notifier.publish(png_path, "20260902")

    assert result == {
        "object_name": "credit-attribution/credit_attribution_20260902.png",
        "image_url": "https://cdn.test/reports/credit-attribution/credit_attribution_20260902.png",
        "response": {"success": True},
    }
    assert len(s3.calls) == 1
    filename, bucket, object_name, extra_args = s3.calls[0]
    assert bucket == "reports"
    assert object_name == "credit-attribution/credit_attribution_20260902.png"
    assert extra_args == {"ContentType": "image/png", "ACL": "public-read"}
    assert session.calls[0][0].startswith("https://oapi.dingtalk.com/robot/send?")
    assert session.calls[0][1] == {
        "msgtype": "image",
        "image": {"picURL": result["image_url"]},
    }


def test_s3_notifier_uploads_without_sending_thumbnail_message():
    s3 = _FakeS3()
    session = _FakeSession(_FakeResponse({"errcode": 0, "errmsg": "ok"}))
    png_path = next((Path("server/data/notification_reports")).glob("*.png"))
    notifier = S3PngDingTalkNotifier(
        bucket="reports",
        region="eu-west-1",
        prefix="credit-attribution",
        webhook_url="https://oapi.dingtalk.com/robot/send?access_token=token",
        webhook_secret="secret",
        public_base_url="https://cdn.test/reports",
        s3_client=s3,
        session=session,
    )

    result = notifier.upload(png_path, "20260902")

    assert result == {
        "object_name": "credit-attribution/credit_attribution_20260902.png",
        "image_url": "https://cdn.test/reports/credit-attribution/credit_attribution_20260902.png",
    }
    assert len(s3.calls) == 1
    assert session.calls == []


def test_s3_notifier_rejects_dingtalk_api_error():
    png_path = next((Path("server/data/notification_reports")).glob("*.png"))
    notifier = S3PngDingTalkNotifier(
        bucket="reports",
        region="eu-west-1",
        prefix="credit-attribution",
        webhook_url="https://oapi.dingtalk.com/robot/send?access_token=token",
        webhook_secret="secret",
        s3_client=_FakeS3(),
        session=_FakeSession(_FakeResponse({"errcode": 1, "errmsg": "failed"})),
    )

    with pytest.raises(RuntimeError, match="钉钉图片消息发送失败"):
        notifier.publish(png_path, "20260902")


def test_s3_notifier_sends_markdown_summary_with_original_image_link():
    session = _FakeSession(_FakeResponse({"errcode": 0, "errmsg": "ok"}))
    notifier = S3PngDingTalkNotifier(
        bucket="reports",
        region="eu-west-1",
        prefix="credit-attribution",
        webhook_url="https://oapi.dingtalk.com/robot/send?access_token=token",
        webhook_secret="secret",
        session=session,
    )

    result = notifier.send_markdown(
        "### 授信归因日报\n\n[点击查看原图](https://cdn.test/report.png)"
    )

    assert result == {"errcode": 0, "errmsg": "ok"}
    assert session.calls[0][1] == {
        "msgtype": "markdown",
        "markdown": {
            "title": "授信归因日报",
            "text": "### 授信归因日报\n\n[点击查看原图](https://cdn.test/report.png)",
        },
    }


def test_s3_summary_contains_original_image_and_detail_links():
    digest = {
        "partition": "20260902",
        "alert_total": 13,
        "level_counts": {"1": 0, "2": 0, "3": 13},
        "latest_application_count": 0,
        "latest_approval_rate": None,
        "latest_cid_approval_rate_pct": None,
        "risk_points": [],
    }

    message = format_s3_summary_markdown(
        digest,
        image_url="https://cdn.test/report.png",
        page_url="http://monitor.test/?page=attribution",
    )

    assert "3、[查看原图](https://cdn.test/report.png)　　[查看明细](http://monitor.test/?page=attribution)" in message
    assert "## [3、查看原图]" not in message
    assert "![" not in message


def test_s3_notifier_from_env_returns_none_until_all_delivery_settings_exist(monkeypatch):
    monkeypatch.delenv("DINGTALK_S3_BUCKET", raising=False)
    monkeypatch.delenv("DINGTALK_WEBHOOK_URL", raising=False)
    assert s3_notifier_from_env() is None

    settings = {
        "DINGTALK_S3_BUCKET": "reports",
        "DINGTALK_S3_REGION": "eu-west-1",
        "DINGTALK_S3_PREFIX": "credit-attribution",
        "DINGTALK_WEBHOOK_URL": "https://oapi.dingtalk.com/robot/send?access_token=token",
        "DINGTALK_SECRET": "secret",
    }
    for key, value in settings.items():
        monkeypatch.setenv(key, value)

    notifier = s3_notifier_from_env()

    assert isinstance(notifier, S3PngDingTalkNotifier)
    assert notifier.bucket == "reports"


def test_digest_counts_levels_and_lists_active_hit_and_non_hit_rules():
    payload = {
        "meta": {"partition": "20260901", "generated_at": "2026-09-03T01:58:11Z"},
        "summary": {"merged_alert_count": 2, "level1_count": 1, "level2_count": 1, "level3_count": 0},
        "merged_alerts": [
            {
                "path": "命中规则",
                "level": 2,
                "level_label": "Level2",
                "status": 1,
                "tracking_start_pt": "20260828",
                "is_tracked_only": False,
                "hit_windows": ["近1日", "近3日"],
            },
            {
                "path": "未命中规则",
                "level": 0,
                "level_label": "未命中",
                "status": 2,
                "tracking_start_pt": "20260901",
                "is_tracked_only": True,
                "hit_windows": [],
            },
        ],
    }

    digest = build_digest(
        payload,
        report_url="http://host/report.png",
        page_url="http://host/?page=attribution",
    )

    assert digest["partition"] == "20260901"
    assert digest["level_counts"] == {"1": 1, "2": 1, "3": 0}
    assert digest["active_hits"][0]["path"] == "命中规则"
    assert digest["active_misses"][0]["path"] == "未命中规则"
    message = format_markdown(digest)
    assert "# 授信归因日报" in message
    assert "预警规则：" not in message
    assert "风险总结" not in message
    assert "数据分区：`20260901`" in message
    assert "最新日申请量：" not in message
    assert "件数通过率：" not in message
    assert "人数通过率：" not in message
    assert "1. 高风险预警：当前 Level3 红色规则 0 条" in message
    assert "2. 持续跟踪风险" in message
    assert "3、[查看原图](http://host/report.png)　　[查看明细](http://host/?page=attribution)" in message
    assert "![授信归因完整截图]" not in message
    assert "[打开完整截图]" not in message
    assert "http://host/report.png" in message


def test_signed_url_uses_dingtalk_hmac():
    notifier = DingTalkNotifier(
        webhook_url="https://oapi.dingtalk.com/robot/send?access_token=token",
        secret="secret",
    )
    signed = notifier.build_signed_url(timestamp_ms=1700000000000)
    assert "timestamp=1700000000000" in signed
    assert "sign=" in signed


def test_digest_contains_only_level3_risk_summary():
    payload = {
        "meta": {"partition": "20260901"},
        "summary": {
            "merged_alert_count": 4,
            "level1_count": 1,
            "level2_count": 2,
            "level3_count": 1,
            "latest_application_count": 50000,
            "latest_day_change_pct": 8.5,
            "latest_approval_rate": 31.2,
            "latest_cid_approval_rate_pct": 29.8,
        },
        "highlight": {
            "path": "traffic_channel=R1 / authen_type=nin",
            "level": 3,
            "level_label": "Level3 红色",
            "primary_window_label": "近3天",
            "hit_windows": ["1d", "3d", "7d"],
            "growth_factor": 4.2,
            "z_score": 12.3,
        },
        "merged_alerts": [],
    }

    digest = build_digest(payload)

    assert len(digest["risk_points"]) == 2
    assert "重点路径 **traffic_channel=R1 / authen_type=nin**" in digest["risk_points"][0]
    assert "请优先核查" in digest["risk_points"][0]
    message = format_markdown(digest)
    assert "# 授信归因日报" in message
    assert "预警规则：" not in message
    assert "数据分区：`20260901`" in message
    assert "最新日申请量：" not in message
    assert "件数通过率：" not in message
    assert "人数通过率：" not in message
    assert "风险总结" not in message
    assert "1. 高风险预警" in message
    assert "2. 持续跟踪风险" in message
    assert "3. " not in message
    assert "高风险预警：当前 Level3 红色规则 1 条" in message
