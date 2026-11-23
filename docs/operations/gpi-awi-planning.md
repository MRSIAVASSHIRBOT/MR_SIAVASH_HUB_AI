# Goal-to-Prompt and AWI Planning API

## Purpose

A deterministic preflight endpoint, `POST /agent/work-orders/analyze`, is available before model-based planning. It reports bounded complexity, research/tool needs, information gaps, text/vision/audio modality signals, and reason codes without selecting a provider or invoking a tool.

The planning endpoint also returns a `decision_analysis` field from the same deterministic analyzer, refined with the validated WorkOrder. The separate `planning_assessment` then evaluates the final AWI DAG, explicit GPI clarification/research fields, model complexity estimate, capability gaps, and effective readiness. Both analyses are advisory and keep permission checks separate.

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

- `work_order`: the validated structured goal, scope, assumptions, constraints, dependencies, capabilities, model-estimated complexity, explicit missing information, clarification questions, research requirement/questions, acceptance criteria, verification steps, and advisory risk class. Derived readiness/tool-use properties are not serialized into this persisted contract; their values are exposed by the separate analyses.
- `plan`: the validated dependency graph and rationale.
- `capability_assessment`: required, available, and missing capability names.
- `planning_assessment`: deterministic complexity factors, potential information gaps, research signals, capability-based tool-readiness, and a validated topological plan order.
- `model_selection`: the provider/model selected from the registered model catalog and its capability/priority metadata.
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
- No plan persistence, task creation, tool execution, automatic retry, or autonomous follow-through is performed here.
- Local inference requires explicit configuration and a running local provider. GPI/AWI planning intentionally has no remote-provider fallback so a planning request cannot incur paid model usage.

## Verification

Focused tests cover work-order validation, server-derived risk classification, dependency graph validation, acceptance-criterion and capability coverage, prohibited-goal handling, capability reporting, and remote-provider rate limiting. CI must pass before this change is considered merge-ready.


## Explainable planning assessment

The planning response includes a read-only assessment alongside the generated WorkOrder and AWI plan:

- Complexity exposes two clearly separated signals: the model's bounded low/moderate/high estimate and a deterministic structural score using plan size, dependency depth, dependency edges, declared capabilities, and unverified assumptions. Neither is a performance estimate or an execution budget.
- Information-gap codes flag an unspecified scope, assumptions requiring confirmation, declared dependencies requiring validation, explicit missing user information, and missing registered capabilities. The validated WorkOrder separately carries the exact missing-information items and clarification questions. An empty gap list means only that these checks detected none; it is not proof that the request contains every detail needed.
- An explicit GPI research requirement and its bounded questions take precedence. When GPI does not request research, freshness-oriented phrases can still flag a required check and explicit source/documentation phrases can recommend research. The response distinguishes `declared_work_order_readiness` (computed from validated GPI fields) from effective `planning_readiness` (which may be stricter after server-side freshness analysis). This keyword fallback is a bounded heuristic, not a semantic guarantee and not an automatic web request.
- Tool readiness distinguishes no declared capability, missing registered capabilities, and capability presence where authorization still remains a separate check.
- Plan steps are returned in deterministic topological order using the shared workflow DAG planner.
- The response exposes the registered provider/model selected for the text-planning request. Planning readiness distinguishes clarification, required research, and ready-for-review states; none grants execution permission.

All fields are advisory. The endpoint remains planning-only: it does not prompt the owner automatically, perform research, select or invoke tools, grant permissions, or execute the plan. A capability being registered does not imply that its invocation is authorized.


## Planning artifact consistency

The intelligence assessment independently verifies its three inputs before
producing a readiness report: every WorkOrder acceptance criterion must be
covered by the Plan, every required capability must be represented in the Plan,
and the capability report must match and partition the same WorkOrder
requirements into available and missing entries. Inconsistent artifacts are
rejected rather than summarized as a successful or complete plan.
