"""Strict, non-authoritative contracts for paired personal device companions.

Device-reported capabilities are descriptive only. Authorization is owned by Hub policy.
"""

from __future__ import annotations

from enum import StrEnum
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator


class DevicePlatform(StrEnum):
    WINDOWS = "windows"
    ANDROID = "android"
    BROWSER = "browser"


class DeviceCapability(StrEnum):
    DEVICE_HEARTBEAT = "device.heartbeat"
    SCREEN_CAPTURE = "screen.capture"
    APP_LAUNCH = "app.launch"
    UI_INSPECT = "ui.inspect"
    UI_INTERACT = "ui.interact"
    BROWSER_READ = "browser.read"
    BROWSER_INTERACT = "browser.interact"
    FILE_READ_SCOPED = "files.read_scoped"


class DeviceStatus(StrEnum):
    ACTIVE = "active"
    REVOKED = "revoked"
    OFFLINE = "offline"


class DeviceDescriptor(BaseModel):
    """A companion's bounded self-description; never an authorization grant."""

    model_config = ConfigDict(extra="forbid", frozen=True, str_strip_whitespace=True)

    device_id: UUID
    platform: DevicePlatform
    label: str = Field(min_length=1, max_length=64, pattern=r"^[^\x00-\x1f\x7f]+$")
    agent_version: str = Field(min_length=1, max_length=32, pattern=r"^[A-Za-z0-9.+_-]+$")
    os_version: str = Field(default="unknown", min_length=1, max_length=64)
    advertised_capabilities: list[DeviceCapability] = Field(default_factory=list, max_length=16)

    @field_validator("advertised_capabilities")
    @classmethod
    def unique_capabilities(
        cls, value: list[DeviceCapability]
    ) -> list[DeviceCapability]:
        if len(value) != len(set(value)):
            raise ValueError("Device capabilities must be unique")
        return value


class DeviceHeartbeatRequest(BaseModel):
    """Small operational heartbeat; excludes screenshots and user activity content."""

    model_config = ConfigDict(extra="forbid", frozen=True, str_strip_whitespace=True)

    agent_version: str = Field(min_length=1, max_length=32, pattern=r"^[A-Za-z0-9.+_-]+$")
    runtime_state: Literal["ready", "busy", "degraded"] = "ready"
    app_uptime_seconds: int = Field(ge=0, le=31_536_000, strict=True)
    last_task_id: UUID | None = None


class DeviceSummary(BaseModel):
    """Owner-visible device status with granted and advertised capabilities separated."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    device_id: UUID
    platform: DevicePlatform
    label: str
    status: DeviceStatus
    advertised_capabilities: list[DeviceCapability]
    granted_scopes: list[str]
    created_at: str
    last_seen_at: str | None = None
    revoked_at: str | None = None
