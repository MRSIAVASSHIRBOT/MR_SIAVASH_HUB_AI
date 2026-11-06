"""Explicitly registered built-in tools and optional integrations."""

from pydantic import BaseModel, ConfigDict, Field

from mrhub.config import get_settings
from mrhub.domain.tasks import RiskClass
from mrhub.integrations.cloudflare import (
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


def _echo(payload: BaseModel) -> EchoToolOutput:
    value = EchoToolInput.model_validate(payload)
    return EchoToolOutput(text=value.text, character_count=len(value.text))


def _register_cloudflare_tools(
    registry: ToolRegistry,
    client: object,
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
            description="List Cloudflare Worker route metadata through the isolated read-only gateway.",
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


def build_tool_registry() -> ToolRegistry:
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

    # Disabled or incomplete configuration never creates a partially usable tool.
    # The gateway factory fails closed when enabled configuration is invalid.
    client = build_cloudflare_gateway_client(get_settings())
    if client is not None:
        _register_cloudflare_tools(registry, client)
    return registry
