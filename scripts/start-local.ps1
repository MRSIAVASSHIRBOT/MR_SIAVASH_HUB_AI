[CmdletBinding()]
param([switch]$SkipInstall)

$ErrorActionPreference = "Stop"
$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
Set-Location $repoRoot

if (-not (Get-Command py -ErrorAction SilentlyContinue)) {
    throw "Python Launcher was not found. Install Python 3.11."
}
& py -3.11 --version *> $null
if ($LASTEXITCODE -ne 0) { throw "Python 3.11 is required by this launcher." }

$venvPython = Join-Path $repoRoot ".venv\Scripts\python.exe"
if (-not (Test-Path $venvPython)) {
    & py -3.11 -m venv .venv
    if ($LASTEXITCODE -ne 0) { throw "Virtual environment creation failed." }
}
if (-not $SkipInstall) {
    & $venvPython -m pip install --upgrade pip
    if ($LASTEXITCODE -ne 0) { throw "pip upgrade failed." }
    & $venvPython -m pip install -e ".[dev]"
    if ($LASTEXITCODE -ne 0) { throw "Project installation failed." }
}

$envFile = Join-Path $repoRoot ".env"
if (-not (Test-Path $envFile)) { Copy-Item ".env.example" $envFile }
$keyLine = Get-Content $envFile | Where-Object { $_ -match '^MRH_WORKFLOW_PAYLOAD_KEY=' } | Select-Object -First 1
if ($keyLine) {
    $payloadKey = $keyLine.Substring("MRH_WORKFLOW_PAYLOAD_KEY=".Length).Trim()
} else {
    $payloadKey = (& $venvPython -c "import base64,secrets; print(base64.urlsafe_b64encode(secrets.token_bytes(32)).decode('ascii'))").Trim()
    if ($LASTEXITCODE -ne 0 -or -not $payloadKey) { throw "Could not generate workflow encryption key." }
    Add-Content -Path $envFile -Value ("MRH_WORKFLOW_PAYLOAD_KEY=" + $payloadKey)
}
$env:MRH_WORKFLOW_PAYLOAD_KEY = $payloadKey
$env:MRH_REQUIRE_WORKER_FOR_READINESS = "true"
& $venvPython -c "from mrhub.jobs.payload_envelope import load_payload_key; load_payload_key(); print('Workflow key validated.')"
if ($LASTEXITCODE -ne 0) { throw "Workflow encryption key validation failed." }

$logDir = Join-Path $repoRoot "logs"
New-Item -ItemType Directory -Force -Path $logDir | Out-Null
$runtimeFile = Join-Path $repoRoot ".mrhub-runtime.json"
if (Test-Path $runtimeFile) {
    $old = Get-Content $runtimeFile -Raw | ConvertFrom-Json
    foreach ($entry in @(@{Pid=$old.api_pid; Match="uvicorn mrhub.main:app"}, @{Pid=$old.worker_pid; Match="mrhub.worker_service"})) {
        if ($entry.Pid) {
            $proc = Get-CimInstance Win32_Process -Filter "ProcessId = $($entry.Pid)" -ErrorAction SilentlyContinue
            if ($proc -and $proc.CommandLine -and $proc.CommandLine.Contains($entry.Match)) {
                Stop-Process -Id $entry.Pid -Force -ErrorAction SilentlyContinue
            }
        }
    }
}
$worker = Start-Process -FilePath $venvPython -ArgumentList @("-m", "mrhub.worker_service") -WorkingDirectory $repoRoot -PassThru -RedirectStandardOutput (Join-Path $logDir "worker.out.log") -RedirectStandardError (Join-Path $logDir "worker.err.log")
$api = Start-Process -FilePath $venvPython -ArgumentList @("-m", "uvicorn", "mrhub.main:app", "--host", "127.0.0.1", "--port", "8000") -WorkingDirectory $repoRoot -PassThru -RedirectStandardOutput (Join-Path $logDir "api.out.log") -RedirectStandardError (Join-Path $logDir "api.err.log")
@{api_pid=$api.Id; worker_pid=$worker.Id; started_at=(Get-Date).ToUniversalTime().ToString("o")} | ConvertTo-Json | Set-Content -Path $runtimeFile -Encoding UTF8

$ready = $false
for ($attempt = 0; $attempt -lt 40; $attempt++) {
    Start-Sleep -Milliseconds 750
    try {
        $response = Invoke-RestMethod -Uri "http://127.0.0.1:8000/ready" -TimeoutSec 2
        if ($response.status -eq "ready" -and $response.worker -eq "running") { $ready = $true; break }
    } catch { }
    if ($api.HasExited -or $worker.HasExited) { break }
}
if (-not $ready) {
    Write-Host "Startup did not reach ready state. Inspect logs/api.err.log and logs/worker.err.log."
    Write-Host "API PID: $($api.Id) | Worker PID: $($worker.Id)"
    exit 1
}
Write-Host "MR_SIAVASH_HUB_AI is running."
Write-Host "Operator UI: http://127.0.0.1:8000/ui/"
Write-Host "API docs:    http://127.0.0.1:8000/docs"
Write-Host "Readiness:   http://127.0.0.1:8000/ready"
Write-Host "API PID: $($api.Id) | Worker PID: $($worker.Id)"
Write-Host "Stop: .\scripts\stop-local.ps1"
Write-Host "Logs: .\logs\api.*.log and .\logs\worker.*.log"
