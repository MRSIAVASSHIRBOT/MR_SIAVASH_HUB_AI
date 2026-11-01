import pytest
from pydantic import BaseModel, Field

from mrhub.domain.tasks import RiskClass
from mrhub.security.policy import PolicyDecision
from mrhub.tools.builtins import build_tool_registry
from mrhub.tools.registry import ToolDefinition, ToolPolicyError, ToolRegistry


class InputValue(BaseModel):
    value: str = Field(min_length=1, max_length=20)


class OutputValue(BaseModel):
    value: str


def test_builtin_echo_tool_validates_and_returns_typed_output():
    result = build_tool_registry().invoke("text.echo", {"text": "hello"})
    assert result == {"text": "hello", "character_count": 5}


def test_registry_rejects_unregistered_tools():
    with pytest.raises(LookupError):
        build_tool_registry().invoke("shell.execute", {"command": "not allowed"})


def test_registry_rejects_duplicate_and_invalid_names():
    registry = ToolRegistry()
    definition = ToolDefinition(
        name="custom.echo",
        description="A test tool",
        input_model=InputValue,
        output_model=OutputValue,
        handler=lambda payload: {"value": payload.value},
    )
    registry.register(definition)
    with pytest.raises(ValueError, match="already registered"):
        registry.register(definition)
    with pytest.raises(ValueError, match="Invalid tool name"):
        registry.register(
            ToolDefinition(
                name="Bad Name",
                description="Invalid name",
                input_model=InputValue,
                output_model=OutputValue,
                handler=lambda payload: {"value": payload.value},
            )
        )


def test_registry_enforces_server_supplied_permissions():
    registry = ToolRegistry()
    registry.register(
        ToolDefinition(
            name="custom.restricted",
            description="Requires a server-granted permission",
            input_model=InputValue,
            output_model=OutputValue,
            handler=lambda payload: {"value": payload.value},
            required_permissions=frozenset({"custom.execute"}),
        )
    )
    with pytest.raises(ToolPolicyError) as error:
        registry.invoke("custom.restricted", {"value": "x"})
    assert error.value.decision is PolicyDecision.DENY


def test_registry_requires_approval_for_external_side_effects():
    registry = ToolRegistry()
    registry.register(
        ToolDefinition(
            name="custom.external",
            description="An external operation",
            input_model=InputValue,
            output_model=OutputValue,
            handler=lambda payload: {"value": payload.value},
            risk_class=RiskClass.LOW,
            external_side_effect=True,
        )
    )
    with pytest.raises(ToolPolicyError) as error:
        registry.invoke("custom.external", {"value": "x"})
    assert error.value.decision is PolicyDecision.REQUIRE_APPROVAL


def test_registry_validates_input_before_handler_invocation():
    called = []
    registry = ToolRegistry()
    registry.register(
        ToolDefinition(
            name="custom.validated",
            description="Input validation test",
            input_model=InputValue,
            output_model=OutputValue,
            handler=lambda payload: called.append(payload) or {"value": payload.value},
        )
    )
    with pytest.raises(ValueError):
        registry.invoke("custom.validated", {"unexpected": "field"})
    assert called == []
