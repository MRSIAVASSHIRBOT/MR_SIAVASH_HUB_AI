# Agent Workflow DAG and Durable Recovery

## Request contract

The authenticated AgentCore request accepts up to five tool requests. Each request tool receives a stable request identifier based on its position in the submitted array:

- The provider-selection step is `step-1`.
- Tool request items are `step-2` through `step-6`.

A tool item may declare `depends_on`:

- Omitted or `null`: preserve the legacy sequential dependency on the preceding request item.
- An explicit empty list (`[]`): the tool is independent of other request tools. Provider selection remains an implicit prerequisite.
- A list such as `["step-4"]`: wait for the referenced request tool as well as provider selection.

Dependencies must identify an item in the same request. Self-dependencies, repeated dependencies, unknown identifiers and dependency cycles are rejected before planning or execution. The graph is bounded by the five-tool request limit.

## Deterministic planning

The server materializes the request graph and runs the shared bounded topological planner. Ready steps are ordered deterministically, preserving request order when multiple steps become ready at the same level.

The plan's ordered step identifiers remain request identifiers. The runtime assigns a separate durable execution position:

- Position 1 is provider selection.
- Positions 2 onward follow the validated topological order.

This distinction is important: a request item such as `step-5` may execute at durable runtime position 2. Execution callbacks, workflow step rows, checkpoints and resume decisions use the durable position; request identifiers continue to select the corresponding tool and payload.

## Durable step identity

Each tool step stores an SHA-256 input digest derived from its request step identifier, tool name and canonical payload. The digest does not store the payload itself.

On resume, the runner rebuilds the validated order and compares the expected tool identity with the persisted step definition. A mismatch blocks resume before a worker is queued. Legacy workflow rows with a null input digest retain their previous step-kind/name compatibility check.

The workflow request digest uses a canonical serialization that omits newly introduced optional defaults when they are absent. In particular, omitted `depends_on` and an empty default `required_capabilities` do not change the identity of legacy requests. Explicit dependencies and non-empty capability requirements remain part of the digest.

## Capability and authorization boundaries

Capability-gap evaluation reports whether required identifiers exist in the registered ToolRegistry catalog. It is a presence report only.

The following remain separate checks:

1. Capability availability in the registry.
2. Owner permission grants.
3. Policy authorization and approval requirements at planning and again at invocation.

A registered capability is not by itself permission to invoke a tool. Tool handlers are not called by the capability assessment function.

## Execution and recovery guarantees

- The executor fails closed when the graph is missing, incomplete, duplicated or not in deterministic topological order.
- The runner persists the exact topological sequence before dispatch.
- Safe steps may be retried according to the existing recovery state machine.
- External-side-effect steps with ambiguous outcomes remain quarantined for reconciliation; they are not blindly replayed.
- Checkpoints store digests rather than executable tool payloads or output bodies.
- Request and per-step input identity are checked again before resume.

## Operational validation

The focused tests cover legacy sequential behavior, explicit dependencies, invalid/cyclic graphs, topological execution, resume positions, input-digest mismatch rejection and legacy digest compatibility.

A test being present in the repository is not evidence that it passed. Exact-head CI must complete successfully before merge. Production deployment and any associated service cost require separate owner approval.
