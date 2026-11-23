# H6/H7 Execution and Self-Evaluation Audit — 2026-11-23

Baseline `main`: `d15c45e4f72a2928e97476944ee7a5a83a3a2d54`.
Source inspection only; no local test execution.

## H6 — Execution Engine

### Verified
- Explicit tool registry and allow-list; unknown tool names are rejected.
- Tool definitions provide typed input/output Pydantic models, handlers, risk class, permissions and side-effect flags.
- Input and output validation are performed at registry boundaries.
- Policy checks run before invoking a tool; restricted permissions and high-risk/external actions are gated.
- Worker is pull-driven and executes registered handlers; startup does not automatically dispatch arbitrary queued work.
- Durable task state, leases/fencing, idempotency reservations, cancellation, retry policy and worker-stop control exist.
- Tests cover registered-only tools, schema/policy enforcement, worker lifecycle, retry behavior, worker stop, and idempotency/recovery integration.

### Gaps
- No universal Tool Lifecycle contract (registered → validated → authorized → running → result-validated → finalized) across every tool adapter verified.
- General handler isolation/process termination and hard deadlines remain open (see H2 audit).
- Concurrency and queue fairness/priority policies need evidence of configured global/per-tool bounds.
- Observability is fragmented between task/audit/agent model run records; unified execution trace linking workflow/step/tool/attempt is not proven.
- External adapters need consistent timeout, cancellation, and unknown-outcome reconciliation contract.

### H6 disposition
**Partial.** Strong registry and worker foundations exist; lifecycle, isolation, queue/concurrency and end-to-end trace acceptance remain.

## H7 — Self-Evaluation and Improvement

### Verified
- `agents/evaluation.py` defines deterministic acceptance criteria with passed/failed/unknown statuses and evidence digest validation; unknown criteria do not count as success.
- Evaluation is based on structured trusted application outcomes rather than self-certification by an LLM.
- `proposal_evaluation.py` provides read-only preflight checks for agent proposals.
- `plan_revision.py` creates additive review-only plan revisions, preserves completed step identities, and rejects malformed dependency graphs.
- `replan_cycle.py` bounds revision cycles (max 3) and requires review; it does not dispatch execution.

### Gaps
- Full linkage from initial WorkOrder acceptance criteria to final evidence and evaluation report is not verified.
- Failure correction strategies need a typed, evidence-backed mapping; evaluation and revision are separate components today.
- Quality dimensions beyond deterministic acceptance (decision quality, usefulness, completeness, efficiency) need explicit metrics and calibrated review.
- Lessons Learned storage/retrieval and approved reuse across later workflows are not verified.
- Regression tests must exercise partial evidence, stale digests, failed criteria, unknown criteria, revision exhaustion, and no-progress loops end-to-end.

### H7 disposition
**Partial.** Evidence-aware evaluation and safe bounded review-only revision exist; integrated correction/learning pipeline remains.

## Recommended next implementation sequence
1. Define shared ExecutionTrace IDs (task/workflow/step/tool/attempt) and lifecycle transitions, then wire logging without sensitive payloads.
2. Specify deadline/isolation/cancellation contracts for tool adapters and enforce them at adapter boundaries.
3. Establish concurrency and queue policy configuration and test limits under load.
4. Connect acceptance criteria, execution evidence, evaluation, and bounded revision via digest/versioned contracts.
5. Add Lessons Learned proposals with owner review, provenance, privacy filters, and retrieval tests; do not auto-write unverified lessons.
