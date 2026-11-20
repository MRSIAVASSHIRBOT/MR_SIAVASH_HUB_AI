"""Owner pairing, registry, heartbeat, and revocation for personal devices."""
from __future__ import annotations

from typing import Annotated, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, Header, HTTPException, Response, status
from pydantic import BaseModel, ConfigDict, Field, model_validator

from mrhub.api.dependencies import require_user
from mrhub.api.device_auth import require_device_scope
from mrhub.config import get_settings
from mrhub.devices.contracts import DeviceCapability, DeviceHeartbeatRequest, DevicePlatform
from mrhub.devices.pairing import DeviceIdentity, DevicePairingError, DevicePairingRepository
from mrhub.devices.tasks import (
    DeviceTaskConflict,
    DeviceTaskNotFound,
    DeviceTaskPermissionError,
    DeviceTaskRepository,
)
from mrhub.domain.tasks import RiskClass
from mrhub.security.auth import AuthenticatedUser
from mrhub.security.policy import ActionRequest, PolicyDecision, PolicyEngine

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
    model_config = ConfigDict(extra="forbid", frozen=True)

    action: Literal["app.launch", "screen.capture"]
    app: Literal["notepad", "calculator", "explorer", "browser", "chatgpt"] | None = None
    timeout_seconds: int = Field(default=30, ge=5, le=60, strict=True)
    expires_in_seconds: int = Field(default=300, ge=60, le=900, strict=True)
    confirm_sensitive_action: bool = Field(default=False, strict=True)

    @model_validator(mode="after")
    def validate_action_parameters(self):
        if self.action == "app.launch" and self.app is None:
            raise ValueError("app.launch requires an allow-listed app")
        if self.action == "screen.capture" and self.app is not None:
            raise ValueError("screen.capture does not accept app parameters")
        if self.action == "screen.capture" and not self.confirm_sensitive_action:
            raise ValueError("screen.capture requires explicit owner confirmation")
        return self


class DeviceTaskOutcomeRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    lease_token: str = Field(min_length=40, max_length=128)
    outcome: Literal["succeeded", "failed"]
    error_code: Literal[
        "app_not_available", "permission_denied", "timeout", "execution_failed"
    ] | None = None
    duration_ms: int = Field(default=0, ge=0, le=60_000, strict=True)

    @model_validator(mode="after")
    def validate_outcome(self):
        if self.outcome == "succeeded" and self.error_code is not None:
            raise ValueError("Successful outcomes cannot include an error code")
        if self.outcome == "failed" and self.error_code is None:
            raise ValueError("Failed outcomes require a bounded error code")
        return self


def get_device_repository() -> DevicePairingRepository:
    return DevicePairingRepository(get_settings().database_path)


def get_device_task_repository() -> DeviceTaskRepository:
    return DeviceTaskRepository(get_settings().database_path)


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
        runtime_state=payload.runtime_state,
        app_uptime_seconds=payload.app_uptime_seconds,
        last_task_id=str(payload.last_task_id) if payload.last_task_id else None,
    )
    if not updated:
        raise HTTPException(status_code=401, detail="Device is no longer active")
    return {
        "device_id": identity.device_id,
        "status": "ok",
        "runtime_state": payload.runtime_state,
        "app_uptime_seconds": payload.app_uptime_seconds,
        "last_task_id": str(payload.last_task_id) if payload.last_task_id else None,
    }


@router.post("/{device_id}/tasks", status_code=status.HTTP_201_CREATED)
def submit_device_task(
    device_id: UUID,
    payload: DeviceTaskCreateRequest,
    response: Response,
    user: Annotated[AuthenticatedUser, Depends(require_user)],
    idempotency_key: Annotated[str, Header(alias="Idempotency-Key", min_length=8, max_length=128)],
) -> dict[str, object]:
    required_scope = "app.launch" if payload.action == "app.launch" else "screen.capture"
    risk_class = RiskClass.LOW if payload.action == "app.launch" else RiskClass.HIGH
    decision = PolicyEngine().evaluate(ActionRequest(
        action=f"device.{payload.action}",
        risk_class=risk_class,
        user_approved=payload.confirm_sensitive_action,
    ))
    if decision.decision is not PolicyDecision.ALLOW:
        raise HTTPException(status_code=403, detail="Device action requires explicit owner confirmation")
    try:
        task, created = get_device_task_repository().create(
            owner_user_id=user.user_id,
            device_id=str(device_id),
            action=payload.action,
            app=payload.app,
            required_scope=required_scope,
            idempotency_key=idempotency_key,
            owner_confirmed=payload.confirm_sensitive_action,
            expires_in_seconds=payload.expires_in_seconds,
            timeout_seconds=payload.timeout_seconds,
        )
    except DeviceTaskNotFound as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except DeviceTaskPermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except DeviceTaskConflict as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    if not created:
        response.status_code = status.HTTP_200_OK
        return {**task, "idempotent_replay": True}
    return task


@router.post("/tasks/claim")
def claim_device_task(
    identity: Annotated[DeviceIdentity, Depends(require_device_scope("device.heartbeat"))],
) -> dict[str, object]:
    try:
        claimed = get_device_task_repository().claim(
            owner_user_id=identity.owner_user_id,
            device_id=identity.device_id,
            granted_scopes=identity.scopes,
        )
    except DeviceTaskNotFound as exc:
        raise HTTPException(status_code=401, detail="Paired device is no longer active") from exc
    return claimed if claimed is not None else {"task": None}


@router.post("/tasks/{task_id}/outcome")
def report_device_task_outcome(
    task_id: UUID,
    payload: DeviceTaskOutcomeRequest,
    identity: Annotated[DeviceIdentity, Depends(require_device_scope("device.heartbeat"))],
) -> dict[str, object]:
    result = get_device_task_repository().report_outcome(
        owner_user_id=identity.owner_user_id,
        device_id=identity.device_id,
        task_id=str(task_id),
        lease_token=payload.lease_token,
        outcome=payload.outcome,
        error_code=payload.error_code,
        duration_ms=payload.duration_ms,
    )
    if result is None:
        raise HTTPException(status_code=409, detail="Task lease is invalid, expired, or no longer active")
    return result


@router.get("/{device_id}/tasks/{task_id}")
def get_device_task(
    device_id: UUID,
    task_id: UUID,
    user: Annotated[AuthenticatedUser, Depends(require_user)],
) -> dict[str, object]:
    result = get_device_task_repository().get_for_owner(
        owner_user_id=user.user_id,
        device_id=str(device_id),
        task_id=str(task_id),
    )
    if result is None:
        raise HTTPException(status_code=404, detail="Device task not found")
    return result


@router.delete("/{device_id}/tasks/{task_id}")
def cancel_device_task(
    device_id: UUID,
    task_id: UUID,
    user: Annotated[AuthenticatedUser, Depends(require_user)],
) -> dict[str, object]:
    try:
        result = get_device_task_repository().cancel_for_owner(
            owner_user_id=user.user_id,
            device_id=str(device_id),
            task_id=str(task_id),
        )
    except DeviceTaskConflict as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    if result is None:
        raise HTTPException(status_code=404, detail="Device task not found")
    return result

