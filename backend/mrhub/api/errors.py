"""Backward-compatible, sanitized API error envelopes with request correlation."""

from __future__ import annotations

from logging import getLogger
from typing import Any
from uuid import UUID, uuid4

from fastapi import Request
from fastapi.exceptions import RequestValidationError
from pydantic import BaseModel, ConfigDict, Field
from starlette.exceptions import HTTPException as StarletteHTTPException
from starlette.responses import JSONResponse

from mrhub.api.public_error_details import SAFE_PUBLIC_ERROR_DETAILS


class APIErrorIssue(BaseModel):
    """One sanitized validation issue exposed by the stable API error contract."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    location: list[str | int] = Field(max_length=8)
    code: str = Field(min_length=1, max_length=80)
    message: str = Field(min_length=1, max_length=160)


class APIErrorEnvelope(BaseModel):
    """Stable machine-readable error metadata shared by every API route."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    code: str = Field(min_length=1, max_length=80)
    message: str = Field(min_length=1, max_length=200)
    request_id: str = Field(
        min_length=36,
        max_length=36,
        pattern=r"^[0-9a-f]{8}-[0-9a-f]{4}-[1-8][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$",
    )
    issues: list[APIErrorIssue] | None = None


class APIErrorResponse(BaseModel):
    """Backward-compatible response body with legacy detail plus typed error."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    detail: Any
    error: APIErrorEnvelope


API_ERROR_RESPONSES: dict[int | str, dict[str, Any]] = {
    status: {
        "model": APIErrorResponse,
        "description": "Sanitized API error envelope; branch on error.code.",
    }
    for status in (400, 401, 403, 404, 409, 413, 422, 429, 500, 502, 503)
}
API_ERROR_RESPONSES["default"] = {
    "model": APIErrorResponse,
    "description": "Sanitized API error envelope for other HTTP error statuses.",
}


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

_SAFE_LEGACY_DETAIL_OBJECTS = (
    {"reason": "stale_revision"},
    {"code": "provider_unavailable", "execution": "not_started"},
)

_POLICY_DECISION_MESSAGES = {
    "allow": "Policy checks passed.",
    "deny": "The requested action is not permitted.",
    "require_approval": "Explicit owner approval is required.",
}

_SAFE_DETAIL_CODE_MESSAGES = {
    "provider_unavailable": "A configured video generation provider is unavailable.",
    "provider_capability_mismatch": "The provider does not support the requested generation configuration.",
    "remote_consent_required": "Explicit consent is required before remote processing.",
    "remote_cost_unknown": "The cost of remote processing could not be verified.",
    "remote_budget_exceeded": "The estimated remote cost exceeds the approved budget.",
    "repository_not_found": "Public repository not found.",
    "generation_cancellation_conflict": "Active or ambiguous provider work cannot be cancelled through this endpoint.",
    "reconciliation_cooldown": "Generation reconciliation is temporarily rate limited.",
    "kimi_rate_limited": "Kimi requests are temporarily rate limited.",
    "renderer_timeline_not_saved": "A saved renderer timeline is required before submitting a render.",
    "analysis_not_completed": "Video analysis must complete before prompt composition.",
    "analysis_result_unavailable": "Video analysis result is unavailable.",
    "analysis_result_invalid": "Video analysis result is invalid.",
    "semantic_analysis_unavailable": "Validated semantic visual analysis is required to compose this prompt.",
    "timeline_draft_invalid": "The selected storyboard draft is invalid.",
    "timeline_draft_unavailable": "The selected storyboard draft is unavailable.",
    "timeline_draft_version_conflict": "The selected storyboard draft has changed; reload it before composing.",
    "edit_specification_unavailable": "A validated edit specification is required to prepare the render timeline.",
    "telegram_video_render_not_completed": "Telegram video render is not completed.",
    "telegram_video_render_too_large": "Telegram video render exceeds the supported size limit.",
}

_SAFE_DETAIL_CODES_WITH_NOT_STARTED = frozenset({
    "provider_unavailable",
    "remote_consent_required",
    "remote_cost_unknown",
    "remote_budget_exceeded",
})

_SAFE_DETAIL_REASON_CODES = frozenset({
    "authorization_scope_denied",
    "review_input_rejected",
})


def _request_id(request: Request) -> str:
    value = getattr(request.state, "request_id", None)
    return value if isinstance(value, str) and value else str(uuid4())


def _status_error(status_code: int) -> tuple[str, str]:
    return _ERROR_CODES.get(
        status_code,
        ("http_error", "The request could not be completed."),
    )


def _safe_http_detail(status_code: int, detail: object) -> object:
    """Preserve only reviewed public fields and replace all dynamic text."""
    if isinstance(detail, str) and detail in SAFE_PUBLIC_ERROR_DETAILS:
        return detail
    if not isinstance(detail, dict):
        return _status_error(status_code)[1]

    if any(detail == allowed for allowed in _SAFE_LEGACY_DETAIL_OBJECTS):
        return detail

    decision = detail.get("decision")
    if isinstance(decision, str) and decision in _POLICY_DECISION_MESSAGES:
        safe_detail: dict[str, str] = {
            "decision": decision,
            "reason": _POLICY_DECISION_MESSAGES[decision],
        }
        correlation_id = detail.get("correlation_id")
        if isinstance(correlation_id, str):
            try:
                parsed_correlation_id = UUID(correlation_id)
            except (TypeError, ValueError, AttributeError):
                pass
            else:
                if str(parsed_correlation_id) == correlation_id:
                    safe_detail["correlation_id"] = correlation_id
        return safe_detail

    reason_code = detail.get("reason_code")
    if isinstance(reason_code, str) and reason_code in _SAFE_DETAIL_REASON_CODES:
        return {"reason_code": reason_code}

    code = detail.get("code")
    if isinstance(code, str) and code in _SAFE_DETAIL_CODE_MESSAGES:
        safe_detail: dict[str, str | int] = {
            "code": code,
            "message": _SAFE_DETAIL_CODE_MESSAGES[code],
        }
        if (
            code in _SAFE_DETAIL_CODES_WITH_NOT_STARTED
            and detail.get("execution") == "not_started"
        ):
            safe_detail["execution"] = "not_started"
        retry_after = detail.get("retry_after_seconds")
        if (
            code in {"kimi_rate_limited", "reconciliation_cooldown"}
            and isinstance(retry_after, int)
            and not isinstance(retry_after, bool)
            and 1 <= retry_after <= 86_400
        ):
            safe_detail["retry_after_seconds"] = retry_after
        max_bytes = detail.get("max_bytes")
        if (
            code == "telegram_video_render_too_large"
            and isinstance(max_bytes, int)
            and not isinstance(max_bytes, bool)
            and 1 <= max_bytes <= 1_073_741_824
        ):
            safe_detail["max_bytes"] = max_bytes
        return safe_detail

    if detail.get("message") == "Unknown model profile ID(s)":
        # Profile IDs arrive in the request body. Do not echo them, even when
        # they look like harmless slugs; clients can use the stable message.
        return {"message": "Unknown model profile ID(s)"}

    # This removes provider codes, exception messages, policy reasons,
    # arbitrary identifiers, and nested request-controlled values.
    return _status_error(status_code)[1]


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
    """Return only reviewed legacy details plus the stable typed error envelope."""
    code, message = _status_error(exc.status_code)
    payload = APIErrorResponse(
        detail=_safe_http_detail(exc.status_code, exc.detail),
        error=APIErrorEnvelope(
            code=code,
            message=message,
            request_id=_request_id(request),
        ),
    )
    return JSONResponse(
        status_code=exc.status_code,
        content=payload.model_dump(mode="json", exclude_none=True),
        headers=exc.headers,
    )


async def validation_exception_handler(
    request: Request,
    exc: RequestValidationError,
) -> JSONResponse:
    """Return safe typed validation metadata without reflecting caller values."""
    issues = _validation_issues(exc)
    payload = APIErrorResponse(
        detail=issues,
        error=APIErrorEnvelope(
            code="request_validation_error",
            message="The request contains invalid fields.",
            request_id=_request_id(request),
            issues=[
                APIErrorIssue(
                    location=item["loc"],
                    code=item["type"],
                    message=item["msg"],
                )
                for item in issues
            ],
        ),
    )
    return JSONResponse(
        status_code=422,
        content=payload.model_dump(mode="json", exclude_none=True),
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
    payload = APIErrorResponse(
        detail="Internal server error",
        error=APIErrorEnvelope(
            code="internal_error",
            message="An internal error occurred.",
            request_id=request_id,
        ),
    )
    return JSONResponse(
        status_code=500,
        content=payload.model_dump(mode="json", exclude_none=True),
        headers={
            "X-Request-ID": request_id,
            "X-Content-Type-Options": "nosniff",
            "X-Frame-Options": "DENY",
            "Referrer-Policy": "no-referrer",
            "Permissions-Policy": "camera=(), microphone=(), geolocation=()",
            "Cache-Control": "no-store",
        },
    )
