# H7 — WorkOrder Acceptance and Evidence Bridge

Status: implementation contract proposal; not implemented by this document.
Related existing foundations: typed WorkOrder, planning/capability assessment, workflow tool-outcome evaluation, deterministic correction-plan proposal, bounded plan revision/review.

## The missing integration
The current workflow evaluator explicitly scopes its report to tool-execution outcomes. A successful tool step does not prove the overall goal or all WorkOrder acceptance criteria were satisfied. This bridge defines how to join these layers without letting the model self-certify.

## Canonical criterion identity
Each WorkOrder acceptance criterion should receive a stable `criterion_id` during validation/normalization. The criterion text is retained in the WorkOrder; the ID is used for references.
- Criterion IDs are unique, normalized, bounded, and immutable for a WorkOrder revision.
- Revision changes that alter criterion meaning require a new ID; unchanged criteria retain IDs.
- The original WorkOrder digest and revision are recorded with the evaluation.

## Evidence contract
Each criterion evaluation record should contain:
- `criterion_id`, criterion digest, and WorkOrder revision.
- `status`: passed / failed / unknown.
- Evidence references and SHA-256 digest(s), source type, timestamp, and verifier identity.
- A bounded reason code and optional sanitized summary.
- `confidence` only if its meaning and calibration are defined; confidence alone cannot convert unknown to passed.

Evidence sources must be allow-listed. Model-generated claims may suggest evidence to inspect but cannot be authoritative evidence. Missing evidence remains unknown. Evidence invalidated by changed input/revision becomes stale and requires reevaluation.

## Aggregation rules
- ACCEPT only when every required criterion is passed with valid, current evidence.
- REJECT if any required criterion has verified failure evidence.
- REVIEW_REQUIRED if any required criterion is unknown, stale, conflicting, or has an unsupported evidence source.
- Optional criteria are clearly marked and do not silently affect required-criterion totals.
- Evaluation is deterministic for identical validated inputs and evidence records.

## Correction bridge
- Failed criterion → repair proposal with cause/evidence references; do not automatically retry.
- Unknown/stale/conflicting criterion → gather evidence or reconcile; no replay of ambiguous side effects.
- Revision proposal must reference the prior WorkOrder digest, criterion IDs, evidence report digest, and revised plan digest.
- No-progress detection compares plan/evidence digests; unchanged proposal is not a new iteration.
- Replanning cycle remains bounded and review-only until separately authorized.
- A correction proposal never changes grants, policy, or workflow state.

## Suggested API contract (versioned)
A read-only evaluation request references:
- WorkOrder revision/digest
- workflow/run identity
- evidence reference IDs (not raw payloads)
- expected criteria IDs

Response:
- report schema version and report digest
- criterion states and sanitized evidence summaries
- overall decision: accept / reject / review_required
- correction proposal (bounded, non-executable)
- `execution_started=false`, `permissions_changed=false`

## Test matrix
- All required criteria passed with fresh valid evidence → accept.
- One required criterion failed with valid evidence → reject and repair proposal.
- Missing/unknown evidence → review_required, never pass.
- Stale WorkOrder/evidence digest → reject or review_required, no stale success.
- Evidence source not allow-listed or malformed → validation failure.
- Duplicate/unknown criterion IDs and unbounded evidence references → validation failure.
- Changed criterion meaning in revision → new criterion identity; unchanged IDs preserved.
- Same inputs produce deterministic report and digest.
- Unknown external outcome yields reconciliation, not retry.
- Replanning limit reached/no progress → stop and report.
- Evaluation/correction cannot dispatch tools or change permissions.

## Implementation order
1. Criterion identity and versioned WorkOrder digest.
2. Evidence reference schema and allow-listed verifier registry.
3. Evaluation aggregator and stable report digest.
4. Correction proposal bridge to revision service with digest binding.
5. API read-only endpoint and owner access checks.
6. UI evidence review, provenance display, and stale/conflict warnings.
7. Contract tests for all states and authorization/privacy boundaries.


## Implemented owner-scoped evidence API

The authenticated endpoint `POST /agent/work-orders/plans/{plan_id}/evidence/evaluate` now evaluates evidence against the exact encrypted, owner-scoped plan revision. It revalidates the envelope, WorkOrder schema, AWI plan schema, canonical plan digest, criterion coverage, and the owner scope before invoking any verifier.

The first trusted adapter is intentionally narrow: `hub.workflow_step.v1` reads a persisted Hub workflow step for the same owner and checks its terminal state and output/failure digest. It can mark a criterion as passed or failed only when the criterion uses the exact machine-verifiable form `workflow_step_succeeded:<step_key>`, the AWI plan declares that same step ID as covering that criterion, and the persisted workflow step name matches one of that plan step's declared capabilities. All other criterion descriptions, capability mismatches, non-terminal states, foreign/unknown workflows, stale WorkOrder digests, and digest mismatches remain unknown/review-required. Caller-supplied status labels are not accepted.

The report is read-only, audited with metadata-only fields, and explicitly scoped to the declared acceptance criteria. An `accept` report is **not** a claim that the entire natural-language goal has been achieved; broader semantic goal completion still requires additional independent verifiers and owner review. The endpoint never executes, retries, authorizes, or changes permissions.


## H19 — Deterministic correction proposal boundary

The evidence endpoint also returns `work_order_correction_proposal.v1`. It is derived only from the verified criterion states and binds to both the WorkOrder digest and the evidence report digest. A verified failed criterion produces a proposal to prepare a reviewed correction; unknown, stale, or conflicting evidence produces a gather/reconcile recommendation. Optional criteria do not create repair actions. The proposal is informational only: no WorkOrder revision is created, no Workflow changes, no retry starts, no permissions change, and owner review is mandatory.
