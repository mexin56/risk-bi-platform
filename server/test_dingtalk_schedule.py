from pathlib import Path


def test_dingtalk_schedule_runs_at_1140_shanghai():
    text = Path("server/pipeline/dagster_defs.py").read_text(encoding="utf-8")
    assert 'cron_schedule="40 11 * * *"' in text
    assert 'execution_timezone="Asia/Shanghai"' in text
    assert 'name="daily_attribution_dingtalk_1130"' in text


def test_env_example_documents_dingtalk_without_credentials():
    text = Path("server/.env.example").read_text(encoding="utf-8")
    assert "DINGTALK_WEBHOOK_URL=" in text
    assert "DINGTALK_SECRET=" in text
    assert "ATTRIBUTION_PUBLIC_BASE_URL=" in text
