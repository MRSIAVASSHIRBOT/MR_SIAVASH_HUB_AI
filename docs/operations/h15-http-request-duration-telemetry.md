# H15 — HTTP Request Duration Telemetry

Status: implemented for Hub HTTP request completion logs; not a full metrics backend.

## Contract

The Hub HTTP middleware measures elapsed request time with a monotonic clock and records a non-negative `duration_ms` value. Every completed HTTP request log carries:

- `request_id`: canonical request correlation ID.
- `method`: HTTP method.
- `route_template`: registered route template, never a raw path with user-controlled identifiers.
- `status_code`: response status.
- `duration_ms`: elapsed application handling time in milliseconds.
- `outcome`: `success` for responses below 400, otherwise `http_error`.

The response continues to expose `X-Request-ID`. Existing error envelopes and task/workflow trace identifiers are unchanged.

## Privacy

Request bodies, query strings, authorization headers, user identifiers, credentials, tool payloads, and raw URL paths are not added to this telemetry. Route templates are used so resource IDs do not become metric/log dimensions.

## Validation

Regression tests assert duration presence and non-negativity for successful and HTTP error responses, request ID consistency, safe route-template logging, and absence of query strings or sensitive error details.

## Bounded process-local request metrics

The Hub also maintains an in-memory aggregate snapshot and exposes it through authenticated `GET /jobs/metrics`. It records only normalized HTTP method, registered route template, status class, request count, duration sum, and cumulative fixed latency buckets. The collector uses a lock for concurrent updates and has a hard series limit with an overflow bucket.

The response explicitly reports:
- `scope=single_process`
- `temporality=cumulative_since_process_start`

The endpoint inherits the jobs router's `require_user` authentication. Query strings, raw paths, request bodies, IP addresses, user/session identifiers, authorization headers and provider payloads are excluded. Metrics reset when the process restarts; multiple processes expose independent snapshots.

See [ADR-0047](../architecture/decisions/ADR-0047-process-local-http-request-metrics.md) for the design decision.

## Limitations

This is a bounded process-local metrics slice, not a fleet-wide metrics backend. Prometheus/OpenTelemetry export, cross-process aggregation, latency SLO alerts, durable retention, and full task-to-tool distributed traces remain separate H15/X7 acceptance items. It does not certify production runtime telemetry.

Production services and deployment configuration were not changed.
