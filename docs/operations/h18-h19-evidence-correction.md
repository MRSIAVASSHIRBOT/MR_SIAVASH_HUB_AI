# H18/H19 — Owner-Scoped Workflow Evidence and Correction Proposals

## Scope

The canonical H10 API remains the single entry point:

`POST /agent/work-orders/plans/{plan_id}/evidence/evaluate`

This implementation extends the existing owner-scoped, encrypted-plan evaluation path. It does not add a parallel route.

## H18 — Trusted workflow-step evidence

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

Other natural-language criterion descriptions are deliberately not accepted by this first verifier. A successful tool call alone is not proof that the overall semantic goal was completed.

## H19 — Correction proposal

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
