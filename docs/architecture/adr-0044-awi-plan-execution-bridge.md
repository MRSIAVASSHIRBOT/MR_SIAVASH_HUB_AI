# ADR-0044: Safe AWI Plan-to-Execution Bridge

- **Status:** Proposed design; implementation not authorized by this ADR alone
- **Date:** 2026-11-22
- **Scope:** GPI work orders, AWI execution plans, CGI capability assessment, ToolRegistry, and durable agent workflows
- **Decision owners:** Project maintainers

## Context

The authenticated `POST /agent/work-orders/plan` endpoint is deliberately planning-only. It creates a validated `WorkOrder`, generates a bounded `ExecutionPlan`, checks whether declared capability names exist in the registered tool catalog, and returns explicit flags showing that authorization and execution did not occur.

The current `PlanStep` contract contains a step identifier, description, dependencies, required capability identifiers, acceptance-criteria coverage, and verification text. It does **not** contain a registered tool name or a typed tool payload. A capability-presence report is not an authorization decision, and a natural-language description is not an executable instruction.

The repository already has a durable execution path:

1. `POST /agent/workflows` accepts an explicit `AgentPlanRequest`.
2. The API validates the requested tools against the server-owned `ToolRegistry` and policy.
3. The API encrypts the request and atomically creates the workflow, queued task, step metadata, and optional idempotency binding.
4. `WorkerEngine` claims the `agent.workflow` task and owns its canonical lease.
5. `WorkflowWorkerHandler` decrypts the owner-bound payload and delegates to `AgentWorkflowRunner`.
6. The runner uses `AgentCore`; the registry validates each payload and re-evaluates server-side permissions and policy at invocation.

The durable path has important guarantees that must be preserved: AES-GCM payload envelopes bound to workflow/task/owner identifiers, task-scoped idempotency, fenced worker leases, owner-scoped reads and mutations, cooperative cancellation, recovery checkpoints, and explicit reconciliation for uncertain external side effects.

A direct conversion from AWI prose to tool arguments would bypass the typed boundary. A second executor, an alternate worker, or a direct handler call would duplicate or bypass existing controls. The bridge therefore needs to translate a reviewed plan into the existing request contract, not create a new execution engine.

## Decision

### 1. Planning never authorizes execution

- A GPI work order and AWI plan are proposals, not permission grants.
- A declared risk class is advisory. The server must derive risk from the original goal and re-evaluate registered tool policy from server-owned definitions.
- CGI capability presence means only that a matching name exists in the registry. It does not prove that the current owner has the required permission or that policy allows invocation.
- Client fields such as `user_approved`, `granted_permissions`, `execution_ready`, or `risk_class` must never be accepted as authority.
- The planning endpoint remains read-only with respect to tools, permissions, workflows, and jobs.

### 2. Require explicit, typed step bindings

Introduce a strict server-validated binding contract. A binding associates one AWI `step_id` with one exact registered `tool_name` and a JSON-object `payload`.

For the first implementation:

- Every executable plan step must declare exactly one required capability.
- The binding's `tool_name` must exactly match that capability identifier. No description, fuzzy match, alias guess, or model-generated tool name is accepted.
- Every plan step must have exactly one binding; duplicate, missing, extra, or unknown step bindings are rejected.
- The caller supplies or confirms the payload. Model-generated prose is never parsed into tool arguments.
- The server resolves the exact `ToolDefinition`, validates the payload with its registered `input_model`, and serializes only the validated JSON representation.
- Unknown tools, malformed JSON, unexpected fields, oversized values, and schema failures are rejected before a task is created.

The first bridge is intentionally limited to one through five bound steps, matching the existing `AgentPlanRequest.tools` limit. Supporting larger plans requires a separate change to the request and workflow contracts, not a silent truncation.

### 3. Preserve the dependency graph deterministically

The existing `AgentWorkflowRunner` executes a bounded sequential tool list; it does not execute an arbitrary DAG or perform parallel scheduling.

Before creating a workflow:

- Validate the stored plan digest and re-validate the complete dependency graph.
- Produce a stable topological order. Ties must be resolved deterministically, for example by the original plan order.
- Reject cycles, missing dependency identifiers, duplicate bindings, or a binding whose step is not in the stored plan.
- Persist the original step identifiers, dependency edges, and their mapping to ordered tool calls inside the encrypted execution envelope.
- Execute sequentially in topological order for v1. Parallel execution is out of scope.

A plan whose steps cannot be represented by the v1 sequential contract must remain planning-only; it must not be weakened or silently rewritten.

