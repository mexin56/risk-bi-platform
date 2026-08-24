# 停止授信归因 Dagster 进程(daemon + webserver + 遗留 code server)
$serverDir = Split-Path -Parent $PSScriptRoot
$procs = Get-CimInstance Win32_Process -Filter "Name='python.exe'" |
    Where-Object { $_.CommandLine -match "dagster" }
if (-not $procs) { Write-Host "no dagster processes"; exit 0 }
foreach ($p in $procs) {
    Write-Host "stopping pid $($p.ProcessId): $($p.CommandLine.Substring(0, [Math]::Min(90, $p.CommandLine.Length)))"
    Stop-Process -Id $p.ProcessId -Force -ErrorAction SilentlyContinue
}
Write-Host "done"
