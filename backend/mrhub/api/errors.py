"""Backward-compatible, sanitized API error envelopes with request correlation."""

from __future__ import annotations

from logging import getLogger
from typing import Any
from uuid import uuid4

from fastapi import Request
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from pydantic import BaseModel, ConfigDict, Field
from starlette.exceptions import HTTPException as StarletteHTTPException
from starlette.responses import JSONResponse

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


def _request_id(request: Request) -> str:
    value = getattr(request.state, "request_id", None)
    return value if isinstance(value, str) and value else str(uuid4())


def _status_error(status_code: int) -> tuple[str, str]:
    return _ERROR_CODES.get(
        status_code,
        ("http_error", "The request could not be completed."),
    )


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
    """Add a typed stable envelope while preserving the legacy detail field."""
    code, message = _status_error(exc.status_code)
    payload = APIErrorResponse(
        detail=jsonable_encoder(exc.detail),
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
