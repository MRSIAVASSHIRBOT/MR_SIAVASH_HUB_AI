$ErrorActionPreference = "Stop"
$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$runtimeFile = Join-Path $repoRoot ".mrhub-runtime.json"
if (-not (Test-Path $runtimeFile)) { Write-Host "No runtime record found; nothing to stop."; exit 0 }
$runtime = Get-Content $runtimeFile -Raw | ConvertFrom-Json
$allStopped = $true
$targets = @(
    @{Pid=$runtime.api_pid; Match="uvicorn mrhub.main:app"; Label="API"},
    @{Pid=$runtime.worker_pid; Match="mrhub.worker_service"; Label="worker"}
)
foreach ($target in $targets) {
    if (-not $target.Pid) { continue }
    $proc = Get-CimInstance Win32_Process -Filter "ProcessId = $($target.Pid)" -ErrorAction SilentlyContinue
    if (-not $proc) { Write-Host "$($target.Label): already stopped."; continue }
    if (-not $proc.CommandLine -or -not $proc.CommandLine.Contains($target.Match)) {
        Write-Warning "$($target.Label): PID command mismatch; refusing to stop it."
        $allStopped = $false
        continue
    }
    Stop-Process -Id $target.Pid -ErrorAction SilentlyContinue
    Wait-Process -Id $target.Pid -Timeout 10 -ErrorAction SilentlyContinue
    $remaining = Get-CimInstance Win32_Process -Filter "ProcessId = $($target.Pid)" -ErrorAction SilentlyContinue
    if ($remaining -and $remaining.CommandLine -and $remaining.CommandLine.Contains($target.Match)) {
        Write-Warning "$($target.Label): process is still running after the shutdown timeout."
        $allStopped = $false
        continue
    }
    Write-Host "$($target.Label): stopped."
}
if ($allStopped) {
    Remove-Item $runtimeFile -ErrorAction SilentlyContinue
} else {
    Write-Warning "Runtime record retained because one or more processes were not stopped."
}
