from pathlib import Path


def test_nightly_schedule_runs_at_1120_shanghai():
    source = Path(__file__).with_name("pipeline") / "dagster_defs.py"
    text = source.read_text(encoding="utf-8")
    assert 'cron_schedule="20 11 * * *"' in text
    assert 'execution_timezone="Asia/Shanghai"' in text
    resolve_block = text.split("def resolve_target_partition", 1)[1].split("@op", 1)[0]
    assert "raise RetryRequested" not in resolve_block
    assert "return latest" in resolve_block


def test_dagster_start_script_uses_installed_cli_executables():
    script = Path(__file__).with_name("scripts") / "start_dagster.ps1"
    text = script.read_text(encoding="utf-8")
    assert 'dagster-daemon.exe' in text
    assert 'dagster-webserver.exe' in text
    assert 'Get-Process -Name $Name' in text


def test_windows_task_registers_startup_entrypoint():
    script = Path(__file__).with_name("scripts") / "register_dagster_task.ps1"
    text = script.read_text(encoding="utf-8")
    assert 'RiskBI-CreditAttribution-Dagster' in text
    assert 'New-ScheduledTaskTrigger -AtLogOn' in text
    assert 'start_dagster.ps1' in text
    assert 'CreateShortcut' in text
