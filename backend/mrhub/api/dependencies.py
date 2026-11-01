"""Shared API authentication dependencies."""

from typing import Annotated

from fastapi import Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from mrhub.config import get_settings
from mrhub.infrastructure.database import TaskRepository
from mrhub.security.auth import AuthenticatedUser, AuthService

bearer_scheme = HTTPBearer(auto_error=False)


def get_auth_service() -> AuthService:
    settings = get_settings()
    repository = TaskRepository(settings.database_path)
    repository.initialize()
    return AuthService(repository, session_ttl_hours=settings.session_ttl_hours)


def require_user(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer_scheme)],
) -> AuthenticatedUser:
    if credentials is None or credentials.scheme.lower() != "bearer":
        raise HTTPException(status_code=401, detail="Authentication required")
    user = get_auth_service().authenticate(credentials.credentials)
    if user is None:
        raise HTTPException(status_code=401, detail="Invalid or expired session")
    return user
