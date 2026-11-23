# H6 — Tool Execution Lifecycle Contract

Status: design and acceptance contract; not an implementation claim.
Current verified foundations from the H6 audit include a registry, typed input/output models, allow-listed handlers, policy checks, pull-driven worker, persistent task states, leases, fencing, idempotency, cancellation, and retry controls.

## Lifecycle
A tool execution attempt should have explicit, auditable states:
1. `registered` — schema and metadata validated before registry insertion.
2. `input_validated` — payload validated against declared input schema and size bounds.
3. `authorized` — policy decision bound to actor, tool, input digest, context, and risk.
4. `queued` — eligible for execution under queue/concurrency limits.
5. `claimed` — worker claim and lease/fencing identity established.
6. `started` — handler execution began.
7. `result_received` — handler returned or exception was classified.
8. `output_validated` — result passes output schema and size constraints.
9. `finalized` — durable terminal state recorded.

Terminal outcomes include succeeded, failed, cancelled, blocked, unknown_outcome, and reconciliation_required. Do not collapse unknown external outcomes into failure if a retry might duplicate the side effect.

## Required immutable attempt metadata
- tool name/version from the registry
- execution/attempt ID and parent task/workflow/step IDs
- owner/actor identity reference
- input digest (not raw input)
- policy decision reference and policy version
- lease/fencing identity
- started/finished timestamps and duration
- bounded status/error code
- output digest and validation outcome (not raw output by default)

## Boundary checks
- Registry insertion validates name, metadata, input/output model, handler callable, risk, side-effect and permission fields.
- Input/output payloads have strict byte/field/collection bounds and reject unknown fields where the schema is strict.
- Authorization is rechecked at the execution boundary, not inferred from planning or registration.
- Cancellation is cooperative for handlers that can stop safely. For external effects, cancellation may produce unknown outcome and require reconciliation.
- Timeouts are adapter-specific and documented; a generic thread timeout must not be presented as stopping the underlying operation.
- Retries require a typed transient failure, a bounded retry policy, and an idempotency/reconciliation contract.
- Worker/process isolation must not be added without explicit state/lease/side-effect semantics.
- Handler exceptions must map to sanitized error codes; sensitive exception text is not returned to clients.

## Lifecycle invariants
- No tool executes before validation and server-side authorization.
- A tool cannot widen its own permissions or rewrite the authorization decision.
- Successful handler output is not trusted until output validation completes.
- Unknown/ambiguous side effects are not replayed automatically.
- Attempt records are append-only or immutable once terminal; corrections use new records.
- The final state must be durably recorded or explicitly surfaced as unknown.
- Trace instrumentation failure cannot trigger duplicate execution.

## Test matrix
- Invalid registry definitions rejected; valid registration stable and versioned.
- Input schema rejects malformed/oversized/unknown fields.
- Output schema rejects malformed/oversized results; tool state is not falsely succeeded.
- Authorization denied before handler invocation; permissions not mutated.
- Actor/owner mismatch rejected.
- Cancellation at queued/running stages is classified safely.
- Lease expiry and fencing reject stale workers.
- Retry count, backoff, deadlines, and attempt IDs remain bounded.
- Non-idempotent side-effect timeout yields unknown outcome and no automatic replay.
- Output and error sanitization prevent secret/raw payload leakage.
- Concurrency and queue limits verified.
- Event/trace linkage preserves task→workflow→step→tool→attempt chain.

## Implementation order
1. Strengthen registry validation (PR #546).
2. Add typed attempt/lifecycle state contract without breaking legacy handlers.
3. Bind authorization and idempotency to attempt creation.
4. Add adapter timeout/cancellation/unknown-outcome classification.
5. Persist sanitized attempt metadata and trace linkage.
6. Add lifecycle tests and operator timeline UI.
