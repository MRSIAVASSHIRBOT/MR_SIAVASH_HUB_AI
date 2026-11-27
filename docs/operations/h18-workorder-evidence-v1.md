# H18 — Digest-bound WorkOrder evidence evaluation

Status: owner-scoped read-only API and encrypted revision binding implemented on a feature branch; production verifier adapters and EL_AI E8 integration remain pending.
This document follows the v6 ecosystem roadmap: H18 is Evaluation & Verification. WorkOrder generation and plan revision are related to H6/H7; task identity and state lifecycle are H10.

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

The deterministic contract and owner-scoped read-only evaluation endpoint are implemented. The trusted verifier registry remains server-side and has no production evidence adapters by default. The plan API continues to keep private Hub state out of the public website and does not change the existing EL_AI `telegram_agent_plan.v1` contract. Until trusted production adapters and consumer tests exist, EL_AI E8 (Tool & Skill Interface) must not treat task execution coverage as semantic goal acceptance and `goal_satisfaction: not_evaluated`.

## Required next integration work

1. Implement an explicit WorkOrder/plan revision lifecycle for any future plan-edit or supersede operation. The current creation path persists revision 1 for both objects; it does not yet provide an edit endpoint or increment revisions.
2. Add independently reviewed verifier adapters for explicitly allow-listed, independently readable evidence sources. The registry intentionally remains fail-closed when no trusted adapter is registered.
3. Expose only a deliberately scoped, versioned evidence-evaluation contract to EL_AI E8; keep task execution coverage distinct from semantic acceptance and retain goal_satisfaction=not_evaluated until trusted verifier adapters and consumer tests exist.
4. Extend the negative matrix to cover every supported adapter's owner, source, digest, staleness, conflict, expiry and authorization failure paths.
5. Keep semantic acceptance disabled for external or non-deterministic criteria until trusted evidence adapters and cross-project acceptance gates pass.

## Verification boundary

The tests in this change cover deterministic aggregation, required/optional criteria, missing/unregistered verifiers, failures, stale references, conflicts, malformed verifier outputs, digest mismatch, invalid references, duplicate identifiers, bounded input, report privacy, and deterministic report digests.

They do not prove any external evidence source, live Telegram flow, Hub deployment, or semantic correctness of a model-produced result.

## Owner-scoped API and encrypted revision binding — PR #641 + revision-binding follow-up

The owner-scoped API was merged in HUB PR #641 at `4f684b8a8494ffe263db6769b312f884cd6df311`. A follow-up feature branch, `feat/h10-persisted-workorder-revisions-20261127`, adds explicit revision metadata to new encrypted plan records. The branch name is historical; this WorkOrder evidence slice belongs to H18 (with H6/H7 plan-versioning dependencies), not the roadmap's H10 Task Lifecycle Engine.

The current API provides:

- `POST /agent/work-orders/plans/{plan_id}/evidence/evaluate`, scoped to the authenticated owner.
- Full plan integrity validation: decrypt using the plan ID and owner ID as associated data, validate the WorkOrder and ExecutionPlan schemas, and recompute the parent plan digest.
- A separate canonical WorkOrder-only SHA-256 digest, which is checked against the validated WorkOrder JSON.
- Three metadata fields inside the encrypted payload: `work_order_revision`, `plan_revision`, and `work_order_digest`. Newly created records start at revisions 1/1. These fields are included in the parent plan digest and therefore protected by the same authenticated encrypted payload.
- Backward-compatible reads for older records that do not have these fields: they are interpreted as WorkOrder revision 1, plan revision 1, with a canonical digest recomputed from the decrypted WorkOrder. Partial metadata, invalid revisions, or a digest mismatch fail closed.
- Evidence references are evaluated against the persisted WorkOrder digest and revision, not hardcoded response constants. An evidence reference for an earlier revision is classified as stale.
- Audit writes only the decision, bounded counts and report digest. Raw source references, evidence payloads and WorkOrder text are not added to audit.
- Reports and correction proposals are read-only. They do not start execution, retry work, change permissions or apply a proposed correction.

No database schema migration is needed for this slice because revision metadata is held inside the existing encrypted payload. Existing payloads remain readable using the revision-1 compatibility rule.

**Important boundary:** this adds first-class persisted revision identity for newly created records, but it does not yet implement a plan-edit/supersede lifecycle or automatic revision increments. Production verifier adapters and the EL_AI E8 consumer integration also remain pending. H18 remains PARTIAL.

## Verification boundary

Current tests cover deterministic aggregation, required/optional criteria, missing/unregistered verifiers, verified failures, stale references, conflicts, malformed verifier outputs, digest mismatches, owner isolation, exact workflow/plan binding, caller-supplied status rejection, persisted non-default revisions, plan-creation metadata, legacy fallback and read-only behavior.

These tests do not prove an external evidence source, live Telegram flow, deployed Hub runtime, production semantic acceptance or physical-device acceptance.
