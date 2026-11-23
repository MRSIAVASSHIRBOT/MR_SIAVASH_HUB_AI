# H2 — Deadlines, Cancellation, and Isolation Contract

Status: implementation contract; not yet implemented by this document.
Verified foundations include typed retry policies, allow-listed retryable task types, leases/fencing, worker stale recovery, workflow attempt bounds, and provider/render-specific timeout handling. Existing active PRs #529, #531, #535, and #542 address distinct recovery/retry guardrails; review their tests before merge.

## Deadline model
Every blocking handler/provider adapter must declare a deadline appropriate to its operation:
- Connect timeout (where network I/O is involved).
- Read/write or operation timeout.
- Overall deadline budget for the attempt.
- Maximum input/output bytes and response size.
- Cancellation semantics (cooperative, safe termination, or not cancellable).
- Side-effect classification and idempotency/reconciliation contract.

A task deadline is a budget, not permission to kill an operation without understanding its effects. Child operations must not exceed the remaining parent deadline.

## Timeout outcome classification
- Known local operation terminated safely before any external effect: terminal failure or retry-wait if policy allows.
- Provider request rejected before acceptance: classified by adapter evidence.
- External request accepted but response lost/timeout: `unknown_outcome`; reconcile by provider request ID/idempotency key, no replay.
- Cancellation requested while external effect may be in flight: `unknown_outcome` or `reconciliation_required`, not ordinary cancelled-success.
- Deadline reached while worker/lease is lost: stale worker cannot finalize; reconcile persisted state and fencing token.

## Isolation guidance
- Use native timeouts on HTTP/DB/subprocess APIs when they truly bound the underlying operation.
- Do not use a thread timeout and claim that the blocked thread or side effect stopped.
- Process isolation may be appropriate for local CPU-bound/untrusted computation, but only with bounded IPC, explicit cleanup, and no shared mutable execution state.
- External side-effect adapters remain responsible for idempotency keys and provider-specific reconciliation.
- FFmpeg and ffprobe should retain their explicit subprocess timeouts and cleanup behavior; avoid duplicating or weakening them.

## Retry contract
- Retry only typed transient errors from a documented allow-list.
- The retry policy must cap attempts, base delay, maximum delay, Retry-After, and total retry time with absolute configured limits.
- Exponential backoff must not overflow or exceed the absolute cap.
- A retry requires safe idempotency or proof the external effect was not accepted.
- A terminal, permanent, malformed, prohibited, or ambiguous error is not retryable.
- No automatic retry after an unknown outcome.

## Test matrix
- Handler without declared timeout is rejected or uses a safe documented default.
- Connect/read/overall deadlines are enforced by the actual adapter.
- Subprocess timeout terminates and waits for child; no orphan process remains.
- Cancellation before claim, during local handler, and during external request are distinguished.
- Parent deadline is propagated; child cannot extend it.
- Attempts, delays, Retry-After, and total retry duration respect absolute caps.
- Unknown external outcome is reconciled without duplicate submission.
- Stale lease/fencing prevents old worker finalization.
- Timeout/error logs contain sanitized code and no raw payload/secret.
- Resource bounds and cleanup are verified under failure.

## Implementation sequence
1. Complete review/merge of the active bounded retry/recovery PRs as the owner chooses.
2. Inventory each handler/provider and record operation type, timeout, idempotency, and cancellation.
3. Add deadline contract and enforce at adapter boundaries.
4. Add typed timeout/error classification and reconciliation states.
5. Add safe isolation only for operations that can be terminated without side-effect ambiguity.
6. Test timeout, cancellation, lease loss, process cleanup, retry budget, and no duplicate side effects.
