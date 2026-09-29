import pytest
from pathlib import Path

from attribution_notification import (
    DingTalkNotifier,
    S3PngDingTalkNotifier,
    attach_tracked_only_rules,
    build_digest,
    build_fund_digest,
    dingtalk_credentials_from_env,
    fund_report_path_is_safe,
    format_fund_markdown,
    format_markdown,
    s3_notifier_from_env,
    format_s3_fund_summary_markdown,
    format_s3_summary_markdown,
)


def test_fund_digest_uses_the_same_template_as_credit_attribution():
    payload = {
        "meta": {"partition": "20260927", "generated_at": "2026-09-28T06:01:20+00:00"},
        "summary": {
            "merged_alert_count": 2,
            "level1_count": 2,
            "level2_count": 0,
            "level3_count": 0,
            "total_order_count": 4891514,
            "abnormal_order_count": 2446,
        },
        "daily_trend": [
            {"date": "2026-09-27", "order_count": 79672, "abnormal_order_count": 37, "abnormal_rate": 0.0004644}
        ],
        "window_overview": [
            {"label": "近3天", "growth_factor": 0.87, "rate_lift_factor": 0.83, "z_score": -1.89}
        ],
        "highlight": {"path": "次新客 / PalmPay_Android", "level": 1, "level_label": "Level1 黄色"},
        "merged_alerts": [
            {
                "path": "次新客 / PalmPay_Android",
                "canonical_path": "cashloan_cid_mob_type=次新客 / register_software=PalmPay_Android",
                "level": 1,
                "level_label": "Level1 黄色",
                "status": 0,
                "hit_windows": ["7d"],
            }
        ],
    }

    digest = build_fund_digest(
        payload,
        report_url="http://host/fund.png",
        page_url="http://host/?page=attribution&tab=fund",
    )
    message = format_fund_markdown(digest)

    assert digest["partition"] == "20260927"
    assert "# 资金归集日报" in message
    assert "数据分区：`20260927`" in message
    assert "1. 高风险预警：当前 Level2+3 红色规则 0 条" in message
    assert "2. 持续跟踪风险" in message
    assert "3、[查看原图](http://host/fund.png)　　[查看明细](http://host/?page=attribution&tab=fund)" in message
    # 设计稿要求资金日报沿用授信归因结构，不展示订单总量/异常率/趋势等额外摘要
    assert "总订单" not in message
    assert "异常订单" not in message
    assert "异常率" not in message
    assert "z-score" not in message
    assert "次新客 / PalmPay_Android" not in message


def test_fund_digest_reports_level2_plus_level3_red_rules():
    payload = {
        "meta": {"partition": "20260928"},
        "summary": {"merged_alert_count": 3, "level1_count": 1, "level2_count": 1, "level3_count": 1},
        "highlight": {"path": "三级路径", "level": 3, "level_label": "Level3 红色", "hit_windows": ["3d"]},
        "merged_alerts": [],
    }

    message = format_fund_markdown(build_fund_digest(payload))

    assert "1. 高风险预警：当前 Level2+3 红色规则 2 条" in message
    assert "重点路径 **三级路径**" in message


def test_credit_and_fund_reports_share_the_same_layout():
    payload = {
        "meta": {"partition": "20260928"},
        "summary": {"merged_alert_count": 1, "level1_count": 1, "level2_count": 0, "level3_count": 0},
        "merged_alerts": [],
    }
    credit = format_markdown(
        build_digest(payload, report_url="http://host/credit.png", page_url="http://host/?tab=credit")
    )
    fund = format_fund_markdown(
        build_fund_digest(payload, report_url="http://host/fund.png", page_url="http://host/?tab=fund")
    )

    assert credit.splitlines()[0] == "# 授信归因日报"
    assert fund.splitlines()[0] == "# 资金归集日报"
    assert credit.splitlines()[1:4] == fund.splitlines()[1:4]
    # 两条风险点位置相同，只是红色规则口径按各业务域不同
    assert [line.split("：")[0] for line in (credit.splitlines()[4], credit.splitlines()[6])] == [
        "1. 高风险预警",
        "2. 持续跟踪风险",
    ]
    assert [line.split("：")[0] for line in (fund.splitlines()[4], fund.splitlines()[6])] == [
        "1. 高风险预警",
        "2. 持续跟踪风险",
    ]
    assert credit.splitlines()[8].startswith("3、")
    assert fund.splitlines()[8].startswith("3、")