### 4. Freeze and re-check the tool contract

At binding validation, compute a canonical digest for the registered tool input schema and record the tool name, schema digest, and registry contract version in the encrypted execution envelope.

At worker dispatch, before invoking a handler:

- Resolve the tool again from the server-owned registry.
- Recompute the schema digest and require an exact match.
- Revalidate the payload against the current input model.
- Fail closed if the tool is missing, disabled, redefined, or has a changed input schema.
- Never deserialize a handler reference, import path, module name, or executable object from client or model data.

The registry remains the only source of handlers, input/output schemas, risk classification, permission requirements, and external-side-effect declarations.

### 5. Re-evaluate authorization and policy at execution time

At submission and again immediately before each tool invocation:

- Resolve active permission grants for the authenticated owner from `ToolPermissionService`.
- Evaluate the current `ToolDefinition` through the registry's `PolicyEngine`.
- Reject missing or expired grants. Never auto-grant permissions because a plan requires them.
- Revalidate the input payload and output schema at the registry boundary.
- Stop if the worker lease is lost or cancellation is requested.

**V1 allow-list:** only actions for which the current server policy returns `ALLOW` may be queued. Actions returning `REQUIRE_APPROVAL` or `DENY` remain non-executable.

The current execution call path does not provide a durable, owner-authenticated, one-time approval proof for an AWI-bound action. Therefore v1 must not pass a client-provided approval boolean or attempt to simulate approval through an ordinary workflow resume.

A later approval-capable version requires a separate server-side approval record bound to owner, workflow, exact tool name, canonical payload digest, schema digest, expiry, and one-time consumption. The worker must verify and consume that record atomically immediately before invocation. Approval of one payload must not authorize a changed payload or another tool.

### 6. Persist plans and execution inputs without plaintext

The current planning endpoint does not persist a durable plan record. The bridge must not trust a client to resend an arbitrary plan and claim it is the original model-generated plan.

Add an owner-scoped plan repository with:

- Opaque plan identifier and authenticated owner identifier.
- Schema/definition version, creation time, expiry, status, and canonical plan digest.
- Encrypted WorkOrder and ExecutionPlan payload; raw goals, descriptions, and tool payloads must not be stored in plaintext workflow metadata.
- Bounded payload size and explicit retention/deletion rules.
- Owner-scoped lookup and mutation. An identifier alone is never authorization.
- State transitions that prevent execution after expiry, after prior consumption, or after a conflicting update.

The existing payload-envelope implementation uses authenticated encryption and resource-bound associated data. Extend that implementation with a versioned plan-resource binding (or an equivalently reviewed envelope contract); do not create a second cryptographic implementation, reuse unrelated identifiers ambiguously, add a plaintext fallback, or generate a fallback key.

A stored plan digest must be recomputed from canonical serialized content before use. Ciphertext authentication and digest checks are both required; the digest alone is not tamper protection.

### 7. Submit execution through the existing durable workflow

A proposed authenticated endpoint is:

- `POST /agent/work-orders/{plan_id}/execute`
- Request: an exact set of step bindings and an `Idempotency-Key`.
- Response: queued workflow/task identifiers and status; no synchronous tool execution.

The service must load the plan by both plan identifier and authenticated owner, verify expiry and state, validate bindings, re-check policy, and build a strict `AgentPlanRequest` from the validated bindings.

The operation must atomically consume the eligible plan, reserve the owner-scoped idempotency key, create the queued task and workflow, persist ordered step metadata, and save the encrypted execution envelope. Matching retries return the original workflow; a changed request under the same key returns conflict. A plan cannot create multiple independent workflows by replay.

The implementation must delegate to the existing `WorkflowRecoveryRepository`, `WorkerEngine`, `WorkflowWorkerHandler`, and `AgentWorkflowRunner`. It must not invoke `ToolDefinition.handler` from an API route, add a parallel executor, start background work in the web process, or bypass canonical worker leases.

The encrypted workflow envelope must retain enough immutable context to validate the plan digest, step-to-tool mapping, tool schema digests, and topological order during dispatch and recovery. The worker derives the `AgentPlanRequest` from that envelope only after its version, authentication tag, owner/task/workflow binding, and schema validations pass.

### 8. Keep recovery and privacy semantics intact

