$ErrorActionPreference = "Stop"
$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$runtimeFile = Join-Path $repoRoot ".mrhub-runtime.json"
if (-not (Test-Path $runtimeFile)) { Write-Host "No runtime record found; nothing to stop."; exit 0 }
$runtime = Get-Content $runtimeFile -Raw | ConvertFrom-Json
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
        continue
    }
    Stop-Process -Id $target.Pid -ErrorAction Stop
    Write-Host "$($target.Label): stopped."
}
Remove-Item $runtimeFile -ErrorAction SilentlyContinue
