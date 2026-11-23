"""Backward-compatible, sanitized API error envelopes with request correlation."""

from __future__ import annotations

import re
from logging import getLogger
from typing import Any
from uuid import uuid4

from fastapi import Request
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from starlette.exceptions import HTTPException as StarletteHTTPException
from starlette.responses import JSONResponse

_ERROR_CODES = {
    400: ("bad_request", "The request could not be processed."),
    401: ("authentication_required", "Authentication is required."),
    403: ("permission_denied", "The requested operation is not permitted."),
    404: ("resource_not_found", "The requested resource was not found."),
    409: ("state_conflict", "The requested operation conflicts with the current state."),
    413: ("payload_too_large", "The request payload exceeds the supported limit."),
    422: ("request_rejected", "The request failed validation or domain checks."),
    429: ("rate_limited", "Too many requests. Try again later."),
    500: ("internal_error", "An internal error occurred."),
    502: ("upstream_failure", "A required upstream operation failed."),
    503: ("service_unavailable", "The service is temporarily unavailable."),
}

# Only source-authored, reviewed detail literals remain eligible for the legacy
# detail field. Runtime exception text, provider messages, policy reasons and
# caller-supplied values are not added to this set.
_SAFE_DETAIL_LITERALS = frozenset(
    value.strip()
    for value in """
A decision already exists for this task
Agent input exceeds the supported bounds
Agent model run not found
Agent proposal failed validation
Agent proposal not found
Agent run not found
Agent workflow not found
An identical draft already exists for this owner and platform/content type
Approval not found
Audit storage is unavailable
Both cursor fields must be provided together
Capability candidate not found
Consumed plan cannot be revoked
Content draft not found
Content draft violates a storage constraint
Encrypted model-run result is unavailable
Encrypted plan storage is unavailable
Execution trace not found
Idempotency key conflicts with an earlier request
Idempotency key conflicts with another run
Idempotency key is already reserved
Idempotency key was used for another request
Initial setup requires the one-time deployment credential
Invalid context query
Invalid idempotency key
Invalid media attachment
Invalid reconciliation request
Invalid timezone-aware trace cursor timestamp
Invalid username or password
Model run cannot be cancelled in its current state
Model run not found
No configured non-stub local model provider is available
No registered provider satisfies the requested capabilities
Owner account is already initialized
Persisted plans are disabled until a valid payload key is configured
Persisted plans are unavailable until a valid payload key is configured
Plan record failed integrity or schema validation
Plan record has expired
Plan record is not available
Plan record is not revocable
Plan record not found
Project is not enrolled
Proposal fingerprint is stale
Proposal is no longer valid
Proposal was already reviewed or changed
Provide at least one supported field
Registered tool catalog is not valid for capability assessment
Request is already being created or requires recovery
Requested inference provider or encrypted workflow storage is unavailable
Stored proposal is invalid
Task is not awaiting approval
Task not found
The generated plan could not be encrypted safely
The plan record is invalid
The requested goal is outside the supported safety policy
Too many failed login attempts
Workflow cannot be cancelled
Workflow cannot be reconciled in its current state
Workflow execution is disabled until a valid payload key is configured
Workflow is not safely resumable
Workflow not found
Workflow plan contains no executable steps
Workflow resume could not be completed
Workflow submission conflicts with an existing resource
Active device not found
At least one non-null field is required
Campaign not found
Configured Kimi model is unavailable
Database is not ready
Database schema is not ready
Device action requires explicit owner confirmation
Device is no longer active
Device not found
Device task not found
Invalid Content-Length
Invalid document content
Invalid media filename
Invalid media upload
Invalid memory update
Invalid source freshness status
Kimi inference is disabled or incompletely configured; no Kimi request was made
Kimi requests are temporarily rate limited
Knowledge document not found
Knowledge source not found
Local inference is disabled or no local model is configured
Local model is unavailable
Media asset is already processed or processing
Media asset is attached to a content draft
Media asset is currently being processed
Media asset not found
Media asset ownership conflict prevents deletion
Media file is missing
Media signature does not match Content-Type
Media upload exceeds the 25 MB limit
Memory entry not found
Model profile not found
One or both drafts were not found
Only expiry may be explicitly cleared
Only original MP4/QuickTime video assets can be transcoded
Paired device is no longer active
Pairing code is invalid, expired, or already used
Refresh credential is invalid, expired, or revoked
Retrieval evaluation benchmark failed
Schedule not found
Stop reason must not be blank
Task lease is invalid, expired, or no longer active
Unknown model profile ID(s)
Unsupported media type
Worker process is not ready
ffmpeg_busy
ffmpeg_failed
ffmpeg_timeout
ffmpeg_unavailable
invalid_ffmpeg_output
kimi_rate_limited
media_asset_integrity_failed
output_registration_failed
upload_busy
Active Telegram client not found
Active or ambiguous provider work cannot be cancelled through this endpoint.
An absolute HTTPS resource URL with a public hostname is required for preview
Capability domain not found
Duplicate Telegram scopes are not allowed
Follow text is required when enabled
Idempotency key conflict
Idempotency reservation is incomplete
Idempotent task is unavailable
Invalid Telegram video render cursor
Invalid idempotency request
Invalid task cursor
Invalid task event cursor
Invalid video generation cursor
Invalid video scene cursor
Keyword is required
Keyword must be a single line
Limit must be between 1 and 50
Pairing code is invalid or expired
Permission grant storage is unavailable
Planning provider is unavailable
Planning provider request failed
Planning provider returned an invalid plan
Policy audit storage is unavailable
Prepare and save the renderer timeline in the Hub dashboard first
Refresh credential is invalid or revoked
Reply text contains an invalid character
Research evidence not found
Research feedback not found
Research opportunity not found
Reserved task is unavailable
Resource label must be a single line
Scene analysis capacity is temporarily full
Scene analysis requires a video asset
Server action registry is unavailable
Share text is required when enabled
Task has not been processed yet
Task reservation could not be read back
Task reservation is incomplete
Telegram memory entry not found
Telegram task is no longer cancellable
Telegram task not found
Telegram task result exceeds the response limit
Telegram task result is not ready
Telegram video analysis assets are unavailable
Telegram video analysis is not completed
Telegram video analysis not found
Telegram video asset is not ready
Telegram video asset not found
Telegram video generation not found
Telegram video render file not found
Telegram video render idempotency conflict
Telegram video render not found
Telegram video render source not found
Telegram video scene job not found
Telegram video scene job state changed
Telegram video timeline draft is invalid
Telegram video timeline draft not found
Use the dedicated video-intelligence scene-job API
Video generation page limit must be between 1 and 20
authorization_scope_denied
generation_cancellation_conflict
invalid_media_signature
media_asset_not_found
media_asset_type_mismatch
media_asset_unavailable
media_url_expired
public_media_not_configured
renderer_timeline_not_saved
review_input_rejected
telegram_video_render_not_completed
telegram_video_render_too_large
A brand with this name already exists
A validated edit specification is required to prepare the render timeline
Analysis source assets are unavailable
Asset is not a supported video
Asset is not part of this analysis
Both before_created_at and before_generation_id are required together
Brand profile not found
Generation history cursor timestamp must include a timezone
Generation job not found
Generation reconciliation is temporarily rate limited
Invalid generation history cursor timestamp
Invalid logo asset ID
Invalid scene-job cursor
Invalid source asset ID
Logo must reference an image owned by this user
Media asset is not ready for analysis
Permission grant request is invalid
Permission grant was not found
Render snapshot not found
Save a renderer-compatible timeline before submitting a render
Scene analysis is not permitted
Scene job not found
Scene job state changed; reload and retry
Source asset is not a supported video
Source asset is not ready for analysis
This generation is no longer safely pending; a worker may have claimed it or provider work may be active or ambiguous.
Timeline draft analysis is invalid
Timeline draft not found
Tool execution failed
Tool input validation failed
Tool is not registered
Video analysis cannot be cancelled in its current state
Video analysis capacity is temporarily full
Video analysis encryption is not configured
Video analysis is not completed
Video analysis must complete before prompt composition
Video analysis not found
Video analysis result is unavailable
Video asset not found
Video generation encryption is not configured
Video render not found
analysis_not_completed
analysis_result_unavailable
edit_specification_unavailable
not_started
provider_capability_mismatch
provider_unavailable
reconciliation_cooldown
remote_budget_exceeded
remote_consent_required
remote_cost_unknown
renderer_timeline_not_saved
stale_revision
""".splitlines()
    if value.strip()
) | frozenset(code for code, _message in _ERROR_CODES.values())

