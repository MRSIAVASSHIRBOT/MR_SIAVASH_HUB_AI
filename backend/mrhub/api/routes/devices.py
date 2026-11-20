"""Owner pairing, registry, heartbeat, and revocation for personal devices."""
from __future__ import annotations

from typing import Annotated, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, ConfigDict, Field

from mrhub.api.dependencies import require_user
from mrhub.api.device_auth import require_device_scope
from mrhub.config import get_settings
from mrhub.devices.contracts import DeviceCapability, DeviceHeartbeatRequest, DevicePlatform
from mrhub.devices.pairing import DeviceIdentity, DevicePairingError, DevicePairingRepository
from mrhub.security.auth import AuthenticatedUser

router = APIRouter(prefix="/devices", tags=["personal-devices"])
DeviceScope = Literal[
    "device.heartbeat",
    "screen.capture",
    "app.launch",
    "ui.inspect",
    "ui.interact",
    "browser.read",
    "browser.interact",
    "files.read_scoped",
]


class PairingChallengeRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    device_id: UUID
    platform: DevicePlatform
    label: str = Field(min_length=1, max_length=64, pattern=r"^[^\\x00-\\x1f\\x7f]+$")
    advertised_capabilities: list[DeviceCapability] = Field(default_factory=list, max_length=16)
    scopes: list[DeviceScope] = Field(default_factory=lambda: ["device.heartbeat"], min_length=1, max_length=8)


class PairingExchangeRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    pairing_code: str = Field(min_length=40, max_length=128)
    device_id: UUID
    agent_version: str = Field(min_length=1, max_length=32, pattern=r"^[A-Za-z0-9.+_-]+$")
    os_version: str = Field(default="unknown", min_length=1, max_length=64)


class DeviceRefreshRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    refresh_token: str = Field(min_length=40, max_length=256)
    device_id: UUID


def get_device_repository() -> DevicePairingRepository:
    return DevicePairingRepository(get_settings().database_path)


@router.post("/pairing-challenges", status_code=status.HTTP_201_CREATED)
def create_pairing_challenge(
    payload: PairingChallengeRequest,
    user: Annotated[AuthenticatedUser, Depends(require_user)],
) -> dict[str, object]:
    try:
        code, expires = get_device_repository().create_challenge(
            owner_user_id=user.user_id,
            device_id=str(payload.device_id),
            platform=payload.platform.value,
            label=payload.label,
            advertised_capabilities=tuple(item.value for item in payload.advertised_capabilities),
            scopes=frozenset(payload.scopes),
        )
    except DevicePairingError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return {
        "pairing_code": code,
        "device_id": str(payload.device_id),
        "expires_at": expires.isoformat(),
        "scopes": sorted(set(payload.scopes)),
    }


@router.post("/pair", status_code=status.HTTP_200_OK)
def exchange_pairing_code(payload: PairingExchangeRequest) -> dict[str, object]:
    try:
        return get_device_repository().exchange(
            pairing_code=payload.pairing_code,
            device_id=str(payload.device_id),
            agent_version=payload.agent_version,
            os_version=payload.os_version,
        )
    except DevicePairingError as exc:
        raise HTTPException(
            status_code=401,
            detail="Pairing code is invalid, expired, or already used",
        ) from exc


@router.post("/refresh")
def refresh_device_credentials(payload: DeviceRefreshRequest) -> dict[str, object]:
    try:
        return get_device_repository().refresh(
            refresh_token=payload.refresh_token,
            device_id=str(payload.device_id),
        )
    except DevicePairingError as exc:
        raise HTTPException(
            status_code=401,
            detail="Refresh credential is invalid, expired, or revoked",
        ) from exc


@router.get("")
def list_devices(
    user: Annotated[AuthenticatedUser, Depends(require_user)],
) -> dict[str, object]:
    devices = get_device_repository().list_devices(user.user_id)
    return {"devices": devices, "count": len(devices)}


@router.delete("/{device_id}")
def revoke_device(
    device_id: UUID,
    user: Annotated[AuthenticatedUser, Depends(require_user)],
) -> dict[str, object]:
    revoked = get_device_repository().revoke(
        owner_user_id=user.user_id,
        device_id=str(device_id),
    )
    if not revoked:
        raise HTTPException(status_code=404, detail="Active device not found")
    return {"device_id": str(device_id), "status": "revoked"}


@router.post("/heartbeat")
def device_heartbeat(
    payload: DeviceHeartbeatRequest,
    identity: Annotated[DeviceIdentity, Depends(require_device_scope("device.heartbeat"))],
) -> dict[str, object]:
    updated = get_device_repository().heartbeat(
        device_id=identity.device_id,
        agent_version=payload.agent_version,
    )
    if not updated:
        raise HTTPException(status_code=401, detail="Device is no longer active")
    return {
        "device_id": identity.device_id,
        "status": "ok",
        "runtime_state": payload.runtime_state,
    }
