# API Error Contract

All HTTP error responses include a stable top-level `error` envelope:

```json
{
  "detail": "Legacy route detail",
  "error": {
    "code": "state_conflict",
    "message": "The requested operation conflicts with the current state.",
    "request_id": "canonical-request-uuid"
  }
}
```

## Compatibility

The existing `detail` field is retained for existing clients. New clients should
use `error.code` for programmatic branching and `error.request_id` for support
and log correlation. Error codes are stable API identifiers; human-readable
messages are generic and are not intended for branching.

## Validation errors

A request-validation response uses `error.code=request_validation_error` and
includes bounded `error.issues` entries with structural locations, error types,
and a generic message. Only the request section (`body/query/path/header/cookie`)
and numeric array indices are preserved in locations; caller-controlled field
names are replaced with a generic `field` token. The legacy `detail` list is
retained in a sanitized form. Raw `input`, Pydantic `context`, and arbitrary
JSON keys are never reflected in this response.

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

## Limitations

This contract standardizes transport errors; it does not replace domain-specific
error codes returned by successful HTTP responses, nor does it automatically
classify every third-party provider error. Legacy `detail` values from
application-raised HTTP exceptions remain intact for compatibility, so route
implementations must continue to avoid placing secrets or raw request bodies in
those details.