_SAFE_DETAIL_KEYS = frozenset(
    {
        "code",
        "message",
        "reason",
        "reason_code",
        "execution",
        "decision",
        "max_bytes",
        "retry_after_seconds",
        "correlation_id",
    }
)
_CORRELATION_ID_PATTERN = re.compile(
    r"^[0-9a-f]{8}-[0-9a-f]{4}-[1-8][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$",
    re.IGNORECASE,
)


def _request_id(request: Request) -> str:
    value = getattr(request.state, "request_id", None)
    return value if isinstance(value, str) and value else str(uuid4())


def _status_error(status_code: int) -> tuple[str, str]:
    return _ERROR_CODES.get(
        status_code,
        ("http_error", "The request could not be completed."),
    )


def _safe_http_detail(detail: Any, status_code: int) -> Any:
    """Project only reviewed public literals and bounded metadata into legacy detail."""
    fallback = _status_error(status_code)[1]
    if isinstance(detail, str):
        return detail if detail in _SAFE_DETAIL_LITERALS else fallback
    if not isinstance(detail, dict):
        return fallback

    sanitized: dict[str, str | int] = {}
    for key, value in detail.items():
        if key not in _SAFE_DETAIL_KEYS:
            continue
        if key == "correlation_id":
            if isinstance(value, str) and _CORRELATION_ID_PATTERN.fullmatch(value):
                sanitized[key] = value
            continue
        if key == "execution":
            if value == "not_started":
                sanitized[key] = value
            continue
        if key == "decision":
            if value in {"approved", "rejected", "allow", "deny"}:
                sanitized[key] = value
            continue
        if key == "max_bytes":
            if isinstance(value, int) and not isinstance(value, bool) and 0 <= value <= 50_000_000:
                sanitized[key] = value
            continue
        if key == "retry_after_seconds":
            if isinstance(value, int) and not isinstance(value, bool) and 0 <= value <= 86_400:
                sanitized[key] = value
            continue
        if isinstance(value, str) and value in _SAFE_DETAIL_LITERALS:
            sanitized[key] = value

    return sanitized or fallback


