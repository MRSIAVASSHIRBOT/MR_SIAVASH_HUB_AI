# Worker emergency-stop operations

## What the stop switch guarantees

The durable worker-control flag is stored in the same SQLite database used by task claiming. Claiming checks the flag inside the same `BEGIN IMMEDIATE` transaction as the queued-task selection and status transition. Once the stop transaction commits, subsequent task claims are rejected until an operator explicitly clears the flag.

The stop switch is a **dispatch gate**, not a process-kill mechanism:

- A synchronous handler that was already claimed may finish. The switch does not roll back an external request already submitted, and it does not prove that such a request was cancelled.
- Do not assume an interrupted external operation failed. If its result is ambiguous, preserve the unknown outcome and reconcile with the provider before retrying.
- Queued tasks remain queued while stopped. Retry timing and durable state are preserved.
- Content schedule dispatch is skipped while the stop flag is set; operators should still verify provider-side state for any operation already in flight.
- The synchronous `/agent/run` path checks the same durable stop flag before each model turn and again after inference before dispatching a proposed tool. A stop cannot interrupt a provider request already in flight, but it prevents a tool proposal returned after the stop from being executed.
- Resumption is explicit through the authenticated `POST /jobs/resume` route. Clearing the flag permits future dispatch; it does not automatically replay or reconcile ambiguous side effects.

## Operator procedure

1. Read `GET /jobs/control` and record the stop reason and timestamp.
2. Activate `POST /jobs/emergency-stop` with a concise, non-secret reason.
3. Confirm the returned state reports `stopped: true`.
4. Inspect running jobs and any external provider records separately. Do not infer cancellation from the stop flag alone.
5. Reconcile operations with unknown outcomes before any retry or resume that could duplicate an external effect.
6. Resume only after the incident is understood, using `POST /jobs/resume`; then verify queued work progresses as expected.

## Verification boundary

Automated tests cover persistence across worker instances, blocking new claims, cancellation of Agent inference before a new turn, and blocking a tool proposal when the stop is raised during model inference. They also preserve the contract that an already-running synchronous handler may finish while subsequent tasks remain queued. They do not simulate cancellation of arbitrary external systems or establish production deployment readiness. Authentication currently protects the stop/resume routes; authorization and owner-scoping require a separate security review before multi-user deployment.
