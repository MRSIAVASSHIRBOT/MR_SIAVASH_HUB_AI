# API Error Contract

All HTTP error responses include a stable top-level `error` envelope:

```json
{
  "detail": "Task not found",
  "error": {
    "code": "resource_not_found",
    "message": "The requested resource was not found.",
    "request_id": "canonical-request-uuid"
  }
}
```

## Compatibility and disclosure boundary

The legacy `detail` field remains present, but compatibility is intentionally
limited to exact, reviewed public-safe string literals and a small set of
explicitly approved object shapes. The source-literal allowlist is maintained
in `mrhub.api.public_error_details`. Unknown details fall back to the generic
message associated with the HTTP status.

This means exception-derived text (`str(exc)`), provider codes or bodies,
policy decision reasons, request-controlled identifiers (including unknown
model-profile IDs), nested objects and arbitrary mappings are never reflected
by the HTTP exception handler. Unknown model profiles return only a stable
message; caller-supplied identifiers are not echoed.

A small set of structured legacy details is also allowlisted by server-owned
error code. Their message is always replaced with a fixed reviewed string;
only explicitly approved fields may survive (for example, the fixed
`execution=not_started` marker, a bounded integer retry delay, a bounded
maximum byte count, or one of the known security-lab reason codes). Unknown
codes and all unapproved fields fall back to the generic status message.
New legacy detail strings or structured codes must be reviewed and added to
the allowlist deliberately; do not add dynamic values or interpolate
user/provider data.

New clients should use `error.code` for programmatic branching and
`error.request_id` for support and log correlation. Error codes are stable API
identifiers; human-readable messages are generic and are not intended for
branching.

## Validation errors

A request-validation response uses `error.code=request_validation_error` and
includes bounded `error.issues` entries with structural locations, error types,
and a generic message. Only the request section
(`body/query/path/header/cookie`) and numeric array indices are preserved in
locations; caller-controlled field names are replaced with a generic `field`
token. The legacy `detail` list is retained in a sanitized form. Raw `input`,
Pydantic `context`, and arbitrary JSON keys are never reflected in this
response.

## Unhandled errors

Unhandled exceptions return a generic 500 response. Exception text, stack
details, prompts, credentials, and arbitrary handler output are not included
in the HTTP response body. The application error handler logs only the
correlation ID and exception type. The ASGI server/runtime may independently
emit a traceback for unhandled exceptions depending on its logging
configuration; deployment log access, retention, and redaction must therefore
be configured separately.

## Request correlation

The `request_id` in the error envelope matches the `X-Request-ID` response
header. A valid caller-supplied canonical UUID is retained; invalid or missing
values are replaced by a new request ID.

## OpenAPI response schemas

Every mounted API router documents the shared `APIErrorResponse` shape for
common HTTP error statuses and a default error response. The schema preserves
the legacy `detail` field while exposing a typed `error` object with stable
`code`, generic `message`, `request_id`, and optional sanitized validation
`issues`. Clients can generate typed error handlers from OpenAPI instead of
guessing response structures.

Runtime handlers validate their envelopes with the same Pydantic models used
by the OpenAPI components. This keeps documented and emitted structures aligned.
