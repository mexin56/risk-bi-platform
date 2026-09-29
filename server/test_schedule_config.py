from pathlib import Path


def test_nightly_schedule_runs_at_1400_shanghai():
    source = Path(__file__).with_name("pipeline") / "dagster_defs.py"
    text = source.read_text(encoding="utf-8")
    assert 'cron_schedule="00 14 * * *"' in text
    assert 'execution_timezone="Asia/Shanghai"' in text
    assert 'name="nightly_attribution_1400"' in text
    resolve_block = text.split("def resolve_target_partition", 1)[1].split("@op", 1)[0]
    assert "raise RetryRequested" in resolve_block
    assert "return ready" in resolve_block


def test_stale_upstream_partition_does_not_pass_readiness_gate():
    from datetime import date

    from pipeline.dagster_defs import select_ready_partition

    assert select_ready_partition(["20260921"], today=date(2026, 9, 23)) is None
    assert select_ready_partition(["20260921", "20260922"], today=date(2026, 9, 23)) == "20260922"
    assert select_ready_partition(["20260921", "20260923"], today=date(2026, 9, 23)) is None


def test_dagster_start_script_uses_installed_cli_executables():
    script = Path(__file__).with_name("scripts") / "start_dagster.ps1"
    text = script.read_text(encoding="utf-8")
    assert 'dagster-daemon.exe' in text
    assert 'dagster-webserver.exe' in text
    assert 'Get-Process -Name $Name' in text


def test_dagster_workspace_sets_pipeline_working_directory():
    text = Path(__file__).with_name("workspace.yaml").read_text(encoding="utf-8")
    assert "module_name: pipeline.dagster_defs" in text
    assert "working_directory:" in text


def test_windows_task_registers_startup_entrypoint():
    script = Path(__file__).with_name("scripts") / "register_dagster_task.ps1"
    text = script.read_text(encoding="utf-8")
    assert 'RiskBI-CreditAttribution-Dagster' in text
    assert 'New-ScheduledTaskTrigger -AtLogOn' in text
    assert 'start_dagster.ps1' in text
    assert 'CreateShortcut' in text
