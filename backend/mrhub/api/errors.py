"""Backward-compatible, sanitized API error envelopes with request correlation."""

from __future__ import annotations

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
        location = [
            (item if isinstance(item, str) else str(item))[:80]
            for item in error.get("loc", ())[:8]
        ]
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
    """Add a stable error envelope while preserving the legacy detail field."""
    code, message = _status_error(exc.status_code)
    return JSONResponse(
        status_code=exc.status_code,
        content={
            "detail": jsonable_encoder(exc.detail),
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
