"""Scoped authentication dependencies for paired Telegram bot clients."""

from __future__ import annotations

from typing import Annotated

from fastapi import Depends, Header, HTTPException
from fastapi.security import HTTPAuthorizationCredentials

from mrhub.api.dependencies import bearer_scheme
from mrhub.config import get_settings
from mrhub.integrations.telegram_pairing import (
    TelegramClientIdentity,
    TelegramPairingRepository,
)


def require_telegram_scope(scope: str):
    """Return a dependency that validates a paired client and one explicit scope."""

    def dependency(
        credentials: Annotated[
            HTTPAuthorizationCredentials | None, Depends(bearer_scheme)
        ],
        telegram_user_id: Annotated[int | None, Header(alias="X-Telegram-User-Id")] = None,
    ) -> TelegramClientIdentity:
        if (
            credentials is None
            or credentials.scheme.lower() != "bearer"
            or telegram_user_id is None
            or telegram_user_id <= 0
        ):
            raise HTTPException(status_code=401, detail="Paired Telegram authentication required")
        identity = TelegramPairingRepository(get_settings().database_path).authenticate(
            access_token=credentials.credentials,
            telegram_user_id=telegram_user_id,
        )
        if identity is None:
            raise HTTPException(status_code=401, detail="Telegram credential is invalid or expired")
        if scope not in identity.scopes:
            raise HTTPException(status_code=403, detail="Telegram client lacks the required scope")
        return identity

    return dependency
