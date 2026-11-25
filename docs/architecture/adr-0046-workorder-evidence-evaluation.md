# ADR-0046 — Digest-bound WorkOrder evidence evaluation

- Status: Accepted
- Date: 2026-11-25
- Roadmap mapping: H10 (Evaluation & Self-Correction), with a future E8 consumer integration

## Context

The Hub already has deterministic tool-outcome evaluation, and EL_AI can report whether a task has a structurally valid terminal result. Neither fact proves that a WorkOrder acceptance criterion was satisfied. Treating a task status or a model-produced claim as semantic acceptance would create a false-success path.

## Decision

Introduce a separate, read-only WorkOrder evidence contract. Each evaluation is bound to one WorkOrder ID, immutable revision, and SHA-256 digest. Evidence is referenced by opaque IDs and must be checked by an exact source/verifier pair registered in trusted server-side code.

A criterion can be accepted only after a registered verifier confirms the evidence digest for the exact WorkOrder revision. Missing, unregistered, malformed, stale, or conflicting evidence never counts as success. Required criteria determine the overall decision; optional criteria remain visible but do not block acceptance.

The initial change provides pure deterministic models, registry behavior, aggregation, and tests. No production verifier or API route is enabled until its source-of-truth, authentication, owner scoping, and consumer contract are implemented.

## Consequences

- The existing telegram_agent_plan.v1 contract remains unchanged.
- EL_AI E8 remains execution-coverage-only and must not claim goal satisfaction.
- A future telegram_agent_plan.v2 or equivalent versioned extension must bind the WorkOrder digest/revision and preserve v1 compatibility.
- Evidence verification remains read-only; the evaluator cannot execute tools, retry tasks, mutate workflows, change grants, or approve actions.
- Semantic acceptance stays unavailable until trusted evidence adapters and cross-project tests are deployed.
