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
5. Start the worker separately: `python -m mrhub.worker_service`. It records a process-specific heartbeat every three seconds and marks itself stopped on graceful shutdown.
6. Use the authenticated `GET /jobs/summary` endpoint to inspect queue counts, workflow-state counts, retry scheduling, expired running leases, and oldest queued age.

**Worker readiness:** `/ready` reports `worker: running` only when a fresh heartbeat exists. By default, API readiness remains database-only so deployments that intentionally run API without a worker still work. Set `MRH_REQUIRE_WORKER_FOR_READINESS=true` when queued jobs require a worker; in that mode `/ready` returns 503 if the heartbeat is absent or older than `MRH_WORKER_HEARTBEAT_TIMEOUT_SECONDS` (default 15). A forced kill may leave a stale `running` row, but its heartbeat ages out and is not considered healthy.

### Bounded dispatch cycle

Each explicit worker polling cycle is bounded: it claims and executes at most one queued task, then attempts at most one due content-publishing schedule. A cycle may therefore publish one due schedule even when no queued task was available. It does not batch-drain the content schedule table. The worker service repeats these cycles at its configured polling interval; the API does not start them.

The durable emergency-stop switch blocks both new task claims and content-schedule dispatch. It does not roll back a handler or provider call that was already in flight when the stop was requested. Content schedules are revalidated against the approved draft version and content hash immediately before publication. A provider-confirmed transient rejection may be retried within the bounded attempt policy; an ambiguous provider outcome is quarantined as `unknown_outcome` and must not be automatically replayed.

## Durable media cleanup

When the opt-in worker process starts, it also starts a separate maintenance thread that retries the durable media-file cleanup queue every 30 seconds. Each pass is globally bounded to 100 entries across owners. Successful unlink operations remove their queue rows; failures remain durable, have their retry count advanced, and move behind untouched entries so one inaccessible file cannot starve the queue.

This sweeper is not started by the API and is not required for database-only API readiness. If the worker is stopped, cleanup intents remain in SQLite and are retried when the worker starts again. The sweeper processes only storage keys already recorded by the media repository; it does not accept paths or URLs from users.

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
- Treat hosted CI as automated evidence only; complete target-runtime, recovery, monitoring, and owner acceptance gates before any production release.


### Scheduled development agent quota handling

The scheduled OpenCode development cycle uses the configured free OpenRouter model. If the provider explicitly returns `free-models-per-day` rate limiting, the cycle exits as a successful no-op, emits a warning, and produces no proposal artifact; the publisher therefore has nothing to apply. Missing credentials and all other agent errors remain failures. This avoids treating exhausted free quota as a code regression and does not add paid retries or alter workflow permissions.
