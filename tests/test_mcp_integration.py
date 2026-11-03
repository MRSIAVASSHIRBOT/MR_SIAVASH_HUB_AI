""""Optional MCP bridge contract and policy tests."""

import json

import anyio
import pytest
from mcp import Client
from pydantic import BaseModel

from mrhub.domain.tasks import RiskClass
from mrhub.integrations.mcp_server import create_mcp_server
from mrhub.tools.builtins import build_tool_registry
from mrhub.tools.registry import ToolDefinition, ToolRegistry


@pytest.mark.anyio
async def test_mcp_bridge_lists_and_invokes_registered_safe_hub_tool():
    server = create_mcp_server(build_tool_registry())
    async with Client(server) as client:
        catalog = await client.list_tools()
        names = {item.name for item in catalog.tools}
        assert names == {"hub.list_tools", "hub.invoke_tool"}

        result = await client.call_tool(
            "hub.invoke_tool",
            {"name": "text.echo", "payload": {"text": "hello"}},
        )
        assert not result.is_error
        response = json.loads(result.content[0].text)
        assert response == {
            "ok": True,
            "result": {"text": "hello", "character_count": 5},
        }


@pytest.mark.anyio
async def test_mcp_bridge_returns_stable_errors_for_unknown_tools_and_invalid_input():
    server = create_mcp_server(build_tool_registry())
    async with Client(server) as client:
        unknown = await client.call_tool(
            "hub.invoke_tool",
            {"name": "missing.tool", "payload": {}},
        )
        invalid = await client.call_tool(
            "hub.invoke_tool",
            {"name": "text.echo", "payload": {"unexpected": "private-input"}},
        )

    assert json.loads(unknown.content[0].text) == {
        "ok": False,
        "error_code": "tool_not_registered",
    }
    invalid_response = json.loads(invalid.content[0].text)
    assert invalid_response == {
        "ok": False,
        "error_code": "tool_invocation_failed",
    }
    assert "private-input" not in invalid.content[0].text


class EmptyInput(BaseModel):
    pass


class EmptyOutput(BaseModel):
    ok: bool


def test_mcp_bridge_does_not_bypass_policy_for_external_side_effects():
    registry = ToolRegistry()
    registry.register(
        ToolDefinition(
            name="custom.external",
            description="Test-only external operation",
            input_model=EmptyInput,
            output_model=EmptyOutput,
            handler=lambda _payload: {"ok": True},
            risk_class=RiskClass.LOW,
            external_side_effect=True,
        )
    )
    server = create_mcp_server(registry)

    async def invoke():
        async with Client(server) as client:
            return await client.call_tool(
                "hub.invoke_tool",
                {"name": "custom.external", "payload": {}},
            )

    result = anyio.run(invoke)
    assert not result.is_error
    response = json.loads(result.content[0].text)
    assert response == {"ok": False, "error_code": "policy_denied"}


def test_mcp_bridge_does_not_expose_handler_exception_details():
    registry = ToolRegistry()

    def fail(_payload):
        raise RuntimeError("sensitive-internal-detail")

    registry.register(
        ToolDefinition(
            name="custom.failure",
            description="Test-only failing operation",
            input_model=EmptyInput,
            output_model=EmptyOutput,
            handler=fail,
            risk_class=RiskClass.LOW,
        )
    )
    server = create_mcp_server(registry)

    async def invoke():
        async with Client(server) as client:
            return await client.call_tool(
                "hub.invoke_tool",
                {"name": "custom.failure", "payload": {}},
            )

    result = anyio.run(invoke)
    assert not result.is_error
    assert json.loads(result.content[0].text) == {
        "ok": False,
        "error_code": "tool_invocation_failed",
    }
    assert "sensitive-internal-detail" not in result.content[0].text
