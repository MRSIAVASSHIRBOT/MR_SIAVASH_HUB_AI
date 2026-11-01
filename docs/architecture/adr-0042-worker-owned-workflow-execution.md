# ADR-0042: Worker-Owned Agent Workflow Execution and Cancellation

- Status: Proposed implementation contract
- Date: 2026-11-01
- Scope: Issue #5; follow-up to ADR-0041
- Decision owners: project maintainers

## Context

The workflow submission endpoint currently plans and executes the workflow in the HTTP request. The generic WorkerEngine deliberately excludes `agent.workflow` because it does not yet have a safe dispatch path. Job and workflow creation, idempotency reservation, and resource binding are not yet one atomic operation. Generic Job cancellation can also update the Job without coordinating the linked workflow.

The existing privacy boundary is intentional: raw goals, tool arguments, and tool outputs are not stored in workflow tables. A durable worker cannot safely infer these values from digests.

## Decision

Do not wire `agent.workflow` into the generic worker until the following invariants are implemented together.

### 1. Canonical worker lease

- WorkerEngine claims the Job and owns its only execution lease.
- WorkflowRunner receives that lease and must not acquire a second lease for the same Job.
- Every workflow/step/checkpoint transition remains fenced by the same lease.
- The worker must not mark a workflow Job successful merely because a handler returned; workflow and Job terminal transitions must be coordinated and verified.

### 2. Durable execution input boundary

- Do not persist plaintext workflow requests, tool arguments, or outputs in the workflow metadata tables, logs, audit events, exception messages, or worker result JSON.
- A digest alone is not executable input and must never be treated as one.
- If asynchronous restart-safe execution requires persisted input, use a separately versioned encrypted payload envelope with authenticated encryption, task/workflow/owner binding as associated data, bounded size, explicit expiry, and deletion on terminal retention policy.
- Encryption keys must come from deployment configuration or a supported secret manager; never generate a fixed fallback key, hardcode a key, or silently fall back to plaintext.
- If key configuration is absent or invalid, submission of workflows requiring durable payload storage must fail closed before reserving the job.
- Key rotation, ciphertext versioning, backup/restore behavior, and deletion semantics must be documented and tested before enabling production use.

### 3. Atomic submission

Within one database transaction, create or bind the idempotency reservation, queued Job, worker execution row, workflow run, ordered steps, and payload-envelope metadata. A failure at any point must roll back all these records. Matching idempotent submissions return the original workflow; a different request digest under the same user/key returns conflict.

### 4. Cancellation protocol

- Cancellation is owner-authorized and represented as a durable request visible to the worker.
- Queued work can transition to cancelled without dispatch.
- Running workers check cancellation and lease ownership between steps and immediately before beginning a step.
- If cancellation arrives during an external side effect, do not assume the side effect was stopped. Mark the step/workflow as requiring reconciliation when its outcome is ambiguous; never automatically replay it.
- Job and workflow state transitions must be coordinated transactionally or through a recoverable state machine; do not leave a cancelled Job with a workflow still marked running.
- Cancellation is cooperative. It cannot guarantee interruption of a tool call already executing.

### 5. Recovery and failure semantics

- Safe, known-not-started steps may be retried according to explicit policy.
- Interrupted external side effects become `unknown_outcome` / `recovery_required` until reconciled.
- A stale lease or failed fencing check prevents all further durable writes by the stale worker.
- Worker exception text and raw payloads are never persisted; use stable, sanitized error codes.

## Required acceptance tests

1. Submission returns queued identifiers without running any tool in the request handler.
2. Job, workflow, steps, idempotency binding, and payload metadata commit atomically; fault injection at every write boundary leaves no partial submission.
3. Duplicate matching idempotency key returns the same workflow; a changed request under the same key returns conflict.
4. Worker uses the single canonical lease; a second worker cannot dispatch the same Job.
5. Cancellation before dispatch prevents tool invocation.
6. Cancellation between safe steps stops the next step and leaves coherent terminal states.
7. Cancellation during an external side effect never claims that the side effect was cancelled; ambiguous results require reconciliation.
8. Worker restart and expired-lease recovery do not replay an ambiguous external side effect.
9. Missing/invalid encryption key fails closed; ciphertext is bound to task/workflow/owner and cannot be swapped across records.
10. Owner isolation applies to submit, status, cancel, resume, and reconciliation.
11. Logs, audit records, task results, and workflow tables contain no raw request, tool arguments, or outputs.
12. Ruff, dependency audit, and the complete test suite pass on the exact commit under review.

## Rollout

Keep this feature disabled until the complete acceptance suite passes. Do not merge the draft PR or modify `main` as part of this ADR. Implement in small commits on the existing feature branch, with CI evidence tied to the exact head SHA.
