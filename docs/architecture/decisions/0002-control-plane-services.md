# ADR 0002: Shared Control-Plane Services

- Status: accepted for the initial implementation
- Date: 2026-11-01

## Context

Agent execution, scheduled workflows, provider selection, and tool authorization need consistent lifecycle and security behavior. Implementing these concerns separately would create duplicated queues, inconsistent permissions, and difficult-to-debug state.

## Decisions

1. Use one Job Engine for task lifecycle, cancellation, and later worker dispatch.
2. Use a deterministic Policy Engine that denies prohibited risk classes, denies missing permission grants, and requires approval for high-impact or external side effects.
3. Use a Model Router that selects only from explicitly registered provider descriptors based on capability and availability.
4. Keep provider invocation separate from routing. The initial router selects a model but does not make network calls.
5. Prefer local models when requested; do not silently send data to a cloud model if no local model meets the requested capability.

## Consequences

- Agent and workflow modules share one task state machine.
- Approval is a first-class task state.
- Provider adapters can be added without changing task orchestration.
- The first implementation remains deterministic and testable without API keys or paid services.
- Actual worker execution, approval identity, provider health checks, and durable audit events remain follow-up work.

## Review triggers

Revisit this decision when adding multi-user access, external publishing, remote workers, or provider-side tool calling.