def _validation_issues(exc: RequestValidationError) -> list[dict[str, Any]]:
    """Keep bounded field locations and error types; never echo input/context."""
    sanitized: list[dict[str, Any]] = []
    for error in exc.errors()[:100]:
        raw_location = error.get("loc", ())[:8]
        location: list[str | int] = []
        for index, item in enumerate(raw_location):
            if (index == 0 and isinstance(item, str) and item in {"body", "query", "path", "header", "cookie"}) or (isinstance(item, int) and not isinstance(item, bool)):
                location.append(item)
            else:
                # Field names can be attacker-controlled (for example, extra
                # JSON keys or arbitrary mapping keys); never reflect them.
                location.append("field")
        error_type = error.get("type")
        code = (
            error_type[:80]
            if isinstance(error_type, str) and error_type
            else "value_error"
        )
        sanitized.append({
            "loc": location,
            "msg": "Invalid request value",
            "type": code,
        })
    return sanitized


async def http_exception_handler(
    request: Request,
    exc: StarletteHTTPException,
) -> JSONResponse:
    """Preserve only allowlisted legacy details; redact dynamic exception and caller data."""
    code, message = _status_error(exc.status_code)
    return JSONResponse(
        status_code=exc.status_code,
        content={
            "detail": jsonable_encoder(_safe_http_detail(exc.detail, exc.status_code)),
            "error": {
                "code": code,
                "message": message,
                "request_id": _request_id(request),
            },
        },
        headers=exc.headers,
    )


async def validation_exception_handler(
    request: Request,
    exc: RequestValidationError,
) -> JSONResponse:
    """Return safe validation metadata without reflecting caller-supplied values."""
    issues = _validation_issues(exc)
    return JSONResponse(
        status_code=422,
        content={
            "detail": issues,
            "error": {
                "code": "request_validation_error",
                "message": "The request contains invalid fields.",
                "request_id": _request_id(request),
                "issues": [
                    {
                        "location": item["loc"],
                        "code": item["type"],
                        "message": item["msg"],
                    }
                    for item in issues
                ],
            },
        },
    )


async def unhandled_exception_handler(
    request: Request,
    exc: Exception,
) -> JSONResponse:
    """Fail closed without returning exception text or private diagnostic values."""
    request_id = _request_id(request)
    getLogger("mrhub.api.errors").error(
        "http_request_failed request_id=%s exception_type=%s",
        request_id,
        type(exc).__name__,
    )
    return JSONResponse(
        status_code=500,
        content={
            "detail": "Internal server error",
            "error": {
                "code": "internal_error",
                "message": "An internal error occurred.",
                "request_id": request_id,
            },
        },
        headers={
            "X-Request-ID": request_id,
            "X-Content-Type-Options": "nosniff",
            "X-Frame-Options": "DENY",
            "Referrer-Policy": "no-referrer",
            "Permissions-Policy": "camera=(), microphone=(), geolocation=()",
            "Cache-Control": "no-store",
        },
    )
