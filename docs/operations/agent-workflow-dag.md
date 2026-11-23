# Agent Workflow DAG and Durable Recovery

## Request contract

The authenticated AgentCore request accepts up to five tool requests. The provider-selection step has the reserved durable identity `step-1`. Each tool request may supply a stable `step_id`; when omitted, the server derives the legacy positional identity `step-{request-index}` (for example, `step-2`).

Caller-supplied tool identifiers are the durable identity used by the DAG and must be unique, bounded identifiers. Supplying them allows a caller to preserve step identity when the request array is reordered. Positional identifiers remain supported for compatibility with older clients and stored workflows.

A tool item may declare `depends_on`:

- Omitted or `null`: preserve the legacy sequential dependency on the preceding request item, using that item's effective step identifier.
- An explicit empty list (`[]`): the tool is independent of other request tools. Provider selection remains an implicit prerequisite.
- A list such as `["step-4"]`: wait for the referenced request tool as well as provider selection.

Dependencies must identify an item in the same request. Self-dependencies, repeated dependencies, unknown identifiers and dependency cycles are rejected before planning or execution. The graph is bounded by the five-tool request limit.

## Deterministic planning

The server materializes the request graph and runs the shared bounded topological planner. Ready steps are ordered deterministically, preserving request order when multiple steps become ready at the same level. AgentCore validates that the dependency plan matches the original request graph before any handler is invoked.

The ordered plan retains request-level step identifiers. The runtime assigns a separate durable execution position:

- Position 1 is provider selection.
- Positions 2 onward follow the validated topological order.

For example, request step `step-5` may execute at durable position 2. The persisted workflow row stores both the runtime position (`step_number`) and stable request identity (`step_key`). Runner callbacks use runtime positions only as an execution-local index; the Runner resolves that index through the validated topological mapping before reading or writing a durable step. Checkpoints and resume decisions retain the stable step identity.

## Durable step identity

Each tool step stores an SHA-256 input digest derived from its request step identifier, tool name, canonical payload and dependency identities. The digest does not store the payload itself.

On resume, the runner rebuilds the validated order and compares the expected tool identity, input digest and dependency edges with the persisted step definition. A mismatch blocks resume before a worker is queued. Already-succeeded steps are skipped by stable identity for current workflow definition versions. Legacy workflow rows retain their historical numeric resume contract and compatibility checks.

The workflow request digest uses canonical serialization. Legacy optional defaults are omitted when absent; explicit dependencies and non-empty capability requirements remain part of the request identity. Fully identified DAG requests can be canonicalized independently of request-array ordering when every tool has an explicit `step_id` and explicit `depends_on` declaration.

## Capability and authorization boundaries

Capability-gap evaluation reports whether required identifiers exist in the registered ToolRegistry catalog. It is a presence report only.

The following remain separate checks:

1. Capability availability in the registry.
2. Owner permission grants.
3. Policy authorization and approval requirements at planning and again at invocation.

A registered capability is not by itself permission to invoke a tool. Tool handlers are not called by the capability assessment function. GPI WorkOrders and AWI ExecutionPlans remain planning artifacts; a natural-language plan description is not an executable tool binding. See ADR-0044 for the typed, policy-checked bridge boundary.

## Execution and recovery guarantees

- The executor fails closed when the graph is missing, incomplete, duplicated or not in deterministic topological order.
- The runner persists the exact topological sequence before dispatch.
- A worker interruption classifies known-safe steps as `retry_wait`; resuming still requires an owner-initiated resume through the API.
- Safe provider-selection and safe-tool steps are bounded to three total attempts, including the initial attempt. Exceeding the limit terminalizes the step, workflow and linked task as failed.
- External-side-effect steps with ambiguous outcomes are recorded as `unknown_outcome` and require explicit reconciliation; they are not blindly replayed.
- Checkpoints store digests rather than executable tool payloads or output bodies.
- Request and per-step input identity are checked again before resume.
- A successful workflow cannot be finalized until every persisted step has succeeded.

## Operational validation

The focused tests cover legacy sequential behavior, explicit dependencies, invalid/cyclic graphs, topological execution, stable-ID resume, already-completed step skipping, input-digest mismatch rejection, legacy digest compatibility, interrupted external-side-effect reconciliation and bounded safe-step attempts.

A test being present in the repository is not evidence that it passed. Exact-head CI must complete successfully before merge. Production deployment and any associated service cost require separate owner approval.
