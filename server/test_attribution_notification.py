from attribution_notification import DingTalkNotifier, build_digest, format_markdown


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
    assert "Level2" in message
    assert "本日未命中，仍在持续跟踪" in message
    assert "http://host/report.png" in message


def test_signed_url_uses_dingtalk_hmac():
    notifier = DingTalkNotifier(
        webhook_url="https://oapi.dingtalk.com/robot/send?access_token=token",
        secret="secret",
    )
    signed = notifier.build_signed_url(timestamp_ms=1700000000000)
    assert "timestamp=1700000000000" in signed
    assert "sign=" in signed
