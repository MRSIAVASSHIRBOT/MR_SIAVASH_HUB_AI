# Assistant Gateway Integration

This document records the architectural direction for connecting an optional, separately managed assistant runtime to MR SIAVASH HUB through a narrow adapter.

The HUB remains the source of truth for authentication, policy, approvals, audit events, durable jobs, workflow execution, idempotency, and recovery. The external runtime owns its own sessions, channels, plugins, and state. The connector must use authenticated HUB APIs and must not access either system's internal database directly.

The initial implementation is maintained in the separate `integration/assistant-gateway-20261103` feature branch and pull request. It adds a disabled-by-default, loopback-only health check with bounded timeouts and response sizes. It does not install, launch, or embed any external runtime.

Future stages must verify a specific runtime's API contract and version compatibility before enabling task submission. Tool execution, publishing, and other external side effects remain out of scope until policy checks, audit records, idempotency, allowlists, and approval gates are tested.

The connector is designed as an original adapter around a documented external interface; no external runtime source code is included in this repository.
