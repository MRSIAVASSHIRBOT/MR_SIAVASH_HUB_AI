# H1 Workflow Engine Audit — 2026-11-23

**Status:** Audit baseline completed; engineering phase remains open.
**Scope:** Workflow DAG planning, durable execution, checkpoint/resume, and dependency-state correctness.
**Evidence inspected:** `backend/mrhub/agents/workflow_plan.py`, `workflow_runner.py`, `workflow_repository.py`, `jobs/recovery.py`, `docs/operations/agent-workflow-dag.md`, `tests/test_workflow_plan.py`, `tests/test_agent_workflow_repository.py`, `tests/test_recovery.py`, `tests/test_agent_workflow_recovery_regressions.py`, `tests/test_workflow_runner_lease.py`.

## Existing behavior confirmed by source inspection

- The bounded DAG planner validates duplicate/unknown/self dependencies and cycles, then produces a deterministic topological order.
- Independent ready nodes retain request order as the tie-breaker.
- Request identifiers and durable runtime positions are distinct. Execution/checkpoint callbacks use runtime positions; request identifiers identify request tools.
- Runner persists step metadata and input digests, and validates ordered tool coverage before dispatch.
- Recovery stores checkpoint digests rather than raw payloads/output bodies.
- Request digest and step input identity are checked on resume.
- Safe interrupted work can be resumed; ambiguous external side-effect outcomes are marked unknown and require reconciliation rather than blind replay.
- Existing tests cover deterministic order, invalid graphs, resume position, completed-step replay prevention, definition/request digest mismatch, unknown outcomes, concurrency claims, and recovery metadata privacy.

## H1 gaps / design decisions

1. **Stable step identity:** Current durable step records and checkpoint interfaces use numeric runtime positions. Request step IDs are positional (`step-1` etc.) and can shift if the request is edited. Add a persisted opaque stable ID (e.g. UUID/ULID generated once when the plan is created) and retain runtime position only as scheduling/display order.
2. **Identity mapping:** Persist an explicit mapping of stable ID, request ID, runtime position, tool name, canonical input digest, and definition/schema version. Resume must validate identity and dependencies against the stored workflow definition.
3. **Dependency state:** Persist dependency outcomes per stable ID. A step is runnable only when every dependency is `succeeded`; failed/unknown dependencies must fail closed and block descendants. Distinguish `pending`, `running`, `succeeded`, `failed`, `blocked`, and `unknown_outcome`.
4. **Resume behavior:** Resume should skip stable IDs already `succeeded`, resume only eligible safe steps, and reconcile any ambiguous external effect before dispatch. No replay solely because the runtime position changed.
5. **Termination contract:** Define terminal workflow decisions for all-success, known failure, blocked descendants, cancellation, worker interruption, retry exhaustion, and reconciliation-required states.
6. **Partial/unknown state:** Persist transitions atomically, reject invalid transitions, and never interpret missing/contradictory checkpoint data as success.

## Proposed implementation sequence

- H1.1: Add stable step IDs to the durable workflow definition and checkpoint schema (versioned migration).
- H1.2: Add ID-keyed transition/read APIs while retaining legacy numeric compatibility during migration.
- H1.3: Add dependency-state gating and blocked-descendant propagation.
- H1.4: Rework resume decision to use stable identity and skip succeeded steps.
- H1.5: Add tests for reordered definitions, stable-ID preservation, completed-step non-replay, dependency failure/unknown gating, missing/duplicate IDs, legacy migration, and terminal-state consistency.
- H1.6: Run focused tests, full backend tests, lint/type checks, CI; resolve failures before merge.

## Acceptance criteria for H1

- Stable step identity is persisted and survives plan serialization/reordering.
- Runtime position is not used as the sole durable identity.
- Every dependency is successful before a step starts.
- Succeeded steps are never replayed during resume.
- Unknown outcomes are reconciled before retry.
- Invalid, incomplete, or contradictory workflow state fails closed.
- Workflow termination states and step states have documented, tested transitions.
- Focused and full test suites plus CI pass on the exact candidate commit.

## Validation limitations

This audit was performed through GitHub source/API access. The local project checkout, dependency installation, local pytest, lint, and live worker execution were unavailable in this session. No test pass is claimed. This document is an audit/design artifact, not an implementation completion.
