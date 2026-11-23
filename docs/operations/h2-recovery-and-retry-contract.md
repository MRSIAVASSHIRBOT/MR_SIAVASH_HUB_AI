# H2 Recovery and Retry Contract

**Scope:** Worker restart/recovery, bounded retries, unknown outcomes, timeout boundaries, cancellation, and execution-state durability.

## Existing recovery guarantees on main

- The worker is explicitly pull-driven. The API does not silently start background execution.
- The worker process maintains a heartbeat and records its instance lifecycle. Readiness can use the heartbeat as a liveness signal.
- Every worker poll invokes stale-work recovery before claiming a new task.
- Recovery is fenced by the persisted worker lease. Expired or missing leases are required before stale work is reclaimed.
- Workflow recovery distinguishes safe steps from external-side-effect steps. A safe interrupted step may enter a resumable state; an external step with an ambiguous result becomes `unknown_outcome` / `recovery_required`.
- The workflow runner persists step attempts and digest-only checkpoints. It does not persist raw tool payloads or output bodies in the recovery ledger.
- Running cancellation is a durable request observed at execution boundaries. Lease loss is not treated as user cancellation.
- Global worker stop prevents new claims and schedule dispatch; it cannot roll back a handler already in flight.

## H2 retry policy implementation

The companion H2 change introduces a validated immutable `RetryPolicy` per allow-listed task type.

- Retry classification uses bounded, lower-case error identifiers rather than exception text.
- Retry-After is accepted only as an integer in the range 0–86,400 seconds.
- Exponential backoff is capped by the policy's maximum delay.
- The retry limit is policy-specific.
- A retry policy can be configured only for task types in the worker's explicit idempotent allow-list. The current allow-list remains `demo.echo`.
- An error code not present in the task type's allow-list is terminal and is not retried.
- External-publishing, video-generation, and other side-effecting task types do not gain automatic retry permission.

## Timeout boundary and remaining work

The current WorkerEngine does not forcibly terminate arbitrary Python handlers after a generic wall-clock timeout. A thread timeout would only abandon the waiting caller while the handler continued running; it could leave an external request in flight and make a second attempt duplicate that effect.

Therefore:
- Network adapters must set their own connect/read/request deadlines and surface a typed, sanitized outcome.
- Subprocess adapters must use subprocess-level timeouts and terminate/reap the child process before reporting a definitive timeout.
- A deadline around an external operation is not proof that the operation did not happen. Ambiguous submissions remain `unknown_outcome` until reconciliation.
- A generic hard task deadline requires a separately isolated execution process with lease fencing and reconciliation-aware termination. It is not implemented by a thread timer.

## H2 acceptance gates

1. Restarted workers recover only tasks whose lease is no longer valid; a live lease is never stolen.
2. Safe interrupted work may resume without replaying succeeded step identities.
3. An external step with an ambiguous outcome is never automatically replayed.
4. Retries require both an allow-listed idempotent task type and an allow-listed transient error class.
5. Backoff, Retry-After, and total attempts remain bounded.
6. Cancellation intent survives a worker crash and a stale worker cannot finalize state after lease loss.
7. A task timeout must not be reported as a known failure when the external outcome is ambiguous.
8. Focused and full CI must pass on the exact candidate commit.

**Validation note:** This document describes code-observed guarantees and the H2 retry-policy delta. It does not claim that a generic hard task timeout or production process supervisor has been implemented.
