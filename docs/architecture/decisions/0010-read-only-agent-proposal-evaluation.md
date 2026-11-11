# ADR-0010: Deterministic read-only agent proposal evaluation

- Status: Implemented on main; risk-aware preflight extended on 2026-11-10
- Date: 2026-11-10

## Context

A proposal can be syntactically valid and reviewed without having been evaluated against the current server-defined agent and tool catalog. Review, technical preflight, and activation must remain distinct lifecycle stages.

## Decision

Expose an authenticated, owner-scoped read-only evaluation endpoint at:

`GET /agent/proposals/{proposal_id}/evaluation`

The evaluator checks profile constraints, name availability against built-in agents, duplicate tool identifiers, bounded tool count, current tool registration, bounded turn count, and the current risk metadata for every requested tool. The response includes each tool's risk class, required permissions, and external-side-effect flag.

Only low-risk tools that declare no external side effects pass the initial preflight policy. Moderate, high, prohibited, or side-effecting tools are blocked for separate security review. Required permissions are reported for owner review; they are never granted by evaluation.

## Security and lifecycle boundaries

- Evaluation is deterministic and does not call a model.
- Evaluation never invokes tools, registers an agent, grants permissions, or changes proposal state.
- The endpoint only returns records belonging to the authenticated owner.
- A passing report means only that static preflight checks passed against the current in-process registries; it is not a runtime test or guarantee of future tool availability.
- The report explicitly marks execution, activation, and permission-grant operations as false.
- Proposal approval remains separate and continues to leave `activation_state` inactive.
- Actual tool invocation continues to enforce the server-side policy independently.

## Consequences

This creates an inspectable, conservative quality gate before owner review while preserving the existing server-side policy checks at actual tool invocation time. Runtime evaluation in a sandbox and controlled activation remain separate future stages requiring independent threat modeling, resource limits, and owner authorization.
