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

- `work_order`: the validated structured goal, scope, assumptions, constraints, dependencies, capabilities, estimated complexity, missing information, clarification questions, research requirement/questions, acceptance criteria, verification steps, and advisory risk class.
- `plan`: the validated dependency graph and rationale.
- `capability_assessment`: required, available, and missing capability names.
- Derived `tool_use_required` is based on validated required capabilities. `planning_readiness` is either `needs_clarification` or `ready_for_review`; neither value grants execution authority.
- Explicit safety indicators: `planning_only: true`, `execution_ready: false`, `execution_started: false`, `tools_executed: false`, `permissions_changed: false`, and `authorization_checked: false`.

The risk classification is not an authorization decision. Actual execution, if added in a later release, must independently pass the existing Hub policy, permission, approval, idempotency, and audit controls. A plan must never be treated as an executable payload.

## Error behavior

| Status | Meaning |
| --- | --- |
| `401/403` | Missing or invalid authenticated session / access denied. |
| `422` | Invalid goal, malformed provider output, incomplete plan, or prohibited goal. |
| `503` | No configured non-stub provider or provider failure. |

Provider output is untrusted input. Validation errors are returned without accepting malformed work orders or plans. Do not put credentials, private keys, or sensitive personal data into goals.

## Current limitations

- The risk classifier is a bounded heuristic, not a semantic safety proof.
- Provider output may be incomplete or incorrect; schema validity does not prove the plan is substantively correct.
- Capability presence is descriptive only; authorization is deliberately not evaluated by this planning endpoint.
- `research_required` and `research_questions` are advisory planning signals; the endpoint does not perform research or fetch sources.
- No plan persistence, task creation, tool execution, automatic retry, or autonomous follow-through is performed here.
- Local inference requires explicit configuration and a running local provider. GPI/AWI planning intentionally has no remote-provider fallback so a planning request cannot incur paid model usage.

## Verification

Focused tests cover work-order validation, server-derived risk classification, dependency graph validation, acceptance-criterion and capability coverage, prohibited-goal handling, capability reporting, and remote-provider rate limiting. CI must pass before this change is considered merge-ready.
