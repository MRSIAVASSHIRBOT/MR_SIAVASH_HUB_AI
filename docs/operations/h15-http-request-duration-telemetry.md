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

## Limitations

This is structured log telemetry only. It does not create a metrics exporter, tracing backend, latency histogram, SLO alert, or full task-to-tool distributed trace. Those remain separate H15/X7 acceptance items. It does not certify production runtime telemetry.

Production services and deployment configuration were not changed.
