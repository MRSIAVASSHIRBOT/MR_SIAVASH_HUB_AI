# Goal-to-Prompt and AWI Planning API

## Purpose

The authenticated `POST /agent/work-orders/plan` endpoint converts one natural-language goal into:

1. A bounded, schema-validated `WorkOrder` (Goal-to-Prompt Intelligence / GPI).
2. A dependency-aware `ExecutionPlan` (Autonomous Workflow Intelligence / AWI).
3. A capability assessment showing which requested capabilities are present in the owner's tool catalog.

This endpoint is a **planning-only** operation. It does not create a task, execute an agent, invoke tools, change permissions, approve an action, or perform an external side effect.

## Request

The caller must first authenticate through the Hub login flow and provide the resulting bearer token.

```http
POST /agent/work-orders/plan
Authorization: Bearer <session-token>
Content-Type: application/json
```

```json
{
  "goal": "Review the project test failures and prepare a safe remediation plan"
}
```

The request body rejects unknown fields. `goal` must contain 1–1,000 characters.

## Processing model

The endpoint selects a configured text-capable, non-stub provider. It does not silently fall back to the development stub.

- GPI asks the provider for a structured work order. The original normalized user goal is retained as the authoritative `goal`; model-supplied `risk_class` is ignored.
- The server derives an advisory risk class from the user goal and selected generated scope fields. Prohibited classifications are rejected before AWI planning.
- AWI asks the provider for a structured plan with 1–12 steps. Each step has a unique identifier, bounded description, dependencies, required capabilities, acceptance-criterion coverage, and a verification description.
- The plan validator rejects duplicate identifiers, unknown dependencies, self-dependencies, dependency cycles, missing acceptance criteria, and undeclared capabilities.
- The endpoint compares required capabilities with the authenticated owner's tool catalog and reports missing capabilities. Presence in the catalog does not imply authorization.
- A planning audit event is recorded for successful planning.

GPI and AWI each make one model-generation request. When the selected provider is Moonshot/Kimi, each remote generation request is independently subject to the per-owner Kimi request limiter. No remote provider fallback is introduced.

## Response guarantees

A successful response includes:

- `work_order`: the validated structured goal, scope, assumptions, constraints, dependencies, capabilities, acceptance criteria, verification steps, and advisory risk class.
- `plan`: the validated dependency graph and rationale.
- `capability_assessment`: required, available, and missing capability names.
- Explicit safety indicators: `planning_only: true`, `execution_ready: false`, `execution_started: false`, `tools_executed: false`, `permissions_changed: false`, and `authorization_checked: false`.

The risk classification is not an authorization decision. Actual execution, if added in a later release, must independently pass the existing Hub policy, permission, approval, idempotency, and audit controls. A plan must never be treated as an executable payload.

## Error behavior

| Status | Meaning |
| --- | --- |
| `401/403` | Missing or invalid authenticated session / access denied. |
| `422` | Invalid goal, malformed provider output, incomplete plan, or prohibited goal. |
| `429` | Per-owner Moonshot/Kimi request limit reached; honor `Retry-After`. |
| `503` | No configured non-stub provider or provider failure. |

Provider output is untrusted input. Validation errors are returned without accepting malformed work orders or plans. Do not put credentials, private keys, or sensitive personal data into goals.

## Optional encrypted plan persistence