def test_tracked_only_rules_are_appended_for_digests_without_them():
    payload = {
        "meta": {"partition": "20260928"},
        "summary": {"merged_alert_count": 1, "level1_count": 1, "level2_count": 0, "level3_count": 0},
        "merged_alerts": [
            {"path": "已命中规则", "canonical_path": "a=1", "level": 1, "status": 1},
        ],
    }
    active = {
        "a=1": {"status": 1, "rule": {"path": "已命中规则", "conditions": []}, "entered_pt": "20260901"},
        "a=2": {"status": 2, "rule": {"path": "已跟踪未命中规则", "conditions": []}, "entered_pt": "20260920"},
    }

    enriched = attach_tracked_only_rules(payload, active)
    message = format_fund_markdown(build_fund_digest(enriched))

    assert len(enriched["merged_alerts"]) == 2
    assert (
        "2. 持续跟踪风险：当前仍命中的打标规则 1 条（已命中规则），"
        "本日未命中，仍在持续跟踪 1 条（已跟踪未命中规则）"
    ) in message
    # 原始 payload 不得被就地修改
    assert len(payload["merged_alerts"]) == 1
    assert attach_tracked_only_rules(payload, {}) == payload


def test_fund_report_path_rejects_credit_report_names(tmp_path: Path):
    with pytest.raises(ValueError):
        fund_report_path_is_safe(tmp_path, "credit_attribution_20260928_20260929_060000.png")
    assert fund_report_path_is_safe(tmp_path, "fund_attribution_20260928_20260929_060000.png").name == (
        "fund_attribution_20260928_20260929_060000.png"
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
        "risk_points": [
            "高风险预警：当前 Level3 红色规则 13 条；重点路径 **三级路径** 在 近3天 命中 3d，增长 2.00 倍、z-score 9.00，请优先核查。",
            "持续跟踪风险：当前仍命中的打标规则 1 条（规则A），本日未命中，仍在持续跟踪 0 条（无），请持续关注后续 pt。",
        ],
    }

    message = format_s3_summary_markdown(
        digest,
        image_url="https://cdn.test/report.png",
        page_url="http://monitor.test/?page=attribution",
    )
    fund_message = format_s3_fund_summary_markdown(
        {**digest, "risk_points": []},
        image_url="https://cdn.test/fund.png",
        page_url="http://monitor.test/?page=attribution&tab=fund",
    )

    assert "3、[查看原图](https://cdn.test/report.png)　　[查看明细](http://monitor.test/?page=attribution)" in message
    assert "## [3、查看原图]" not in message
    assert "![" not in message
    assert (
        "1、[查看原图](https://cdn.test/fund.png)　　"
        "[查看明细](http://monitor.test/?page=attribution&tab=fund)"
    ) in fund_message


def test_s3_notifier_from_env_returns_none_until_all_delivery_settings_exist(monkeypatch):
    monkeypatch.delenv("DINGTALK_S3_BUCKET", raising=False)
    monkeypatch.delenv("DINGTALK_WEBHOOK_URL", raising=False)
    monkeypatch.delenv("DINGTALK_TEST_WEBHOOK_URL", raising=False)
    monkeypatch.delenv("DINGTALK_TEST_SECRET", raising=False)
    monkeypatch.setenv("DINGTALK_TARGET_ENV", "test")
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


def test_dingtalk_credentials_keep_test_and_prod_groups_separate(monkeypatch):
    # 其他用例可能已通过 load_local_env() 写入真实群配置，这里先清干净再断言
    for key in ("DINGTALK_TEST_WEBHOOK_URL", "DINGTALK_TEST_SECRET"):
        monkeypatch.delenv(key, raising=False)
    monkeypatch.setenv("DINGTALK_TARGET_ENV", "test")
    monkeypatch.setenv("DINGTALK_WEBHOOK_URL", "https://test.example/robot")
    monkeypatch.setenv("DINGTALK_SECRET", "test-secret")
    monkeypatch.setenv("DINGTALK_PROD_WEBHOOK_URL", "https://prod.example/robot")
    monkeypatch.setenv("DINGTALK_PROD_SECRET", "prod-secret")

    assert dingtalk_credentials_from_env() == (
        "test",
        "https://test.example/robot",
        "test-secret",
    )
    assert dingtalk_credentials_from_env("prod") == (
        "prod",
        "https://prod.example/robot",
        "prod-secret",
    )


def test_prod_group_does_not_fall_back_to_test_webhook(monkeypatch):
    monkeypatch.setenv("DINGTALK_TARGET_ENV", "prod")
    monkeypatch.delenv("DINGTALK_PROD_WEBHOOK_URL", raising=False)
    monkeypatch.delenv("DINGTALK_PROD_SECRET", raising=False)
    monkeypatch.setenv("DINGTALK_WEBHOOK_URL", "https://test.example/robot")
    monkeypatch.setenv("DINGTALK_SECRET", "test-secret")

    with pytest.raises(ValueError, match="DINGTALK_PROD_WEBHOOK_URL"):
        dingtalk_credentials_from_env()


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
