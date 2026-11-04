"""Optional MCP bridge contract and policy tests."""

import json

import anyio
import pytest
from mcp import Client
from pydantic import BaseModel

from mrhub.agents.core import AgentCore, AgentPlanRequest
from mrhub.domain.tasks import RiskClass
from mrhub.integrations.mcp_server import create_mcp_server
from mrhub.providers.router import ModelRouter
from mrhub.providers.stub import StubProvider
from mrhub.security.policy import PolicyDecision, PolicyEngine, PolicyResult
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
async def test_mcp_bridge_uses_explicitly_injected_falsey_registry():
    class FalseyRegistry(ToolRegistry):
        def __bool__(self):
            return False

    registry = FalseyRegistry()
    server = create_mcp_server(registry)
    async with Client(server) as client:
        result = await client.call_tool("hub.list_tools", {})
    assert json.loads(result.content[0].text) == []


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
    called = []

    def external_handler(_payload):
        called.append(True)
        return {"ok": True}

    registry.register(
        ToolDefinition(
            name="custom.external",
            description="Test-only external operation",
            input_model=EmptyInput,
            output_model=EmptyOutput,
            handler=external_handler,
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
    assert called == []


@pytest.mark.anyio
async def test_mcp_bridge_does_not_infer_missing_permission_grants():
    registry = ToolRegistry()
    called = []

    def restricted_handler(_payload):
        called.append(True)
        return {"ok": True}

    registry.register(
        ToolDefinition(
            name="custom.restricted",
            description="Test-only permission-gated operation",
            input_model=EmptyInput,
            output_model=EmptyOutput,
            handler=restricted_handler,
            required_permissions=frozenset({"custom.execute"}),
        )
    )
    server = create_mcp_server(registry)
    async with Client(server) as client:
        result = await client.call_tool(
            "hub.invoke_tool",
            {"name": "custom.restricted", "payload": {}},
        )

    assert json.loads(result.content[0].text) == {
        "ok": False,
        "error_code": "policy_denied",
    }
    assert called == []


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


@pytest.mark.anyio
async def test_mcp_and_agent_share_falsey_injected_policy_authority():
    class FalseyDenyPolicy(PolicyEngine):
        def __bool__(self):
            return False

        def evaluate(self, request):
            return PolicyResult(
                decision=PolicyDecision.DENY,
                reason="Shared integration policy denies this operation",
            )

    policy = FalseyDenyPolicy()
    registry = ToolRegistry(policy=policy)
    called = []

    def restricted_handler(_payload):
        called.append(True)
        return {"ok": True}

    registry.register(
        ToolDefinition(
            name="custom.shared_policy",
            description="Test shared policy authority across Hub and MCP.",
            input_model=EmptyInput,
            output_model=EmptyOutput,
            handler=restricted_handler,
            risk_class=RiskClass.LOW,
        )
    )

    assert registry.policy is policy
    router = ModelRouter()
    router.register_provider(StubProvider())
    agent = AgentCore(router, registry)
    plan = agent.plan(
        AgentPlanRequest(
            goal="Check shared policy authority",
            tools=[{"name": "custom.shared_policy", "payload": {}}],
        )
    )
    assert plan["execution_ready"] is False
    assert plan["steps"][1]["decision"] == PolicyDecision.DENY.value

    server = create_mcp_server(registry)
    async with Client(server) as client:
        result = await client.call_tool(
            "hub.invoke_tool",
            {"name": "custom.shared_policy", "payload": {}},
        )

    assert json.loads(result.content[0].text) == {
        "ok": False,
        "error_code": "policy_denied",
    }
    assert called == []
