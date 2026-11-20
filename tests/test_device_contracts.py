from __future__ import annotations

import pytest
from pydantic import ValidationError

from mrhub.devices.contracts import (
    DeviceCapability,
    DeviceDescriptor,
    DeviceHeartbeatRequest,
    DevicePlatform,
)


def test_device_descriptor_accepts_bounded_windows_companion():
    descriptor = DeviceDescriptor(
        device_id="a4e1b9cc-cb55-4c2d-aed0-c8e1ec9c40f4",
        platform=DevicePlatform.WINDOWS,
        label="Siavash Windows workstation",
        agent_version="0.1.0",
        os_version="Windows 11",
        advertised_capabilities=[
            DeviceCapability.DEVICE_HEARTBEAT,
            DeviceCapability.SCREEN_CAPTURE,
        ],
    )

    assert descriptor.platform == DevicePlatform.WINDOWS
    assert descriptor.advertised_capabilities == [
        DeviceCapability.DEVICE_HEARTBEAT,
        DeviceCapability.SCREEN_CAPTURE,
    ]


def test_device_descriptor_rejects_unknown_fields_and_capabilities():
    with pytest.raises(ValidationError):
        DeviceDescriptor(
            device_id="a4e1b9cc-cb55-4c2d-aed0-c8e1ec9c40f4",
            platform="windows",
            label="Workstation",
            agent_version="0.1.0",
            arbitrary_shell=True,
        )

    with pytest.raises(ValidationError):
        DeviceDescriptor(
            device_id="a4e1b9cc-cb55-4c2d-aed0-c8e1ec9c40f4",
            platform="windows",
            label="Workstation",
            agent_version="0.1.0",
            advertised_capabilities=["shell.execute"],
        )


def test_device_descriptor_rejects_duplicate_capabilities_and_control_chars():
    base = {
        "device_id": "a4e1b9cc-cb55-4c2d-aed0-c8e1ec9c40f4",
        "platform": "windows",
        "label": "Workstation",
        "agent_version": "0.1.0",
    }
    with pytest.raises(ValidationError):
        DeviceDescriptor(
            **base,
            advertised_capabilities=["device.heartbeat", "device.heartbeat"],
        )
    with pytest.raises(ValidationError):
        DeviceDescriptor(**{**base, "label": "Bad\nLabel"})


def test_heartbeat_is_bounded_and_rejects_content_fields():
    heartbeat = DeviceHeartbeatRequest(
        agent_version="0.1.0",
        runtime_state="ready",
        app_uptime_seconds=120,
    )
    assert heartbeat.app_uptime_seconds == 120

    with pytest.raises(ValidationError):
        DeviceHeartbeatRequest(
            agent_version="0.1.0",
            runtime_state="ready",
            app_uptime_seconds=120,
            screenshot_base64="not-allowed",
        )

    with pytest.raises(ValidationError):
        DeviceHeartbeatRequest(
            agent_version="0.1.0",
            runtime_state="ready",
            app_uptime_seconds=40_000_000,
        )
