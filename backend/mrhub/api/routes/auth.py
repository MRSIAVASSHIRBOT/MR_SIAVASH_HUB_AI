"""One-time local owner setup and session endpoints."""

import ipaddress
import sqlite3
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from fastapi.security import HTTPAuthorizationCredentials
from pydantic import BaseModel, Field

from mrhub.api.dependencies import bearer_scheme, get_auth_service, require_user
from mrhub.security.auth import AuthenticatedUser, AuthService, LoginAttemptLimiter

router = APIRouter(prefix="/auth", tags=["authentication"])


class SetupRequest(BaseModel):
    password: str = Field(min_length=14, max_length=256)


class LoginRequest(BaseModel):
    username: str = Field(default="owner", min_length=1, max_length=40)
    password: str = Field(min_length=1, max_length=256)


class SessionResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in: int
    user: AuthenticatedUser


@router.post("/setup", status_code=201)
def setup_owner(
    payload: SetupRequest,
    request: Request,
    service: Annotated[AuthService, Depends(get_auth_service)],
) -> dict[str, str]:
    host = request.client.host if request.client else ""
    is_loopback = host == "testclient"
    if not is_loopback:
        try:
            is_loopback = ipaddress.ip_address(host).is_loopback
        except ValueError:
            is_loopback = False
    if not is_loopback:
        raise HTTPException(status_code=403, detail="Initial setup is available only locally")
    if service.repository.auth_user_exists():
        raise HTTPException(status_code=409, detail="Owner account is already initialized")
    try:
        service.initialize_owner(payload.password)
    except sqlite3.IntegrityError as exc:
        raise HTTPException(status_code=409, detail="Owner account is already initialized") from exc
    return {"status": "owner_initialized", "next": "POST /auth/login"}


@router.post("/login", response_model=SessionResponse)
def login(
    payload: LoginRequest,
    request: Request,
    response: Response,
    service: Annotated[AuthService, Depends(get_auth_service)],
) -> SessionResponse:
    response.headers["Cache-Control"] = "no-store"
    response.headers["Pragma"] = "no-cache"
    limiter: LoginAttemptLimiter = request.app.state.login_attempt_limiter
    client_key = request.client.host if request.client else "unknown"
    retry_after = limiter.retry_after(client_key)
    if retry_after:
        response.headers["Retry-After"] = str(retry_after)
        raise HTTPException(status_code=429, detail="Too many failed login attempts")

    result = service.login(payload.username, payload.password)
    if result is None:
        limiter.record_failure(client_key)
        raise HTTPException(status_code=401, detail="Invalid username or password")
    limiter.reset(client_key)
    token, user = result
    return SessionResponse(
        access_token=token,
        expires_in=service.session_ttl_hours * 3600,
        user=user,
    )


@router.post("/logout", status_code=204)
def logout(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer_scheme)],
    _user: Annotated[AuthenticatedUser, Depends(require_user)],
    service: Annotated[AuthService, Depends(get_auth_service)],
) -> None:
    if credentials is not None:
        service.logout(credentials.credentials)
