# Worker stop contract

The durable worker stop switch is a **dispatch-quiesce control**. It prevents the worker from claiming new tasks. It is not a process kill and does not promise to interrupt Python code, a provider request, or an external side effect already in progress.

## Defined behavior

- A stop request is persisted in the application database and is observed by later claim attempts, including attempts from a newly created worker instance.
- A task already executing when stop is requested is allowed to return through its normal completion path. This avoids pretending that an external operation was cancelled when it may already have committed remotely.
- After the active handler returns, the worker does not claim another task while the stop switch remains enabled.
- Scheduled content dispatch is skipped after an active task returns if the durable stop switch is enabled.
- Operators must inspect durable task/workflow state after stopping. If an external side effect has an ambiguous outcome, reconcile it against the external system before retrying; do not blindly replay it.

## Explicit non-guarantees

- Stop does not forcibly terminate synchronous handlers or cancel in-flight HTTP requests.
- Stop does not roll back a side effect that has already reached an external service.
- A successful stop-control response confirms the durable switch was written; it does not prove all active work has stopped.

## Verification

The tests in tests/test_worker_control.py cover persistence across worker instances, preventing new claims, and the in-flight contract: the active task is allowed to finish, while the next queued task remains queued. Provider-specific cancellation, bounded timeouts, and external outcome reconciliation remain separate requirements and must be tested by each adapter before being described as supported.
