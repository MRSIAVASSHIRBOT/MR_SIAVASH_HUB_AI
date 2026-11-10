# ADR-0010: Deterministic read-only agent proposal evaluation

- Status: Implemented on the feature branch; pending exact-head CI and review
- Date: 2026-11-10

## Context

A proposal can be syntactically valid and reviewed without having been evaluated against the current server-defined agent and tool catalog. Review, technical preflight, and activation must remain distinct lifecycle stages.

## Decision

Expose an authenticated, owner-scoped read-only evaluation endpoint at:

`GET /agent/proposals/{proposal_id}/evaluation`

The evaluator checks profile constraints, name availability against built-in agents, duplicate tool identifiers, bounded tool count, current tool registration, and bounded turn count. It returns individual check results and a recommendation for whether the candidate is eligible for owner review.

## Security and lifecycle boundaries

- Evaluation is deterministic and does not call a model.
- Evaluation never invokes tools, registers an agent, grants permissions, or changes proposal state.
- The endpoint only returns records belonging to the authenticated owner.
- A passing report means only that static preflight checks passed against the current in-process registries; it is not a security certification, runtime test, activation approval, or guarantee of future tool availability.
- The endpoint reports execution, activation, and permission-grant flags as false.
- Proposal approval remains separate and continues to leave `activation_state` inactive.

## Consequences

This creates an inspectable, low-risk quality gate before owner review while preserving the existing server-side policy checks at actual tool invocation time. Runtime evaluation in a sandbox and controlled activation remain separate future stages requiring independent threat modeling, resource limits, and owner authorization.
