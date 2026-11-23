# H2/H3 Continuation Audit — 2026-11-23

**Repository baseline:** `main` at `d15c45e4f72a2928e97476944ee7a5a83a3a2d54`.
**Method:** GitHub source inspection only. No local checkout or local test execution was available during this checkpoint.

## H2 — Recovery and Fault Tolerance

### Verified implementation on baseline
- Durable workflow checkpoints and step-attempt records with digest-only evidence.
- Lease/fencing-token checks guard durable state transitions; heartbeat loss prevents continued ownership.
- Safe interrupted steps are resumable; ambiguous external side effects transition to `unknown_outcome` / reconciliation-required rather than automatic replay.
- Cancellation is durable and observed at execution boundaries; a stale worker cannot finalize after lease loss.
- RetryPolicy validates bounded exponential backoff and Retry-After, limits attempts, and restricts retries to allow-listed task types and transient error identifiers. Current allow-list is deliberately narrow (`demo.echo`).

### Remaining H2 gaps / acceptance gates
- **Generic hard task deadline/process isolation is not implemented.** A thread timer cannot safely terminate an in-flight handler. Subprocess adapters must terminate/reap their child and adapters must enforce connect/read deadlines.
- Restart/supervisor behavior and host-level process restart policy require deployment/device acceptance; source-level worker recovery is not equivalent to verified service restart.
- External-operation timeout must preserve ambiguity and reconcile; it must not become an automatic retry unless idempotency is explicitly proven.

### H2 disposition
**Partial—not complete.** Recovery, lease fencing, cancellation, unknown outcomes, and bounded retry primitives are present. Hard deadline/process isolation and deployment-level restart acceptance remain.

## H3 — Intelligence and Decision Engine

### Verified source modules
- `gpi.py`: Goal-to-Prompt conversion to a strictly validated WorkOrder; server-side risk derivation; prompt treats user goal as untrusted; generation does not execute tools.
- `work_order.py`: structured work-order contract.
- `capability_gaps.py`: capability-gap assessment.
- `awi_planner.py`, `workflow_plan.py`: bounded deterministic dependency planning.
- `plan_revision.py`, `replanning.py`, `replan_cycle.py`: proposal-based revision with bounded cycles (maximum 3) and human review; no automatic dispatch.
- `validation.py`, `revision_review.py`, `revision_integration.py`: read-only structural validation and digest-bound review/preview; does not authorize execution.

### Remaining H3 gaps / acceptance gates
- Verify end-to-end integration of WorkOrder → capability assessment → DAG plan → authorized execution, with one canonical contract and persisted revision identity.
- Confirm tool/model selection criteria and capability evidence are consistent across API and worker; tests should cover mismatched/partial plans.
- Replan on failures only when evidence supports a change, preserve revision/digest chain, and enforce bounded/no-progress stopping.
- Review integration PR #526 and PR #511 after CI and source-level conflict checks; do not merge draft PRs based on status alone.

### H3 disposition
**Partial—not complete.** Core GPI, capability-gap, DAG, and bounded review/replanning primitives exist. Full integrated intelligence-to-execution contract and failure-driven plan-revision validation remain.

## Next safe implementation sequence
1. Finish H2 hard-deadline design with process-isolation requirements; do not add unsafe thread-based timeout.
2. Reconcile PR #526 after dependency #518 merged; verify all exact-head checks and review findings.
3. Audit PR #511 persistence and plan revision contract; ensure digest/version/owner boundaries and migration compatibility.
4. Close remaining H3 integration gaps with tests before advancing to H4 security and H5 memory.