- A worker lease is canonical. Every workflow and step transition remains fenced by the same lease.
- Safe known-not-started steps may follow the existing explicit retry policy.
- An interrupted external side effect or ambiguous outcome remains `unknown_outcome` / `recovery_required`; never automatically replay it.
- Cancellation remains cooperative and does not claim to undo an in-flight tool call.
- Resume, cancellation, status, and reconciliation remain owner-scoped.
- Audit events contain only allow-listed metadata and counts/digests; never include raw goals, plan text, payloads, credentials, provider output, or tool output.
- Terminal payload deletion follows the documented retention policy and preserves only the minimum metadata needed for audit and recovery.

## Proposed lifecycle

```text
GPI/AWI planning
      |
      v
Persist owner-bound, encrypted plan (short expiry)
      |
      v
User supplies exact step -> tool -> typed payload bindings
      |
      v
Validate plan, graph, registry schema, owner permissions and policy
      |
      +---- DENY / REQUIRE_APPROVAL ----> remain non-executable
      |
      v
Atomically consume plan + idempotency + encrypted workflow payload
      |
      v
WorkerEngine claims task and canonical lease
      |
      v
WorkflowWorkerHandler validates envelope and registry schema
      |
      v
AgentWorkflowRunner -> AgentCore -> ToolRegistry
      |
      v
Fenced checkpoint / terminal state / recovery or reconciliation
```

## Required acceptance tests

### Plan and binding integrity
1. A plan is retrievable only by its authenticated owner.
2. Unknown, expired, consumed, or tampered plan identifiers fail closed.
3. The canonical plan digest is re-computed and checked before bindings are accepted.
4. Every step has exactly one binding; duplicate, missing, extra, and unknown bindings are rejected.
5. Tool names must exactly match the step's single declared capability.
6. A payload cannot contain fields outside the registered input schema.
7. A changed tool schema digest invalidates the binding before handler invocation.
8. Cycles and unknown dependencies are rejected; stable topological ordering is deterministic.
9. Plans exceeding the v1 five-step limit remain planning-only.

### Policy and permissions
10. A capability present in the catalog but not authorized for the owner is not executable.
11. A missing, expired, or revoked permission grant blocks execution.
12. A policy result of `REQUIRE_APPROVAL` or `DENY` creates no executable workflow.
13. No client-supplied approval or permission field can change a policy decision.
14. A prohibited goal is rejected before provider inference and before provider quota is consumed.

### Durability and execution
15. Planning and binding-validation endpoints invoke no tool handler.
16. Task, workflow, ordered steps, encrypted payload, plan consumption, and idempotency binding are atomic.
17. A matching idempotency replay returns the original workflow; a changed request conflicts.
18. No handler runs in the API request; execution starts only after WorkerEngine claims the task.
19. A handler runs only through the existing registry and canonical worker lease.
20. Lease loss, cancellation, and worker restart preserve current workflow fencing semantics.
21. An uncertain external side effect is never automatically replayed.
22. Owner isolation covers plan retrieval, binding, execution, status, cancellation, resume, and reconciliation.

### Privacy, crypto and operations
23. Missing/invalid encryption keys fail closed before task reservation.
24. Ciphertext cannot be swapped across plans, owners, workflows, or tasks.
25. Plaintext goals, plan content, tool payloads, credentials, and outputs do not appear in logs, audit events, task descriptions, or workflow metadata.
26. Payload size, plan lifetime, binding count, and step count are bounded.
27. Expired/consumed plan payloads are deleted according to the approved retention policy.
28. Ruff, security scans, focused unit tests, integration tests, and the full suite pass on the exact reviewed commit.

## Rollout gates

1. Merge the GPI/AWI planning and CGI registry changes only after exact-head CI and security review pass.
2. Implement plan persistence and the binding contract in a separate, reviewable change.
3. Keep the execution bridge behind a disabled-by-default feature flag until all acceptance tests pass.
4. Enable only v1 low-risk actions with `PolicyDecision.ALLOW`; do not enable high-risk or external-side-effect actions until the durable approval design is separately implemented and reviewed.
5. Validate API/worker operation, encryption-key configuration, recovery, cancellation, and monitoring in a non-production environment.
6. Obtain explicit owner approval for any Production deployment and associated cost before merging changes that trigger automatic deployment.

## Non-goals

- Executing AWI descriptions as shell commands, Python, SQL, or arbitrary code.
- Inferring tool arguments from natural-language prose.
- Letting a model grant permissions, approve its own plan, or select an unregistered handler.
- Direct handler invocation from the API or model-provider process.
- Unbounded autonomous loops, dynamic tool installation, parallel workflow execution, or automatic replay of uncertain external actions.
