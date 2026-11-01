# ADR-004.1: Unified Job Engine, Workflow Recovery, and Resume

- Status: Accepted
- Phase: 4.1 architecture / 4.2 implementation
- Date: 2026-11-01
- Scope: local-first runtime, SQLite persistence, pull-driven workers

## Context

The repository already has a task lifecycle, a pull-driven worker, and a persistent agent workflow ledger. These components currently have overlapping lifecycle responsibilities. Workflow execution is not yet owned by the Job Engine, worker recovery treats stale running tasks as failed, and the worker has no durable lease/heartbeat ownership. The workflow ledger is also initialized independently of the versioned schema migrator.

Recent commits added atomic workflow step transitions and replay protection. This ADR preserves those guarantees and extends them rather than replacing them.

## Decisions

### 1. One lifecycle owner

The Job Engine is the sole owner of task lifecycle and queue eligibility. Workflows are durable aggregates attached to jobs; they do not introduce a second queue or worker pool. Agent/API entry points submit work and read state. A Workflow Runner, invoked by a claimed worker, performs bounded step execution and persists each transition.

### 2. Payload minimization

Persist only the minimum metadata required to identify, audit, and recover a workflow:
- request/input digests, not raw prompts or tool payloads;
- step identity, status, timestamps, bounded error codes, and attempt counts;
- checkpoint version and digest, not executable serialized user input;
- references only when a separately approved storage mechanism exists.

If restart recovery requires an input that was intentionally not persisted, the workflow pauses and requests that input again. Any approval bound to the previous input fingerprint must be revalidated after input changes. Secrets, raw prompts, tool arguments, and tool outputs must not be written to audit metadata.

### 3. Fail closed for ambiguous external outcomes

A step whose external side effect may have occurred but whose outcome cannot be verified is marked `unknown_outcome`. It is not eligible for automatic retry or resume. The system must require reconciliation or explicit operator/user resolution. A retry is permitted only when the handler contract establishes that the operation is safe to retry or the downstream service provides a stable idempotency guarantee.

Exactly-once execution across arbitrary external systems is not claimed. The design provides durable deduplication and effectively-once behavior only where downstream idempotency is supported.

### 4. Durable ownership

Worker ownership is represented by a database-backed lease with owner, expiry, heartbeat, and an execution fencing token. Claims and state changes use short SQLite write transactions and compare-and-set predicates. A process-local lock is not considered cross-process ownership.

### 5. Checkpoints and resume

A checkpoint is committed only after a step has a validated durable result. Resume starts from the first incomplete safe step; succeeded steps are not replayed. Corrupt, missing, stale, or input-mismatched checkpoints fail closed. Recovery must distinguish a worker that died before dispatch from one that may have completed an external side effect.

### 6. Versioned migrations

All persistent schema changes are introduced through immutable, checksummed SQLite migrations. Existing rows and existing workflow ledger data must remain intact. Runtime components must not independently create or alter production tables.

## Workflow lifecycle

`queued -> running -> paused | waiting_approval | recovery_required | succeeded | failed | cancelled`

Only explicit, validated transitions are allowed. `recovery_required` may return to `queued` only after reconciliation establishes that resumption is safe. Terminal states are immutable.

## Step lifecycle

`pending -> running -> succeeded | failed | retry_wait | unknown_outcome | cancelled`

A completed step cannot transition back to running. `unknown_outcome` is not equivalent to `failed`.

## Implementation sequence

1. Add a versioned schema migration and migration regression tests.
2. Introduce durable lease/heartbeat and fencing semantics.
3. Add idempotency records and request deduplication.
4. Add checkpoint and recovery contracts.
5. Add safe resume orchestration and workflow runner.
6. Route agent workflows through the Job Engine.
7. Add fault-injection, concurrency, migration, and security regression tests.
8. Update operational and architecture documentation.

## Acceptance criteria

- A restart after a committed step resumes at the next safe step.
- An ambiguous external result is never replayed automatically.
- Duplicate submissions with the same idempotency scope/key do not create duplicate jobs.
- Two workers cannot hold valid ownership for the same execution concurrently.
- Expired leases are recovered only with fencing and outcome classification.
- Missing required input causes a request for re-entry rather than payload reconstruction from logs.
- Existing databases migrate without loss of task, approval, audit, or workflow data.
- All schema changes are applied through the versioned migrator.
