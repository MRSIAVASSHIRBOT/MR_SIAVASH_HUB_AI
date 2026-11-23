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

The endpoint selects a configured **local-only**, text-capable, non-stub provider (for example, the locally running Ollama model). It does not register Moonshot/Kimi, invoke a paid provider, or silently fall back to the development stub. If no local model is configured and available, planning fails closed with `503`.

- GPI asks the provider for a structured work order. The original normalized user goal is retained as the authoritative `goal`; model-supplied `risk_class` is ignored.
- The server derives an advisory risk class from the user goal and selected generated scope fields. Prohibited classifications are rejected before AWI planning.
- AWI asks the provider for a structured plan with 1–12 steps. Each step has a unique identifier, bounded description, dependencies, required capabilities, acceptance-criterion coverage, and a verification description.
- The plan validator rejects duplicate identifiers, unknown dependencies, self-dependencies, dependency cycles, missing acceptance criteria, and undeclared capabilities.
- The endpoint compares required capabilities with the authenticated owner's tool catalog and reports missing capabilities. Presence in the catalog does not imply authorization.
- A planning audit event is recorded for successful planning.

GPI and AWI each make one local model-generation request. The dedicated Kimi endpoints remain separate and require their own explicit use and rate limiting; this planning endpoint never calls them.

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

Expired records are marked expired and their ciphertext fields are erased when accessed. New plan creation also runs a bounded expiry sweep (up to 100 due records); this is opportunistic cleanup, not a background scheduler.

An owner may revoke an active plan:

```http
DELETE /agent/work-orders/plans/{plan_id}
Authorization: Bearer <session-token>
```

Revocation uses an owner-scoped atomic transition. The ciphertext and nonce fields are overwritten with non-secret terminal markers; repeated DELETE requests are idempotent. A foreign owner's plan is reported as not found. Expired plans remain expired, and consumed plans cannot be revoked. The `consumed` state remains reserved for a future reviewed plan-to-workflow integration; no plan-to-execution endpoint is exposed by this change.

| Status | Meaning |
| --- | --- |
| \`404\` | Plan identifier does not exist or is not owned by the authenticated user. |
| \`409\` | Plan is not active or failed envelope/schema/digest validation. |
| \`410\` | Plan has expired; its ciphertext has been erased. |
| \`503\` | Encryption key is missing/invalid, or encrypted plan storage is unavailable. |

## Current limitations

- The risk classifier is a bounded heuristic, not a semantic safety proof.
- Provider output may be incomplete or incorrect; schema validity does not prove the plan is substantively correct.
- Capability presence is descriptive only; authorization is deliberately not evaluated by this planning endpoint.
- No plan persistence, task creation, tool execution, automatic retry, or autonomous follow-through is performed here.
- Local inference requires explicit configuration and a running local provider. GPI/AWI planning intentionally has no remote-provider fallback so a planning request cannot incur paid model usage.

## Verification

Focused tests cover work-order validation, server-derived risk classification, dependency graph validation, acceptance-criterion and capability coverage, prohibited-goal handling, capability reporting, and remote-provider rate limiting. CI must pass before this change is considered merge-ready.
