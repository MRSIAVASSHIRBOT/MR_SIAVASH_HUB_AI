# H10 — Digest-bound WorkOrder evidence evaluation

Status: foundation implemented; verifier adapters and EL_AI integration remain pending.
This document uses the current 73-phase roadmap numbering. Older Hub documents that use H7 for self-evaluation are historical labels and do not redefine H10.

## Goal

Keep three different claims separate:

1. A task reached a terminal status.
2. A structurally valid result envelope exists.
3. A required WorkOrder acceptance criterion was independently verified.

Only the third can contribute to an accepted WorkOrder decision. A model-authored statement, task status, plan-step description, or unverified digest is not sufficient evidence.

## Contract in this change

WorkOrderSnapshot binds evaluation to a WorkOrder ID, positive revision, lowercase SHA-256 digest, and up to 12 unique criterion IDs (ac_001 through ac_012).

EvidenceReference stores only an opaque evidence reference, source/verifier identifiers, a SHA-256 digest, a timezone-aware observation timestamp, and the exact WorkOrder digest/revision. It accepts no caller-supplied pass/fail status and stores no evidence payload.

EvidenceVerifierRegistry resolves an exact (source_type, verifier_id) pair registered by trusted server-side application code. A missing verifier, verifier exception, malformed return, or digest mismatch becomes unknown. A stale WorkOrder digest/revision becomes stale. Conflicting verified outcomes become conflicting.

The report is deterministic for identical inputs and verifier outputs. It returns only criterion IDs, evidence IDs and bounded reason codes; it does not return raw evidence, source references, or private WorkOrder text.

## Decision rules

- accept: every required criterion is passed.
- reject: at least one required criterion has verified failed evidence.
- review_required: any required criterion is missing, unknown, stale, or conflicting.
- Optional criteria are reported but do not block required-criterion acceptance.
- Unknown evidence never counts as a pass.
- A report never starts execution, retries work, changes permissions, or applies a correction.

## Security and integration boundary

The registry is a server-side composition concern. A public request, Telegram message, model output, or stored plan cannot register or replace a verifier. A verifier must independently resolve the opaque source reference and recompute/confirm the evidence digest before returning passed or failed.

This change adds the deterministic contract and its unit tests only. It does not register production evidence verifiers, add a public evaluation endpoint, change the current telegram_agent_plan.v1 response, or connect EL_AI. Until those pieces exist, E8 must continue reporting execution coverage only and goal_satisfaction: not_evaluated.

## Required next integration work

1. Produce a canonical WorkOrder digest and revision in a backward-compatible, versioned Hub planning response.
2. Persist the digest/revision with the owner-scoped EL_AI plan; reject stale evidence after plan revision.
3. Add verifier adapters for explicitly allow-listed, independently readable evidence sources.
4. Add an owner-scoped read-only evaluation route with audit and privacy-safe error handling.
5. Connect EL_AI E8 to the report contract and test both projects with consumer-driven contract fixtures.
6. Keep semantic acceptance disabled until at least one verifier adapter and the complete negative authorization/stale/conflict test matrix are integrated.

## Verification boundary

The tests in this change cover deterministic aggregation, required/optional criteria, missing/unregistered verifiers, failures, stale references, conflicts, malformed verifier outputs, digest mismatch, invalid references, duplicate identifiers, bounded input, report privacy, and deterministic report digests.

They do not prove any external evidence source, live Telegram flow, Hub deployment, or semantic correctness of a model-produced result.

## Owner-scoped API candidate — PR #641 (2026-11-27)

The current implementation candidate adds:

- `POST /agent/work-orders/plans/{plan_id}/evidence/evaluate`.
- It loads the plan only through the authenticated owner's encrypted plan repository lookup, requires an active record, decrypts it with plan/owner associated data, revalidates WorkOrder and ExecutionPlan schemas, and recomputes the stored plan digest before evaluation.
- The evidence snapshot is bound to the exact persisted **plan** digest (not yet a separate canonical WorkOrder-only digest) and a single immutable plan revision. Acceptance criteria are mapped in order to ac_001... identifiers and returned to the authenticated owner.
- The request accepts bounded opaque evidence references only. It forbids caller-supplied pass/fail status, raw evidence payloads, and verifier definitions.
- Verifiers resolve only from the server-side EvidenceVerifierRegistry initialized by the application composition root. The registry currently starts empty. Until trusted production adapters are registered, unknown/unregistered references return review_required; nothing is accepted from client claims.
- Each evaluation writes an allow-listed audit event with decision, bounded counts and report digest. Raw source references, evidence payloads and WorkOrder text are not written to audit.

**Status:** Candidate implementation in PR #641; not yet merged or accepted by mainline CI. This is progress toward the owner-scoped API gate, not full H10 completion.

### Remaining H10 gates

1. Define a canonical WorkOrder-only digest/revision field in a backward-compatible, versioned planning response; the current API binds to the immutable persisted plan digest.
2. Implement and independently review production verifier adapters for approved evidence sources.
3. Add consumer-driven contract fixtures and an E8 integration in EL_AI; until that passes, E8 must remain execution-coverage-only and goal satisfaction not evaluated.
4. Run exact-head CI, post-merge CI and any required live integration acceptance.

## Owner-scoped API candidate — PR #641 (2026-11-27)

The current implementation candidate adds:

- `POST /agent/work-orders/plans/{plan_id}/evidence/evaluate`.
- It loads the plan only through the authenticated owner's encrypted plan repository lookup, requires an active record, decrypts it with plan/owner associated data, revalidates WorkOrder and ExecutionPlan schemas, and recomputes the stored plan digest before evaluation.
- The evidence snapshot is bound to the exact persisted **plan** digest (not yet a separate canonical WorkOrder-only digest) and a single immutable plan revision. Acceptance criteria are mapped in order to ac_001... identifiers and returned to the authenticated owner.
- The request accepts bounded opaque evidence references only. It forbids caller-supplied pass/fail status, raw evidence payloads, and verifier definitions.
- Verifiers resolve only from the server-side EvidenceVerifierRegistry initialized by the application composition root. The registry currently starts empty. Until trusted production adapters are registered, unknown/unregistered references return review_required; nothing is accepted from client claims.
- Each evaluation writes an allow-listed audit event with decision, bounded counts and report digest. Raw source references, evidence payloads and WorkOrder text are not written to audit.

**Status:** Candidate implementation in PR #641; not yet merged or accepted by mainline CI. This is progress toward the owner-scoped API gate, not full H10 completion.

### Remaining H10 gates

1. Define a canonical WorkOrder-only digest/revision field in a backward-compatible, versioned planning response; the current API binds to the immutable persisted plan digest.
2. Implement and independently review production verifier adapters for approved evidence sources.
3. Add consumer-driven contract fixtures and an E8 integration in EL_AI; until that passes, E8 must remain execution-coverage-only and goal satisfaction not evaluated.
4. Run exact-head CI, post-merge CI and any required live integration acceptance.
