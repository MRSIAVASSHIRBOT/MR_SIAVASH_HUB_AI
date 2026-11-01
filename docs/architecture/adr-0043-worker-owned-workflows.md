# ADR-0043: Worker-owned Agent Workflow Execution

- Status: Partially implemented; atomic cross-table terminal transitions and full fault-injection coverage remain open
- Phase: 4.5 — Workflow Dispatch and Cancellation
- Date: 2026-11-01

## Context

The durable workflow runner currently creates a Job and a Workflow, acquires a lease, and executes AgentCore steps within the HTTP request handler. The generic pull-driven WorkerEngine is separate and supports only registered TaskRecord handlers. Generic Job cancellation changes the Job state, but there is no single worker-owned state machine coordinating cancellation with the workflow run and its current step.

Simply registering the existing request-scoped runner as a handler is unsafe: the original AgentPlanRequest contains tool arguments, and current workflow recovery deliberately avoids persisting raw prompts, arguments, and outputs. A worker cannot safely resume after process restart unless the execution input has an explicit storage and privacy design.

## Decisions

### 1. Submission and execution are separate

Implemented on the current feature branch: the HTTP endpoint validates and plans the request, reserves idempotency, creates the Job/Workflow, stores bounded encrypted input, and returns a queued response. It does not execute tools synchronously.

Only a worker holding the current lease/fencing token may advance durable workflow state. The existing explicit pull-driven model remains in place until a separately reviewed runtime lifecycle is added.

### 2. No raw payload persistence by accident

The explicit execution-input repository is implemented and used by the queue/dispatch path. Tool arguments may contain private data, so the default design is to persist a bounded, versioned, encrypted payload only when encryption key management is available and configured. Otherwise the API must require a caller-provided resume payload or fail closed; it must not store plaintext tool arguments merely to make background execution convenient.

Workflow metadata, logs, checkpoints, and audit events retain digests and identifiers rather than raw inputs or outputs. Secret values are rejected from durable input storage unless a specific secret-reference mechanism is implemented.

### 3. Idempotency is atomic with submission

Workflow submission accepts a bounded Idempotency-Key. A unique key is scoped to the authenticated owner and endpoint. Within one SQLite transaction, the service must reserve the key, create the Job and Workflow, and bind their IDs and request digest.

- Same owner, same key, same digest: return the existing workflow without executing it again.
- Same owner and key but different digest: return HTTP 409.
- Concurrent duplicate submissions: exactly one reservation wins; losers read and return the existing record.
- No raw request body is stored in the idempotency record.

### 4. Cancellation is a durable request, not an optimistic state flip

Cancellation is represented as a durable signal associated with the Job/Workflow. The worker checks task state and lease ownership at step boundaries. Queued cancellation updates the linked Job and Workflow; active external steps are moved to recovery review rather than reported as cleanly cancelled. Full atomic terminal-state coordination and process-level cancellation remain under verification. Cancellation cannot forcibly reverse an external side effect already in flight.

For an interrupted external step whose outcome cannot be verified, the step becomes unknown_outcome and requires reconciliation. The system must not label it cleanly cancelled or automatically replay it. Safe deterministic steps may be resumed only according to their explicit retry policy.

Job and Workflow terminal transitions must be committed atomically where they share a database, with lease/fencing checks applied to the transition.

### 5. No background thread started implicitly by an API request

The API remains a submit/status interface. Worker execution is explicitly invoked by a worker process or an operator-controlled run loop. Application startup does not silently begin executing queued work.

### 6. State machine and audit requirements

Expected lifecycle:
- submit: queued
- worker claim: running
- user cancellation before dispatch: cancelled
- safe interrupted work: paused / resumable
- uncertain external outcome: recovery_required
- successful completion: succeeded
- terminal known failure: failed

Audit events record actor, Job ID, Workflow ID, transition, and reason code. They must not contain request payloads, secrets, or tool outputs.

## Implementation sequence

1. Owner-scoped idempotent submission: implemented in the existing submission repository.
2. Encrypted bounded execution input: implemented and used by queued submission and dispatch.
3. Worker-owned dispatch: implemented on this branch through WorkerEngine's leased dispatch path.
4. Worker-owned resume: implemented as a validation-and-requeue operation; execution happens on a worker.
5. Cancellation: queued cancellation is synchronized; active external outcomes are classified for recovery. Additional fault-injection and atomicity work remains.
6. Run the full test suite and confirm CI for the latest head; no green result is claimed until GitHub Actions reports it.
7. Keep this PR draft until the remaining lifecycle and fault-injection checks pass.

## Acceptance criteria

- API response time is bounded by validation and durable submission.
- Repeated idempotent requests do not create duplicate Jobs/Workflows.
- A cancelled workflow dispatches no subsequent step.
- No raw tool arguments are stored in plaintext as a side effect of this refactor.
- A valid fencing lease is required for every worker-owned state advance.
- Job and Workflow terminal states cannot diverge after a committed transition.
- Ambiguous side effects require reconciliation; no exactly-once guarantee is claimed for arbitrary external systems.
- Existing tests for owner isolation, migration compatibility, recovery, and safe resume remain green.
