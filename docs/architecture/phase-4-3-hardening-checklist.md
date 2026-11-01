# Phase 4.3 Hardening Checklist

This checklist tracks the 19-step workflow hardening sequence. Status distinguishes code that exists from work that has been verified on the current PR head.

## Cancellation, fencing, and recovery

- [x] **1. Cancellation error contract:** map invalid workflow state to HTTP 409; preserve owner-scoped 404 behavior.
- [x] **2. Cancellation boundaries:** test cancellation before the first tool, between tools, during the worker claim/dispatch window, and while a safe tool is active.
- [x] **3. Crash recovery:** persist running cancellation intent and recover after worker interruption; do not replay an active external side effect with unknown outcome.
- [x] **4. Idempotency and lease fencing:** preserve atomic idempotency creation and fenced state commits; distinguish lease loss from user cancellation.
- [x] **5. Fault-injection gate (current branch head):** latest-head CI passed after cancellation boundary, crash recovery, and read-only readiness tests; keep rerunning CI for every subsequent code change.
- [x] **6. State-machine enforcement:** task transitions are allow-listed; workflow step completion checks run state, step ownership, attempt state, and lease.
- [x] **7. Restart recovery:** stale worker records are reconciled on the next explicit worker poll.
- [x] **8. Retry policy:** transient retry uses bounded exponential backoff and an explicit retry-safe task-type allow-list.
- [x] **9. Unknown external outcomes:** interrupted external-side-effect steps require explicit reconciliation rather than blind replay.

## Security and observability

- [x] **10. Ownership boundaries:** user-facing workflow access and mutations are owner-scoped; repository tests cover cross-owner isolation.
- [x] **11. Sensitive data controls:** workflow payloads are encrypted at rest; recovery metadata stores digests and bounded error codes, not executable inputs or outputs.
- [x] **12. API security tests:** authentication, request bounds, idempotency conflicts, owner-scoped history, and safe tool allow-list behavior have test coverage.
- [x] **13. Structured audit events:** audit metadata is explicitly allow-listed and bounded.
- [x] **14. Operational metrics:** worker summary reports queue counts, retry count, workflow-state counts, expired running leases, and oldest queued age.
- [x] **15. Readiness diagnostics:** `/health` reports liveness; `/ready` checks the existing schema read-only and reports a process-specific Worker heartbeat. `MRH_REQUIRE_WORKER_FOR_READINESS=true` makes a fresh heartbeat mandatory; stale heartbeats age out using `MRH_WORKER_HEARTBEAT_TIMEOUT_SECONDS`.

## Integration and release

- [x] **16. API + DB + Worker integration:** integration tests enqueue, process, inspect, cancel, and recover durable workflows.
- [x] **17. Concurrency tests:** existing tests cover competing step starts, multiple worker instances, heartbeats, and stale fencing tokens.
- [x] **18. Operational documentation:** ADR-0042 describes worker-owned execution; ADR-0043 records cancellation/recovery invariants.
- [ ] **19. Release gate:** keep PR in Draft until latest CI passes, cancellation/recovery tests pass on the latest head, and remaining readiness/security risks are reviewed.

## Acceptance criteria

1. CI passed on commit `e1e5a7ad173601fbb50a2619c81b030d63be4ac7`, including dependency audit, lint, and tests. Rerun before merge if any further code changes are pushed.
2. A cancellation request survives worker interruption and cannot be overwritten by late success.
3. Lease-losing workers cannot commit checkpoints, results, or terminal transitions.
4. Unknown external outcomes remain blocked from automatic replay until reconciled.
5. Workflow history and operational summaries do not disclose prompts, tool payloads, results, credentials, or ciphertext.
6. The release review records any accepted limitations before the PR is marked ready.
