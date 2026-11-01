# ADR-0043: Fenced Workflow Cancellation and Crash Recovery

- **Status:** Proposed in PR #7
- **Date:** 2026-11-02
- **Scope:** Durable agent workflows executed by the pull-driven WorkerEngine

## Context

A cancellation request can race with task claiming, tool execution, lease expiry, and worker shutdown. Treating cancellation as an immediate terminal task transition can hide an unfinished workflow from stale-worker recovery. Treating lease loss as cancellation is also unsafe: a stale worker must not finalize state owned by a successor.

## Decisions

1. **Queued workflow cancellation is immediate.** If the workflow is still queued, atomically cancel the task and workflow, remove the encrypted queued payload, and mark any idempotency binding failed.
2. **Running workflow cancellation is a durable request.** Persist `cancellation_requested` on the worker execution record while leaving the task in `running`. The active runner observes that flag at tool boundaries and finalizes the task/workflow cooperatively.
3. **Lease loss is not cancellation.** A worker that loses its fencing token stops execution and must not finalize the task, workflow, or result. The current lease owner or stale-worker recovery owns the next transition.
4. **Recovery does not replay uncertain external side effects.** If a worker dies while an external-side-effect step is active, mark the step `unknown_outcome`, move the workflow to `recovery_required`, and require explicit reconciliation. Safe interrupted steps may be retried only when the workflow has not been cancelled.
5. **Cancellation after a crash is recovered explicitly.** If the durable cancellation request survives a worker crash and no external outcome is uncertain, recovery marks the workflow/task cancelled and deletes the retained encrypted payload. If an external outcome is uncertain, recovery prioritizes reconciliation and marks the task as waiting for approval.
6. **Terminal worker bookkeeping is fenced.** Results and completion timestamps are persisted only for the current, unexpired lease. A cancelled workflow is never rewritten as succeeded by the post-handler path.
7. **Operational summaries are metadata-only.** Queue counts, workflow state counts, expired lease counts, and queue age may be exposed to authenticated operators; task descriptions, prompts, tool payloads, results, credentials, and ciphertext are excluded.

## Invariants

- A stale worker cannot commit a step checkpoint or terminal job transition.
- User cancellation does not authorize replaying a possibly completed external action.
- A worker crash cannot erase a durable cancellation request.
- A terminal cancellation cannot be overwritten by a late success result.
- Ambiguous external outcomes require reconciliation before resumption.
- Owner scoping remains mandatory for user-facing workflow reads and mutations.

## Verification

The PR adds tests for cancellation before execution, cancellation between tools, cancellation in the worker-claim window, durable running-cancellation intent, and crash recovery with both safe and uncertain active steps. CI must pass on the latest PR head before this ADR is accepted or the PR is merged.

## Operational follow-up

- Exercise API + database + worker together in a clean test environment.
- Verify worker shutdown and lease-expiry behavior under concurrent cancellation.
- Review recovery-required workflows and expired leases in the job summary.
- Keep PR #7 unmerged until latest CI is green and the remaining release-readiness review is complete.
