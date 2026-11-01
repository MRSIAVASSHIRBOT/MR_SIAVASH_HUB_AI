# Workflow Worker Operations Runbook

This runbook describes the current local-first, pull-driven worker. It is not a production deployment approval.

## Runtime layout

Run the API and worker as separate processes against the same configured SQLite database. The API does not execute queued work automatically.

### Configure

Set the database path with `MRH_DATABASE_PATH` (or `MRH_DATABASE_PATH` via the application's settings environment mapping) and provide `MRH_WORKFLOW_PAYLOAD_KEY` before accepting durable agent workflows. The payload key must be URL-safe Base64 that decodes to exactly 32 bytes. Use a secret manager or protected environment injection; do not commit the key, place it in shell history, or print it in logs.

A missing or invalid key is a hard configuration error. Do not replace it with a generated fallback or plaintext storage. The API and worker must use the same key to decrypt queued workflow inputs.

## Start and verify

1. Install the project in its supported Python environment with `pip install -e ".[dev]"`.
2. Start the API: `uvicorn mrhub.main:app --host 127.0.0.1 --port 8000`.
3. Check `GET /health` for process liveness.
4. Check `GET /ready` for read-only database/schema readiness. A 503 indicates the existing database is missing, unreadable, or not at the expected migration version. This endpoint never runs migrations.
5. Start the worker separately: `python -m mrhub.worker_service`.
6. Use the authenticated `GET /jobs/summary` endpoint to inspect queue counts, workflow-state counts, retry scheduling, expired running leases, and oldest queued age.

**Important limitation:** `/ready` checks the database only. It does not prove that the separate worker process is alive. Worker-process heartbeat/readiness remains a follow-up before production orchestration.

## Cancellation and recovery

- Queued workflows can be cancelled before dispatch.
- Running cancellation is cooperative. A tool already executing may finish before the runner observes cancellation.
- If the worker stops while a safe step is active, recovery may pause the workflow for an explicit safe resume.
- If an external side effect may have completed, the workflow must remain in `unknown_outcome` / `recovery_required` until a human or a dedicated reconciliation handler determines the result. Do not blindly retry it.
- A worker that loses its lease must not write a checkpoint or terminal state. Let the current lease owner or stale-worker recovery reconcile the task.

## Shutdown

Send SIGINT or SIGTERM to the worker process. It stops polling; an in-flight handler may need to finish or be recovered after its lease expires. Do not delete lease or workflow rows manually to force progress.

## Key rotation and restore

The current envelope uses versioned authenticated encryption and binds ciphertext to workflow, task, and owner identifiers. Back up the key independently from the database. Losing the key makes retained queued payloads unreadable; restoring the database without the matching key does not restore executability. Key rotation and a multi-key decryption window need a separately reviewed migration plan.

## Release checks

Before deploying beyond a local/test environment:

- Require green Backend CI and CI on the exact commit.
- Verify cancellation, stale lease fencing, and crash recovery with integration tests.
- Verify the actual API and worker processes share the intended database and encryption key.
- Configure monitoring for queue age, expired leases, recovery-required workflows, and worker process liveness.
- Keep the feature PR unmerged until the owner approves the release and the worker-heartbeat design is complete.
