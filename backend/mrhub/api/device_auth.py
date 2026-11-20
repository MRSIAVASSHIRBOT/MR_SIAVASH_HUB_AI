"""Scoped authentication for paired personal device companions."""
from __future__ import annotations

from typing import Annotated

from fastapi import Depends, Header, HTTPException
from fastapi.security import HTTPAuthorizationCredentials

from mrhub.api.dependencies import bearer_scheme
from mrhub.config import get_settings
from mrhub.devices.pairing import DeviceIdentity, DevicePairingRepository


def require_device_scope(scope: str):
    def dependency(
        credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer_scheme)],
        device_id: Annotated[str | None, Header(alias="X-Device-ID")] = None,
    ) -> DeviceIdentity:
        if credentials is None or credentials.scheme.lower() != "bearer" or not device_id:
            raise HTTPException(status_code=401, detail="Paired device authentication required")
        identity = DevicePairingRepository(get_settings().database_path).authenticate(
            access_token=credentials.credentials, device_id=device_id
        )
        if identity is None:
            raise HTTPException(status_code=401, detail="Device credential is invalid, expired, or revoked")
        if scope not in identity.scopes:
            raise HTTPException(status_code=403, detail="Device lacks the required scope")
        return identity

    return dependency
