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
    param([string]$Name, [string]$FilePath, [string[]]$ProcArgs)
    $existing = Get-Process -Name $Name -ErrorAction SilentlyContinue
    if ($existing) {
        Write-Host "$Name already running (pid $($existing.ProcessId -join ','))"
        return
    }
    $out = Join-Path $logDir "$Name.out.log"
    $err = Join-Path $logDir "$Name.err.log"
    $resolvedFilePath = (Get-Command $FilePath -ErrorAction Stop).Source
    Start-Process -FilePath $resolvedFilePath -ArgumentList $ProcArgs `
        -RedirectStandardOutput $out -RedirectStandardError $err `
        -WindowStyle Hidden
    Write-Host "$Name started (logs: $logDir)"
}

# Start the daemon first; it owns schedule and sensor execution.
Start-DagsterProc -Name "dagster-daemon" -FilePath "dagster-daemon.exe" -ProcArgs @("run")
Start-Sleep -Seconds 3
Start-DagsterProc -Name "dagster-webserver" -FilePath "dagster-webserver.exe" -ProcArgs @(
    "--host", "127.0.0.1", "--port", "3001",
    "--workspace", (Join-Path $serverDir "workspace.yaml")
)
Write-Host "Dagster UI: http://127.0.0.1:3001"