The separate authenticated \`POST /agent/work-orders/plans\` endpoint performs the same GPI/AWI planning operation and then persists the validated plan as a short-lived owner-scoped record.

\`\`\`http
POST /agent/work-orders/plans
Authorization: Bearer <session-token>
Content-Type: application/json
\`\`\`

\`\`\`json
{
  "goal": "Prepare a reviewed implementation plan",
  "expires_in_seconds": 900
}
\`\`\`

- \`expires_in_seconds\` defaults to 900 and is bounded to 60–86,400 seconds.
- The endpoint requires \`MRH_WORKFLOW_PAYLOAD_KEY\` (or the equivalent protected application setting) to decode to exactly 32 bytes. There is no plaintext fallback or generated default key.
- WorkOrder and plan JSON are encrypted with AES-GCM. Associated data binds the ciphertext to the plan resource type, plan UUID, and authenticated owner. The database stores ciphertext, a canonical SHA-256 digest, owner/status metadata, and timestamps—not plaintext goal, WorkOrder, or plan text.
- The response includes the plan ID, digest, expiry, and the newly generated plan, while retaining all planning-only flags.

Retrieve an active plan using the same authenticated owner:

\`\`\`http
GET /agent/work-orders/plans/{plan_id}
Authorization: Bearer <session-token>
\`\`\`

The read endpoint verifies the owner binding, envelope authentication, strict WorkOrder/ExecutionPlan schemas, and canonical digest before returning the decrypted content. It recalculates the capability-presence report against the current owner tool catalog. It does not authorize or execute any tool.

Expired records are marked expired and their ciphertext fields are erased when accessed. New plan creation also runs a bounded expiry sweep (up to 100 due records); this is opportunistic cleanup, not a background scheduler. Consumed records are linked to their one queued workflow and are erased after a terminal outcome; revoked remains a reserved state.

| Status | Meaning |
| --- | --- |
| \`404\` | Plan identifier does not exist or is not owned by the authenticated user. |
| \`409\` | Plan is not active or failed envelope/schema/digest validation. |
| \`410\` | Plan has expired; its ciphertext has been erased. |
| \`503\` | Encryption key is missing/invalid, or encrypted plan storage is unavailable. |

## Controlled execution of an encrypted plan

The authenticated endpoint `POST /agent/work-orders/plans/{plan_id}/execute` can consume one active persisted plan and enqueue it through the existing durable workflow system. This is a separate operation from planning and does not execute tools inside the HTTP request.

A caller must submit the exact step-to-tool bindings and typed payloads. The request accepts no approval or permission flags:

```http
POST /agent/work-orders/plans/{plan_id}/execute
Authorization: Bearer <session-token>
Idempotency-Key: awi-plan-execution-001
Content-Type: application/json
```

```json
{
  "step_bindings": [
    {
      "step_id": "review",
      "tool_name": "text.echo",
      "payload": {
        "text": "A bounded, schema-validated input"
      }
    }
  ]
}
```

V1 execution is deliberately narrow:

- The plan must contain 1–5 steps. Each step must declare exactly one registered capability. The submitted `tool_name` must exactly match that capability and the step ID must match the persisted plan.
- Payloads are validated by the current registered tool input model. The combined serialized binding request is limited to 64 KiB. Natural-language descriptions are never converted into tool arguments.
- The server revalidates the persisted WorkOrder, plan graph, digest, risk classification, tool contract, current owner grants, and policy decision. Only server-classified LOW-risk work orders and LOW-risk tools without external side effects, with `PolicyDecision.ALLOW`, are eligible.
- Tools requiring approval, tools with external side effects, high-risk work, missing/revoked permissions, unknown tools, schema drift, and malformed bindings are rejected. The endpoint cannot grant permissions or approve an action.
- Plan consumption, the queued task, workflow, ordered step metadata, encrypted workflow payload, and owner-scoped idempotency binding are committed in one database transaction. A failed consume or insert rolls the entire transaction back.
- The encrypted workflow payload binds the owner, task, workflow, plan ID, plan digest, exact request digest, and tool contract digests. The existing `WorkerEngine` / `WorkflowWorkerHandler` / `AgentWorkflowRunner` path performs execution; the API route does not call a tool handler.
- The worker rechecks the consumed-plan association, plan integrity, current registry schema, current owner grants, and policy immediately before dispatch. A matching idempotency replay returns the original workflow; a changed request with the same key conflicts. A consumed plan cannot create another workflow through a different key.
- The response means **queued**, not completed. It reports `execution_started: false` and `tools_executed: false`. Check the owner-scoped workflow resource for its actual state.
- When a workflow reaches a terminal state, the workflow payload and consumed plan ciphertext are erased. If cleanup storage fails, the terminal result remains stable and reports `payload_cleanup_pending`; the ciphertext remains encrypted until cleanup is reconciled.

Example response fields include `workflow.workflow_id`, `workflow.status`, `queued: true`, `idempotent_replay: false`, `planning_only: false`, `execution_started: false`, and `tools_executed: false`.

| Status | Meaning |
| --- | --- |
| `401/403` | Authentication failure or current policy/permission denies the requested tool binding. |
| `404` | Plan does not exist or is not owned by the authenticated user. |
| `409` | Plan is not active, integrity/schema validation fails, a tool contract changed, or an idempotency/consumption conflict occurs. |
| `410` | The plan has expired and its ciphertext has been erased. |
| `422` | Binding count, exact step/tool mapping, payload schema, risk boundary, or request size is invalid. |
| `503` | Encryption key, permission lookup, registry, or durable storage is unavailable. |

The v1 bridge intentionally does not execute high-risk, approval-required, externally visible, or side-effecting tools. A future approval-capable version must add a durable, owner-authenticated, one-time approval record bound to the exact tool, canonical payload digest, tool schema digest, workflow, and expiry. A client boolean must never substitute for that record.

## Current limitations

- The risk classifier is a bounded heuristic, not a semantic safety proof.
- Provider output may be incomplete or incorrect; schema validity does not prove the plan is substantively correct.
- Capability presence is descriptive only; authorization is deliberately not evaluated by this planning endpoint.
- No plan persistence, task creation, tool execution, automatic retry, or autonomous follow-through is performed here.
- Local inference requires explicit configuration. Remote inference may incur provider cost and is governed by the configured provider and request limiter.

## Verification

Focused tests cover work-order validation, server-derived risk classification, dependency graph validation, acceptance-criterion and capability coverage, prohibited-goal handling, capability reporting, and remote-provider rate limiting. CI must pass before this change is considered merge-ready.
