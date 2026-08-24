# 授信归因 Dagster 调度启动脚本(daemon + webserver)
# 用法: 在任意 PowerShell 中执行  scripts/start_dagster.ps1
# UI:   http://127.0.0.1:3001

$ErrorActionPreference = "Stop"
$serverDir = Split-Path -Parent $PSScriptRoot   # scripts/ 的上级 = server/
Set-Location $serverDir

$env:DAGSTER_HOME = Join-Path $serverDir "dagster_home"
New-Item -ItemType Directory -Force -Path $env:DAGSTER_HOME | Out-Null
$env:PYTHONIOENCODING = "utf-8"

$logDir = Join-Path $serverDir "dagster_home\logs"
New-Item -ItemType Directory -Force -Path $logDir | Out-Null

function Start-DagsterProc {
    param([string]$Name, [string[]]$ProcArgs)
    $existing = Get-CimInstance Win32_Process -Filter "Name='python.exe'" |
        Where-Object { $_.CommandLine -like "*$Name*" }
    if ($existing) {
        Write-Host "$Name already running (pid $($existing.ProcessId -join ','))"
        return
    }
    $out = Join-Path $logDir "$Name.out.log"
    $err = Join-Path $logDir "$Name.err.log"
    Start-Process -FilePath "python" -ArgumentList $ProcArgs `
        -RedirectStandardOutput $out -RedirectStandardError $err `
        -WindowStyle Hidden
    Write-Host "$Name started (logs: $logDir)"
}

# daemon 负责 schedule/sensor 触发; webserver 提供 UI 与手动触发入口
Start-DagsterProc -Name "dagster-daemon" -ProcArgs @("-m", "dagster.daemon", "run")
Start-Sleep -Seconds 3
Start-DagsterProc -Name "dagster-webserver" -ProcArgs @(
    "-m", "dagster.webserver",
    "--host", "127.0.0.1", "--port", "3001",
    "--workspace", (Join-Path $serverDir "workspace.yaml")
)
Write-Host "Dagster UI: http://127.0.0.1:3001"
