"""Explicitly registered built-in tools and optional integrations."""

import re
from datetime import UTC, date, datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator

from mrhub.config import get_settings
from mrhub.domain.tasks import RiskClass
from mrhub.devices.pairing import DevicePairingRepository
from mrhub.devices.tasks import DeviceTaskRepository
from mrhub.integrations.cloudflare import (
    BindingMetadata,
    CloudflareGatewayClient,
    D1DatabaseSummary,
    WorkerRoute,
    WorkerSettingsSummary,
    WorkerSummary,
    build_cloudflare_gateway_client,
)
from mrhub.tools.registry import ToolDefinition, ToolRegistry


class EchoToolInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    text: str = Field(min_length=1, max_length=500)


class EchoToolOutput(BaseModel):
    text: str
    character_count: int = Field(ge=1, le=500)


class EmptyToolInput(BaseModel):
    model_config = ConfigDict(extra="forbid")


class DeviceRegistryItem(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    device_id: str = Field(min_length=36, max_length=36, pattern=r"^[0-9a-f-]{36}$")
    platform: Literal["windows", "android", "browser"]
    label: str = Field(min_length=1, max_length=64)
    status: Literal["active", "revoked"]
    granted_scopes: list[str] = Field(max_length=8)
    last_seen_at: str | None = Field(default=None, max_length=40)
    runtime_state: Literal["unknown", "ready", "busy", "degraded"]
    app_uptime_seconds: int = Field(ge=0, le=31_536_000)


class DeviceRegistryOutput(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    devices: list[DeviceRegistryItem] = Field(max_length=100)
    count: int = Field(ge=0, le=100)


class DeviceAppLaunchInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    device_id: UUID
    app: Literal["notepad", "calculator", "explorer", "browser", "chatgpt"]
    idempotency_key: UUID
    scheduled_at: datetime | None = None
    expires_in_seconds: int = Field(default=300, ge=60, le=86_400, strict=True)
    timeout_seconds: int = Field(default=30, ge=5, le=60, strict=True)

    @model_validator(mode="after")
    def require_timezone_for_schedule(self) -> "DeviceAppLaunchInput":
        if self.scheduled_at is not None and (
            self.scheduled_at.tzinfo is None or self.scheduled_at.utcoffset() is None
        ):
            raise ValueError("scheduled_at must include a timezone offset")
        return self


class DeviceTaskSummary(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    task_id: str = Field(min_length=36, max_length=36)
    device_id: str = Field(min_length=36, max_length=36)
    action: Literal["app.launch"]
    app: Literal["notepad", "calculator", "explorer", "browser", "chatgpt"]
    required_scope: Literal["app.launch"]
    status: Literal[
        "queued", "claimed", "reported_succeeded", "reported_failed",
        "cancelled", "expired", "unknown_outcome"
    ]
    scheduled_at: str = Field(min_length=20, max_length=40)
    expires_at: str = Field(min_length=20, max_length=40)
    owner_confirmed: bool


class DeviceAppLaunchOutput(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    task: DeviceTaskSummary
    idempotent_replay: bool


class CloudflareWorkersOutput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    workers: list[WorkerSummary]


class CloudflareRoutesOutput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    routes: list[WorkerRoute]


class CloudflareD1Output(BaseModel):
    model_config = ConfigDict(extra="forbid")

    databases: list[D1DatabaseSummary]


class CloudflareWorkerSettingsInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    script_name: str = Field(
        min_length=1,
        max_length=63,
        pattern=r"^[a-z0-9_][a-z0-9_-]{0,62}$",
    )


class CloudflareWorkerSettingsOutput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    settings: WorkerSettingsSummary


class CloudflareInventorySnapshotOutput(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    observed_at: str = Field(min_length=20, max_length=40)
    workers: list[WorkerSummary] = Field(max_length=1_000)
    routes: list[WorkerRoute] = Field(max_length=1_000)
    databases: list[D1DatabaseSummary] = Field(max_length=1_000)
    worker_count: int = Field(ge=0, le=1_000)
    route_count: int = Field(ge=0, le=1_000)
    database_count: int = Field(ge=0, le=1_000)
    read_only: Literal[True] = True
    deployment_performed: Literal[False] = False


class CloudflareWorkerSettingsPreviewInput(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    script_name: str = Field(
        min_length=1,
        max_length=63,
        pattern=r"^[a-z0-9_][a-z0-9_-]{0,62}$",
    )
    compatibility_date: str = Field(min_length=10, max_length=10)
    bindings: list[BindingMetadata] = Field(max_length=100)

    @model_validator(mode="after")
    def validate_proposal(self) -> "CloudflareWorkerSettingsPreviewInput":
        try:
            parsed_date = date.fromisoformat(self.compatibility_date)
        except ValueError as exc:
            raise ValueError("compatibility_date must be a real ISO calendar date") from exc
        if parsed_date.isoformat() != self.compatibility_date:
            raise ValueError("compatibility_date must use canonical YYYY-MM-DD format")
        names = [binding.name for binding in self.bindings]
        if len(names) != len(set(names)):
            raise ValueError("proposed binding names must be unique")
        if any(
            not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]{0,127}", name)
            for name in names
        ):
            raise ValueError("proposed binding names must be safe identifiers")
        return self


class CloudflareSettingChange(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    field: Literal["compatibility_date", "binding"]
    action: Literal["add", "remove", "change"]
    name: str | None = None
    current: str | None = None
    proposed: str | None = None


class CloudflareWorkerSettingsPreviewOutput(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    script_name: str
    current: WorkerSettingsSummary
    proposed: WorkerSettingsSummary
    changes: list[CloudflareSettingChange] = Field(max_length=201)
    read_only: Literal[True] = True
    deployment_performed: Literal[False] = False


def _echo(payload: BaseModel) -> EchoToolOutput:
    value = EchoToolInput.model_validate(payload)
    return EchoToolOutput(text=value.text, character_count=len(value.text))


def _register_device_tools(
    registry: ToolRegistry,
    *,
    database_path,
    owner_user_id: str,
) -> None:
    """Register owner-bound, scope-checked device tools for this authenticated owner."""

    def list_owner_devices(_payload: BaseModel) -> dict[str, object]:
        devices = DevicePairingRepository(database_path).list_devices(owner_user_id)
        summaries = [
            {
                "device_id": item["device_id"],
                "platform": item["platform"],
                "label": item["label"],
                "status": item["status"],
                "granted_scopes": item["granted_scopes"],
                "last_seen_at": item["last_seen_at"],
                "runtime_state": item["runtime_state"],
                "app_uptime_seconds": item["app_uptime_seconds"],
            }
            for item in devices
        ]
        return {"devices": summaries, "count": len(summaries)}

    def submit_app_launch(payload: BaseModel) -> dict[str, object]:
        request = DeviceAppLaunchInput.model_validate(payload)
        devices = DevicePairingRepository(database_path).list_devices(owner_user_id)
        selected = next(
            (item for item in devices if item["device_id"] == str(request.device_id)),
            None,
        )
        if selected is None or selected["status"] != "active":
            raise ValueError("Selected owner device is not active.")
        supported_aliases = {
            "windows": {"notepad", "calculator", "explorer", "browser", "chatgpt"},
            "android": {"browser", "chatgpt"},
            "browser": set(),
        }
        if request.app not in supported_aliases.get(str(selected["platform"]), set()):
            raise ValueError("Selected application is not supported on this device platform.")

        task, created = DeviceTaskRepository(database_path).create(
            owner_user_id=owner_user_id,
            device_id=str(request.device_id),
            action="app.launch",
            app=request.app,
            required_scope="app.launch",
            idempotency_key=str(request.idempotency_key),
            owner_confirmed=False,
            scheduled_at=request.scheduled_at,
            expires_in_seconds=request.expires_in_seconds,
            timeout_seconds=request.timeout_seconds,
        )
        return {"task": task, "idempotent_replay": not created}

    registry.register(
        ToolDefinition(
            name="device.registry.list",
            description="List only this owner's paired-device metadata and explicitly granted scopes.",
            input_model=EmptyToolInput,
            output_model=DeviceRegistryOutput,
            handler=list_owner_devices,
            risk_class=RiskClass.LOW,
            required_permissions=frozenset({"device.registry.read"}),
        )
    )
    registry.register(
        ToolDefinition(
            name="device.app_launch.submit",
            description="Queue one allowlisted app launch for an active owner device with app.launch scope.",
            input_model=DeviceAppLaunchInput,
            output_model=DeviceAppLaunchOutput,
            handler=submit_app_launch,
            risk_class=RiskClass.LOW,
            required_permissions=frozenset({"device.registry.read", "device.app_launch"}),
        )
    )


def _register_cloudflare_tools(
    registry: ToolRegistry,
    client: CloudflareGatewayClient,
) -> None:
    """Register only fixed read-only operations behind the owner grant gate."""

    def list_workers(_payload: BaseModel) -> dict[str, object]:
        workers = client.list_workers()
        return {"workers": [item.model_dump(mode="json") for item in workers]}

    def list_routes(_payload: BaseModel) -> dict[str, object]:
        routes = client.list_worker_routes()
        return {"routes": [item.model_dump(mode="json") for item in routes]}

    def list_databases(_payload: BaseModel) -> dict[str, object]:
        databases = client.list_d1_databases()
        return {"databases": [item.model_dump(mode="json") for item in databases]}

    def read_worker_settings(payload: BaseModel) -> dict[str, object]:
        value = CloudflareWorkerSettingsInput.model_validate(payload)
        settings = client.get_worker_settings(value.script_name)
        return {"settings": settings.model_dump(mode="json")}

    def inventory_snapshot(_payload: BaseModel) -> dict[str, object]:
        workers = client.list_workers()
        routes = client.list_worker_routes()
        databases = client.list_d1_databases()
        return {
            "observed_at": datetime.now(UTC).isoformat(),
            "workers": [item.model_dump(mode="json") for item in workers],
            "routes": [item.model_dump(mode="json") for item in routes],
            "databases": [item.model_dump(mode="json") for item in databases],
            "worker_count": len(workers),
            "route_count": len(routes),
            "database_count": len(databases),
            "read_only": True,
            "deployment_performed": False,
        }

    def preview_worker_settings(payload: BaseModel) -> dict[str, object]:
        value = CloudflareWorkerSettingsPreviewInput.model_validate(payload)
        current = client.get_worker_settings(value.script_name)
        proposed_bindings = sorted(value.bindings, key=lambda item: item.name)
        proposed = WorkerSettingsSummary(
            compatibility_date=value.compatibility_date,
            usage_model=current.usage_model,
            bindings=proposed_bindings,
        )
        changes: list[dict[str, object]] = []
        if current.compatibility_date != proposed.compatibility_date:
            changes.append({
                "field": "compatibility_date",
                "action": "add" if current.compatibility_date is None else "change",
                "name": None,
                "current": current.compatibility_date,
                "proposed": proposed.compatibility_date,
            })
        current_bindings = {item.name: item.type for item in current.bindings}
        proposed_map = {item.name: item.type for item in proposed.bindings}
        for name in sorted(current_bindings.keys() | proposed_map.keys()):
            old_type = current_bindings.get(name)
            new_type = proposed_map.get(name)
            if old_type == new_type:
                continue
            changes.append({
                "field": "binding",
                "action": (
                    "add" if old_type is None
                    else "remove" if new_type is None
                    else "change"
                ),
                "name": name,
                "current": old_type,
                "proposed": new_type,
            })
        return {
            "script_name": value.script_name,
            "current": current.model_dump(mode="json"),
            "proposed": proposed.model_dump(mode="json"),
            "changes": changes,
            "read_only": True,
            "deployment_performed": False,
        }

    permission = frozenset({"cloudflare.read"})
    registry.register(
        ToolDefinition(
            name="cloudflare.workers.list",
            description="List Cloudflare Worker metadata through the isolated read-only gateway.",
            input_model=EmptyToolInput,
            output_model=CloudflareWorkersOutput,
            handler=list_workers,
            risk_class=RiskClass.LOW,
            required_permissions=permission,
        )
    )
    registry.register(
        ToolDefinition(
            name="cloudflare.worker_routes.list",
            description=(
                "List Cloudflare Worker route metadata through the isolated read-only gateway."
            ),
            input_model=EmptyToolInput,
            output_model=CloudflareRoutesOutput,
            handler=list_routes,
            risk_class=RiskClass.LOW,
            required_permissions=permission,
        )
    )
    registry.register(
        ToolDefinition(
            name="cloudflare.d1_databases.list",
            description="List Cloudflare D1 database metadata without reading database rows.",
            input_model=EmptyToolInput,
            output_model=CloudflareD1Output,
            handler=list_databases,
            risk_class=RiskClass.LOW,
            required_permissions=permission,
        )
    )
    registry.register(
        ToolDefinition(
            name="cloudflare.worker.settings.read",
            description="Read projected Cloudflare Worker settings and binding names/types only.",
            input_model=CloudflareWorkerSettingsInput,
            output_model=CloudflareWorkerSettingsOutput,
            handler=read_worker_settings,
            risk_class=RiskClass.LOW,
            required_permissions=permission,
        )
    )
    registry.register(
        ToolDefinition(
            name="cloudflare.inventory.snapshot",
            description=(
                "Capture one bounded, read-only snapshot of Worker, route, and D1 metadata."
            ),
            input_model=EmptyToolInput,
            output_model=CloudflareInventorySnapshotOutput,
            handler=inventory_snapshot,
            risk_class=RiskClass.LOW,
            required_permissions=permission,
        )
    )
    registry.register(
        ToolDefinition(
            name="cloudflare.worker.settings.diff_preview",
            description=(
                "Compare proposed Worker compatibility date and binding metadata with "
                "current settings; never deploys or mutates resources."
            ),
            input_model=CloudflareWorkerSettingsPreviewInput,
            output_model=CloudflareWorkerSettingsPreviewOutput,
            handler=preview_worker_settings,
            risk_class=RiskClass.LOW,
            required_permissions=permission,
        )
    )


def build_tool_registry(*, correlation_id: str | None = None, owner_user_id: str | None = None) -> ToolRegistry:
    registry = ToolRegistry()
    registry.register(
        ToolDefinition(
            name="text.echo",
            description="Return the supplied text unchanged; performs no external action.",
            input_model=EchoToolInput,
            output_model=EchoToolOutput,
            handler=_echo,
        )
    )

    # Device tools are registered only inside an authenticated owner's context.
    # Possessing a device ID is never sufficient: server-side expiring grants and
    # the device's exact app.launch scope are both checked at execution time.
    settings = get_settings()
    if owner_user_id is not None:
        _register_device_tools(
            registry,
            database_path=settings.database_path,
            owner_user_id=owner_user_id,
        )

    # Disabled or incomplete configuration never creates a partially usable tool.
    # The gateway factory fails closed when enabled configuration is invalid.
    settings = get_settings()
    client = (
        build_cloudflare_gateway_client(settings)
        if correlation_id is None
        else build_cloudflare_gateway_client(settings, correlation_id=correlation_id)
    )
    if client is not None:
        _register_cloudflare_tools(registry, client)
    return registry
