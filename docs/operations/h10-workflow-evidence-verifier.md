# H10 — Trusted workflow-step evidence and read-only correction proposals

## Phase mapping

This is an extension of the existing H10 WorkOrder evidence-evaluation API and a scoped implementation slice across the active H0–H32 sequence:

- **H10 — Task Lifecycle Engine:** evaluate evidence against the encrypted, owner-scoped persisted GPI/AWI plan.
- **H18 — Evaluation & Verification:** verify a durable workflow step using trusted server-owned evidence adapters, exact plan bindings, and fail-closed UNKNOWN/REVIEW_REQUIRED outcomes.
- **H19 — Self-Correction & Replanning:** produce digest-bound, read-only correction proposals for explicit owner review.

It does not complete H10, H18, or H19. Remaining H10 gates include broader WorkOrder revision lifecycle support, additional independently reviewed evidence adapters, the complete negative evidence matrix, and EL_AI E8 consumer integration. H18 still needs broader evaluation coverage and production acceptance across relevant workflows. H19 still needs an owner-approved correction-to-replan lifecycle with independently verified outcomes; this slice intentionally does not execute a correction or retry.

The repository also contains an older 73-phase baseline with different numbering. It remains historical input for a later crosswalk and does not override this active H0–H32 sequence.

## Scope

The canonical H10 API remains the single entry point:

`POST /agent/work-orders/plans/{plan_id}/evidence/evaluate`

This implementation extends the existing owner-scoped, encrypted-plan evaluation path. It does not add a parallel route.

## Trusted workflow-step evidence adapter

The default server composition registers one narrow verifier:

- source type: `agent_workflow_step`
- verifier ID: `hub.workflow_step.v1`
- accepted criterion form: `workflow_step_succeeded:<step_id>`

Before verification, the API revalidates the encrypted persisted plan, canonical plan digest, WorkOrder schema, AWI schema, and exact acceptance-criterion coverage. It derives criterion-to-step IDs and capability allow-lists from the persisted AWI plan.

The verifier checks:
- the workflow belongs to the authenticated owner;
- the referenced step exists in that workflow;
- the step ID is declared by an AWI step that covers the criterion;
- the persisted tool name matches a capability declared by that exact AWI step;
- the step is terminal and its output/failure evidence digest matches the reference.

Only a succeeded step with a matching digest can pass this criterion. A failed step produces a digest-bound failure result. Missing, foreign, non-terminal, mismatched, or unverifiable evidence remains UNKNOWN / REVIEW_REQUIRED.

### One-to-one persisted plan binding

A workflow can be bound to a persisted GPI/AWI plan by supplying its `work_order_plan_id` to the existing `POST /agent/workflows` request. The server decrypts and validates the owner-scoped plan, then requires an exact match for the WorkOrder goal, every stable tool-step ID, declared dependencies, one-tool capability mapping, and full acceptance-criterion coverage.

The workflow row and plan consumption are committed in the same SQLite transaction. The plan transitions from `active` to `consumed` and records that exact `workflow_id`; a plan can never be consumed by a second workflow. A failed binding rolls back workflow/task creation. An ordinary workflow without this association is not accepted as evidence for a persisted plan, even when the owner, step ID, and tool name happen to match.

Evidence evaluation rechecks the owner-scoped consumed-plan/workflow association. Consumed plans retain only the association metadata after their original TTL; encrypted plan content is erased at expiry, and evidence evaluation is rejected after that deadline.

Other natural-language criterion descriptions are deliberately not accepted by this first verifier. A successful tool call alone is not proof that the overall semantic goal was completed.

## Read-only correction proposal

Every evidence report now includes `work_order_correction_proposal.v1`, bound to both the WorkOrder digest and evidence report digest.

- A verified failed required criterion recommends preparing a reviewed correction.
- Unknown, stale, or conflicting evidence recommends gathering or reconciling evidence.
- Optional criteria do not create correction tasks.

The proposal is informational only. It does not modify the plan or workflow, execute tools, retry an ambiguous side effect, change permissions, or promote memory. Owner review remains mandatory.

## Acceptance coverage

Tests cover:
- default registry wiring and the successful owner-owned workflow-step path;
- unknown/unowned workflow references;
- criterion-to-plan step mismatch;
- AWI capability mismatch;
- non-terminal step handling;
- correction proposal digest stability and required/optional criterion handling;
- explicit no-execution, no-retry, no-workflow-mutation, and no-permission-change flags.

The evidence API continues to be audited using metadata-only fields. No raw tool output, prompt, or evidence payload is added to the audit event.
