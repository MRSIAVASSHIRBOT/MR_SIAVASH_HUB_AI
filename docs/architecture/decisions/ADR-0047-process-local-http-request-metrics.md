# ADR-0047 — Bounded process-local HTTP request metrics

- Status: Accepted
- Date: 2026-11-25
- Scope: H15 — Observability and Operations

## Context

The Hub already emits structured HTTP completion logs with request IDs, route templates, status codes, and monotonic duration measurements. These logs are useful for diagnosis but are not directly queryable as bounded aggregate counters or latency buckets. A full distributed metrics backend is not part of the current local-first deployment.

## Decision

Add an in-process collector with fixed latency bucket boundaries and a hard series limit. The collector records only:
- normalized HTTP method;
- the registered Starlette route template (never the raw URL path);
- HTTP status class;
- request count, duration sum, and cumulative duration bucket counts.

Unknown methods, unmatched routes, and excess series are collapsed into bounded fallback dimensions. The collector rejects non-finite durations and protects mutation/snapshot operations with a lock.

Expose `GET /jobs/metrics` through the existing authenticated jobs router. The response explicitly states `scope=single_process` and `temporality=cumulative_since_process_start`. Metrics are process-local, reset on restart, and are not a fleet-wide or durable source of truth.

## Privacy and security

No request body, query string, raw URL path, user/session identifier, IP address, authorization header, credential, or provider payload is recorded. Route templates are source-controlled route definitions. The endpoint inherits the jobs router's `require_user` authentication dependency.

## Consequences

- Operators can inspect bounded request counts and latency buckets without querying logs.
- No external dependency, database table, migration, exporter, or deployment change is introduced.
- Multiple Hub processes expose independent snapshots; aggregation, Prometheus/OpenTelemetry export, SLO alerts, and durable retention remain future X7/H15 work.

## Rollback

Revert the request-metrics collector, middleware hook, authenticated route, tests, and this ADR. Existing structured request logs remain unchanged.
