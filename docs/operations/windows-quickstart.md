# Windows local quick start

This first-run path starts the FastAPI control plane and pull-driven worker as separate local processes. It does not enable cloud inference or social publishing.

## Requirements
- Windows 10/11
- Python 3.11 available through the Windows Python Launcher (py -3.11)
- Git and a checkout of this repository

## Start
Open PowerShell in the repository root and run:

    Set-ExecutionPolicy -Scope Process Bypass
    .\scripts\start-local.ps1

The first run creates .venv, installs the editable development package, copies .env.example to the ignored local .env file, and generates a persistent 32-byte workflow-payload encryption key if one is not already present. The key is stored only in .env and is not printed. Keep .env private and back up the key separately from SQLite; losing it makes previously queued encrypted workflow inputs unreadable.

The launcher starts the worker and API, then waits for /ready to report both the database and worker as ready. Process IDs are recorded in the ignored .mrhub-runtime.json file. Logs are written under the ignored logs/ directory.

Open:
- Operator UI: http://127.0.0.1:8000/ui/
- API documentation: http://127.0.0.1:8000/docs
- Readiness: http://127.0.0.1:8000/ready

Initialize the owner account from the same machine using POST /auth/setup with a unique password of at least 14 characters. Then sign in through POST /auth/login and use the returned bearer token for protected API operations.

## Stop

    .\scripts\stop-local.ps1

The stop script verifies each recorded PID's command line before stopping it. If a PID has been reused by another process, it refuses to stop that process.

## Configuration boundaries
- The application binds to 127.0.0.1; do not expose it directly to the public internet.
- Ollama and OpenRouter inference remain disabled unless explicitly configured.
- Telegram and Instagram publishing remain disabled unless credentials and provider-side configuration are supplied. Real publishing requires a separate controlled acceptance test.
- The generated workflow encryption key is not an inference API key. No OpenRouter credential is required to start the application.
- The launcher currently requires Python 3.11. If only Python 3.12 is installed, use the manual commands in the root README.

## Troubleshooting
- Installation failure: inspect the pip error and rerun the launcher.
- API startup failure: inspect logs/api.err.log.
- Worker startup failure: inspect logs/worker.err.log.
- Readiness timeout: confirm port 8000 is available, then inspect both error logs and /ready.
- Rerunning the launcher does not delete .env, the database, or media files.
- Retain the exact same workflow key across restarts and backups.
