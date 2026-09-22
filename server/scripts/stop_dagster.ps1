# 停止授信归因 Dagster 进程(daemon + webserver + 遗留 code server)
$serverDir = Split-Path -Parent $PSScriptRoot
$procs = Get-Process -Name "dagster-daemon", "dagster-webserver" -ErrorAction SilentlyContinue
if (-not $procs) { Write-Host "no dagster processes"; exit 0 }
foreach ($p in $procs) {
    Write-Host "stopping pid $($p.Id): $($p.ProcessName)"
    Stop-Process -Id $p.Id -Force -ErrorAction SilentlyContinue
}
Write-Host "done"
