from pathlib import Path


def test_dingtalk_schedule_runs_at_1420_shanghai():
    text = Path("server/pipeline/dagster_defs.py").read_text(encoding="utf-8")
    assert 'cron_schedule="20 14 * * *"' in text
    assert 'execution_timezone="Asia/Shanghai"' in text
    assert 'name="daily_attribution_dingtalk_1420"' in text


def test_model_monitoring_schedule_runs_at_1430_shanghai():
    text = Path("server/pipeline/dagster_defs.py").read_text(encoding="utf-8")
    assert 'cron_schedule="30 14 * * *"' in text
    assert 'name="nightly_model_monitoring_1430"' in text


def test_fund_attribution_schedule_runs_at_1400_shanghai():
    text = Path("server/pipeline/dagster_defs.py").read_text(encoding="utf-8")
    assert 'cron_schedule="00 14 * * *"' in text
    assert 'name="daily_fund_attribution_1400"' in text
    assert 'daily_fund_attribution_job' in text


def test_fund_attribution_dingtalk_schedule_runs_after_fund_publish():
    text = Path("server/pipeline/dagster_defs.py").read_text(encoding="utf-8")
    assert 'name="daily_fund_attribution_dingtalk_1420"' in text
    assert 'job=daily_fund_attribution_dingtalk_job' in text
    assert 'def notify_fund_dingtalk' in text


def test_fund_dingtalk_uses_the_credit_template_and_serves_its_own_report():
    defs_text = Path("server/pipeline/dagster_defs.py").read_text(encoding="utf-8")
    app_text = Path("server/app.py").read_text(encoding="utf-8")

    assert "build_fund_digest(payload, report_url=report_url, page_url=page_url)" in defs_text
    assert "format_s3_fund_summary_markdown" in defs_text
    assert "capture_fund_page" in defs_text
    assert "attach_tracked_only_rules" in defs_text
    assert "/api/fund-attribution/notification-reports/{filename}" in app_text


def test_env_example_documents_dingtalk_without_credentials():
    text = Path("server/.env.example").read_text(encoding="utf-8")
    assert "DINGTALK_TARGET_ENV=test|prod" in text
    assert "DINGTALK_WEBHOOK_URL=" in text
    assert "DINGTALK_SECRET=" in text
    assert "DINGTALK_PROD_WEBHOOK_URL=" in text
    assert "DINGTALK_PROD_SECRET=" in text
    assert "ATTRIBUTION_PUBLIC_BASE_URL=" in text
    assert "DINGTALK_S3_FUND_PREFIX=" in text
