"""Owner pairing, registry, heartbeat, and revocation for personal devices."""
from __future__ import annotations

from datetime import UTC, datetime
from typing import Annotated, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, ConfigDict, Field, field_validator

from mrhub.api.dependencies import require_user
from mrhub.api.device_auth import require_device_scope
from mrhub.config import get_settings
from mrhub.devices.contracts import DeviceCapability, DeviceHeartbeatRequest, DevicePlatform
from mrhub.devices.pairing import DeviceIdentity, DevicePairingError, DevicePairingRepository
from mrhub.devices.tasks import DeviceTaskError, DeviceTaskRepository
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
    label: str = Field(min_length=1, max_length=64, pattern=r"^[^\x00-\x1f\x7f]+$")
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


class DeviceTaskCreateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    action: Literal["launch_app"] = "launch_app"
    app_alias: Literal["notepad", "calculator", "explorer", "browser", "chatgpt"]
    idempotency_key: UUID
    scheduled_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    expires_in_seconds: int = Field(default=300, ge=30, le=86400, strict=True)

    @field_validator("scheduled_at")
    @classmethod
    def require_timezone(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("scheduled_at must include a timezone offset")
        return value


class DeviceTaskCompleteRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    outcome: Literal["succeeded", "failed"]
    result_code: Literal["launched", "launch_failed", "app_not_available", "unsupported_platform"]


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


def get_device_task_repository() -> DeviceTaskRepository:
    return DeviceTaskRepository(get_settings().database_path)


@router.post("/tasks/claim")
def claim_device_task(
    identity: Annotated[DeviceIdentity, Depends(require_device_scope("app.launch"))],
) -> dict[str, object]:
    task = get_device_task_repository().claim_next(
        owner_user_id=identity.owner_user_id,
        device_id=identity.device_id,
    )
    return {"task": task}


@router.post("/tasks/{task_id}/complete")
def complete_device_task(
    task_id: UUID,
    payload: DeviceTaskCompleteRequest,
    identity: Annotated[DeviceIdentity, Depends(require_device_scope("app.launch"))],
) -> dict[str, object]:
    try:
        task = get_device_task_repository().complete_device_task(
            device_id=identity.device_id,
            task_id=str(task_id),
            outcome=payload.outcome,
            result_code=payload.result_code,
        )
    except DeviceTaskError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return {"task": task}


@router.post("/{device_id}/tasks", status_code=status.HTTP_201_CREATED)
def create_owner_device_task(
    device_id: UUID,
    payload: DeviceTaskCreateRequest,
    user: Annotated[AuthenticatedUser, Depends(require_user)],
) -> dict[str, object]:
    try:
        task = get_device_task_repository().create_owner_task(
            owner_user_id=user.user_id,
            device_id=str(device_id),
            app_alias=payload.app_alias,
            idempotency_key=str(payload.idempotency_key),
            scheduled_at=payload.scheduled_at,
            expires_in_seconds=payload.expires_in_seconds,
        )
    except DeviceTaskError as exc:
        message = str(exc)
        code = 403 if "scope" in message else 404 if "device not found" in message else 409
        raise HTTPException(status_code=code, detail=message) from exc
    return {"task": task}


@router.get("/{device_id}/tasks")
def list_owner_device_tasks(
    device_id: UUID,
    user: Annotated[AuthenticatedUser, Depends(require_user)],
) -> dict[str, object]:
    tasks = get_device_task_repository().list_owner_tasks(
        owner_user_id=user.user_id,
        device_id=str(device_id),
    )
    return {"tasks": tasks, "count": len(tasks)}


@router.delete("/{device_id}/tasks/{task_id}")
def cancel_owner_device_task(
    device_id: UUID,
    task_id: UUID,
    user: Annotated[AuthenticatedUser, Depends(require_user)],
) -> dict[str, object]:
    state = get_device_task_repository().cancel_owner_task(
        owner_user_id=user.user_id,
        device_id=str(device_id),
        task_id=str(task_id),
    )
    if state is None:
        raise HTTPException(status_code=404, detail="Device task not found")
    if state != "cancelled":
        raise HTTPException(
            status_code=409,
            detail=f"Task is {state}; only queued tasks can be cancelled safely",
        )
    return {"task_id": str(task_id), "status": "cancelled"}
