# H1 Workflow Engine Audit — 2026-11-23

**Status:** Historical audit baseline; the gaps below were subsequently addressed by the H1 implementation recorded later in this document.
**Scope:** Workflow DAG planning, durable execution, checkpoint/resume, and dependency-state correctness.
**Evidence inspected:** `backend/mrhub/agents/workflow_plan.py`, `workflow_runner.py`, `workflow_repository.py`, `jobs/recovery.py`, `docs/operations/agent-workflow-dag.md`, `tests/test_workflow_plan.py`, `tests/test_agent_workflow_repository.py`, `tests/test_recovery.py`, `tests/test_agent_workflow_recovery_regressions.py`, `tests/test_workflow_runner_lease.py`.

## Existing behavior confirmed by the initial audit

- The bounded DAG planner validates duplicate/unknown/self dependencies and cycles, then produces a deterministic topological order.
- Independent ready nodes retain request order as the tie-breaker.
- Request identifiers and durable runtime positions are distinct. Execution/checkpoint callbacks use runtime positions; request identifiers identify request tools.
- Runner persists step metadata and input digests, and validates ordered tool coverage before dispatch.
- Recovery stores checkpoint digests rather than raw payloads/output bodies.
- Request digest and step input identity are checked on resume.
- Safe interrupted work can be resumed; ambiguous external side-effect outcomes are marked unknown and require reconciliation rather than blind replay.
- Existing tests cover deterministic order, invalid graphs, resume position, completed-step replay prevention, definition/request digest mismatch, unknown outcomes, concurrency claims, and recovery metadata privacy.

## Initial audit gaps (historical; superseded)

At the time of this audit, stable identity, dependency-state persistence, identity-keyed resume, and terminal-state consistency were identified as the next engineering targets. The acceptance criteria below were used to guide the follow-up implementation.

## Follow-up implementation: H1 completed

**Implemented and merged in PR #523** (`feat(workflows): complete identity-aware H1 workflow engine`; merge commit `25979d63482cd2b4f579ccd3dc0aef52c0334ca8`; PR head `cc2b1a47f25621ce48e582604c6cb826a9e824a4`).

- Added caller-defined stable tool step IDs while preserving position-derived identities for legacy requests.
- Bound request and input digests to stable identity; explicit IDs and dependencies remain digest-stable across harmless reordering.
- Persisted step keys and dependency edges alongside durable UUID step rows and legacy execution positions.
- Added migration V54 to backfill old workflow steps, sequential dependencies, checkpoint identities, and dependency readiness.
- Addressed step starts, attempts, completion, failure, reconciliation, checkpoints, and resume decisions by stable identity while retaining numeric compatibility.
- Enforced dependency readiness and blocked descendants of failed, ambiguous, or cancelled prerequisites.
- Kept ambiguous external outcomes in reconciliation-required state; reconciliation records an outcome but never re-invokes the external action.
- Resume skips every succeeded stable identity and validates version-3 definitions by identity/dependency mapping; historical definitions remain position-validated.
- Rejected inconsistent resume step ID/position mappings and prevented terminal success unless all workflow steps succeeded.

## Validation evidence

GitHub Actions passed on the exact PR #523 head `cc2b1a47f25621ce48e582604c6cb826a9e824a4`:

- Backend CI: 1,540 passed, 2 skipped; dependency audit and Ruff lint passed.
- CI on Python 3.11 and 3.12: 1,540 passed, 2 skipped on each version; build, packaged UI asset verification, and lint passed.
- Windows wheel smoke on Python 3.11 and 3.12 passed.
- Windows Launcher Validation passed.
- Video Render Integration (Linux and Windows FFmpeg/FFprobe) passed.
- Defensive Python Scan and Workflow Security Audit passed.

This is CI evidence for the exact PR head, not a claim of local execution or production deployment. No production deployment, external provider invocation, or publishing action is included.

## Acceptance criteria and outcome

- Stable step identity persists and survives harmless plan reordering: **implemented**.
- Runtime position is not the sole durable identity: **implemented with legacy compatibility**.
- Every dependency must be successful before a step starts: **implemented**.
- Succeeded steps are not replayed during resume: **implemented and regression-tested**.
- Unknown outcomes require reconciliation before continuation: **implemented**.
- Invalid, incomplete, or contradictory workflow state fails closed: **implemented and regression-tested**.
- Workflow and step terminal states are consistent: **implemented and regression-tested**.
- Focused and full test suites plus CI pass on the exact candidate commit: **CI passed as listed above**.

## Scope boundary

This document records H1 only. It does not certify H2–H10 or a production release. Later phases require their own implementation and verification evidence.
