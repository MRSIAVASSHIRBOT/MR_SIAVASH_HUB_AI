import pytest
from pydantic import BaseModel, Field

from mrhub.domain.tasks import RiskClass
from mrhub.security.policy import PolicyDecision
from mrhub.tools.builtins import build_tool_registry
from mrhub.tools.registry import (
    ReplaySafety,
    ToolDefinition,
    ToolExecutionError,
    ToolLifecycleEvent,
    ToolLifecycleStage,
    ToolPolicyError,
    ToolRegistry,
)


class InputValue(BaseModel):
    value: str = Field(min_length=1, max_length=20)


class OutputValue(BaseModel):
    value: str


def test_builtin_echo_tool_validates_and_returns_typed_output():
    result = build_tool_registry().invoke("text.echo", {"text": "hello"})
    assert result == {"text": "hello", "character_count": 5}


def test_builtin_echo_tool_is_explicitly_retry_safe():
    registry = build_tool_registry()
    tool = registry.get("text.echo")

    assert tool.replay_safety.value == "retry_safe"
    assert registry.catalog()[0]["replay_safety"] == "retry_safe"


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



def test_registry_sanitizes_invalid_handler_output():
    registry = ToolRegistry()
    registry.register(
        ToolDefinition(
            name="custom.invalid_output",
            description="A tool with an invalid test output",
            input_model=InputValue,
            output_model=OutputValue,
            handler=lambda _payload: {"unexpected": "private output"},
        )
    )
    with pytest.raises(ToolExecutionError, match="Tool output validation failed"):
        registry.invoke("custom.invalid_output", {"value": "x"})



def test_registry_does_not_retain_handler_exception_context():
    registry = ToolRegistry()

    def fail_with_private_details(_payload):
        raise RuntimeError("private credential-bearing request detail")

    registry.register(
        ToolDefinition(
            name="custom.private_failure",
            description="A handler failure must be sanitized",
            input_model=InputValue,
            output_model=OutputValue,
            handler=fail_with_private_details,
        )
    )

    with pytest.raises(ToolExecutionError) as error:
        registry.invoke("custom.private_failure", {"value": "safe"})

    assert str(error.value) == "Tool handler failed"
    assert error.value.__cause__ is None
    assert error.value.__context__ is None
    assert "credential-bearing" not in repr(error.value)


def test_registry_does_not_retain_invalid_output_values_in_exception_context():
    registry = ToolRegistry()

    registry.register(
        ToolDefinition(
            name="custom.private_output",
            description="An invalid output must not be retained",
            input_model=InputValue,
            output_model=OutputValue,
            handler=lambda _payload: {"private": "credential-bearing-output"},
        )
    )

    with pytest.raises(ToolExecutionError) as error:
        registry.invoke("custom.private_output", {"value": "safe"})

    assert str(error.value) == "Tool output validation failed"
    assert error.value.__cause__ is None
    assert error.value.__context__ is None
    assert "credential-bearing-output" not in repr(error.value)



def _tool_definition(**overrides):
    values = {
        "name": "custom.contract",
        "description": "A tool definition contract test",
        "input_model": InputValue,
        "output_model": OutputValue,
        "handler": lambda payload: {"value": payload.value},
        "risk_class": RiskClass.LOW,
        "required_permissions": frozenset(),
        "external_side_effect": False,
    }
    values.update(overrides)
    return ToolDefinition(**values)


@pytest.mark.parametrize(
    ("overrides", "message"),
    [
        ({"name": None}, "Invalid tool name"),
        ({"description": None}, "Tool description"),
        ({"description": "   "}, "Tool description"),
        ({"input_model": dict}, "input_model"),
        ({"output_model": dict}, "output_model"),
        ({"handler": None}, "handler must be callable"),
        ({"risk_class": "low"}, "server-defined RiskClass"),
        ({"external_side_effect": 1}, "must be a boolean"),
        ({"replay_safety": "retry_safe"}, "server-defined ReplaySafety"),
        ({"required_permissions": {"custom.read"}}, "immutable frozenset"),
        ({"required_permissions": frozenset({"Invalid Permission"})}, "invalid permission name"),
        (
            {"required_permissions": frozenset(f"permission.{i}" for i in range(33))},
            "cannot exceed 32",
        ),
    ],
)
def test_registry_rejects_malformed_tool_definitions_without_registering(overrides, message):
    registry = ToolRegistry()
    definition = _tool_definition(**overrides)

    with pytest.raises((TypeError, ValueError), match=message):
        registry.register(definition)

    with pytest.raises(LookupError):
        registry.get("custom.contract")


def test_registry_rejects_async_handlers_before_registration():
    async def async_handler(_payload):
        return {"value": "not supported by the synchronous registry"}

    registry = ToolRegistry()
    with pytest.raises(ValueError, match="must be synchronous"):
        registry.register(_tool_definition(handler=async_handler))

    with pytest.raises(LookupError):
        registry.get("custom.contract")


def test_registry_rejects_async_generator_handlers_before_registration():
    async def async_generator_handler(_payload):
        yield {"value": "not supported by the synchronous registry"}

    registry = ToolRegistry()
    with pytest.raises(ValueError, match="must be synchronous"):
        registry.register(_tool_definition(handler=async_generator_handler))

    with pytest.raises(LookupError):
        registry.get("custom.contract")


def test_registry_rejects_non_definition_objects():
    with pytest.raises(TypeError, match="ToolDefinition"):
        ToolRegistry().register({"name": "custom.invalid"})


def test_registry_accepts_only_validated_immutable_tool_contracts():
    registry = ToolRegistry()
    registry.register(
        _tool_definition(
            required_permissions=frozenset({"cloudflare.read"}),
            external_side_effect=False,
        )
    )

    assert registry.get("custom.contract").required_permissions == frozenset({"cloudflare.read"})
    assert registry.catalog()[0]["required_permissions"] == ["cloudflare.read"]
    assert registry.get("custom.contract").replay_safety is ReplaySafety.RECONCILE_REQUIRED
    assert registry.catalog()[0]["replay_safety"] == "reconcile_required"



def test_registry_rejects_awaitable_results_from_synchronous_handlers():
    async def async_result():
        return {"value": "not supported"}

    registry = ToolRegistry()
    registry.register(
        _tool_definition(handler=lambda _payload: async_result())
    )

    with pytest.raises(ToolExecutionError, match="Tool handler failed"):
        registry.invoke("custom.contract", {"value": "safe"})

def test_registry_rejects_async_generator_results_from_synchronous_handlers():
    async def async_result():
        yield {"value": "not supported"}

    registry = ToolRegistry()
    registry.register(_tool_definition(handler=lambda _payload: async_result()))

    with pytest.raises(ToolExecutionError, match="Tool handler failed"):
        registry.invoke("custom.contract", {"value": "safe"})


def test_registry_cancels_awaitable_results_from_synchronous_handlers():
    class PendingAwaitable:
        def __init__(self):
            self.cancelled = False

        def __await__(self):
            yield

        def cancel(self):
            self.cancelled = True

    pending = PendingAwaitable()
    registry = ToolRegistry()
    registry.register(
        _tool_definition(handler=lambda _payload: pending)
    )

    with pytest.raises(ToolExecutionError, match="Tool handler failed"):
        registry.invoke("custom.contract", {"value": "safe"})

    assert pending.cancelled is True



def test_registry_exposes_explicit_retry_safe_classification():
    registry = ToolRegistry()
    registry.register(
        _tool_definition(replay_safety=ReplaySafety.RETRY_SAFE)
    )

    assert registry.catalog()[0]["replay_safety"] == "retry_safe"

def test_registry_emits_ordered_metadata_only_lifecycle_events_for_success():
    registry = ToolRegistry()
    registry.register(_tool_definition(replay_safety=ReplaySafety.RETRY_SAFE))
    events: list[ToolLifecycleEvent] = []

    result = registry.invoke(
        "custom.contract",
        {"value": "safe-input"},
        lifecycle_observer=events.append,
    )

    assert result == {"value": "safe-input"}
    assert [event.stage for event in events] == [
        ToolLifecycleStage.INPUT_VALIDATED,
        ToolLifecycleStage.AUTHORIZATION_GRANTED,
        ToolLifecycleStage.HANDLER_STARTED,
        ToolLifecycleStage.HANDLER_RETURNED,
        ToolLifecycleStage.OUTPUT_VALIDATED,
        ToolLifecycleStage.SUCCEEDED,
    ]
    assert all(event.tool_name == "custom.contract" for event in events)
    assert all(event.input_digest and len(event.input_digest) == 64 for event in events)
    assert events[-1].output_digest and len(events[-1].output_digest) == 64
    assert all(not hasattr(event, "payload") for event in events)
    assert all(not hasattr(event, "result") for event in events)


def test_registry_reports_input_rejection_without_running_handler():
    called = []
    events: list[ToolLifecycleEvent] = []
    registry = ToolRegistry()
    registry.register(
        _tool_definition(
            replay_safety=ReplaySafety.RETRY_SAFE,
            handler=lambda value: called.append(value) or {"value": "ok"},
        )
    )

    with pytest.raises(ValueError):
        registry.invoke(
            "custom.contract",
            {"unexpected": "private-sentinel"},
            lifecycle_observer=events.append,
        )

    assert called == []
    assert len(events) == 1
    assert events[0].stage is ToolLifecycleStage.INPUT_REJECTED
    assert events[0].reason_code == "input_schema_validation_failed"
    assert "private-sentinel" not in repr(events)


def test_registry_reports_policy_denial_before_handler_invocation():
    called = []
    events: list[ToolLifecycleEvent] = []
    registry = ToolRegistry()
    registry.register(
        _tool_definition(
            external_side_effect=True,
            replay_safety=ReplaySafety.RECONCILE_REQUIRED,
            handler=lambda value: called.append(value) or {"value": "unexpected"},
        )
    )

    with pytest.raises(ToolPolicyError):
        registry.invoke(
            "custom.contract",
            {"value": "safe"},
            lifecycle_observer=events.append,
        )

    assert called == []
    assert [event.stage for event in events] == [
        ToolLifecycleStage.INPUT_VALIDATED,
        ToolLifecycleStage.AUTHORIZATION_DENIED,
    ]
    assert events[-1].reason_code == "approval_required"


def test_registry_marks_non_external_stateful_handler_failure_unknown():
    events: list[ToolLifecycleEvent] = []
    registry = ToolRegistry()
    registry.register(
        _tool_definition(
            external_side_effect=False,
            replay_safety=ReplaySafety.RECONCILE_REQUIRED,
            handler=lambda _value: (_ for _ in ()).throw(
                RuntimeError("private-response-sentinel")
            ),
        )
    )

    with pytest.raises(ToolExecutionError, match="Tool handler failed"):
        registry.invoke(
            "custom.contract",
            {"value": "safe"},
            lifecycle_observer=events.append,
        )

    assert events[-1].stage is ToolLifecycleStage.UNKNOWN_OUTCOME
    assert events[-1].reason_code == "handler_failed"
    assert "private-response-sentinel" not in repr(events)


def test_registry_marks_retry_safe_handler_failure_as_failed_not_unknown():
    events: list[ToolLifecycleEvent] = []
    registry = ToolRegistry()
    registry.register(
        _tool_definition(
            external_side_effect=False,
            replay_safety=ReplaySafety.RETRY_SAFE,
            handler=lambda _value: (_ for _ in ()).throw(RuntimeError("private-failure")),
        )
    )

    with pytest.raises(ToolExecutionError):
        registry.invoke(
            "custom.contract",
            {"value": "safe"},
            lifecycle_observer=events.append,
        )

    assert events[-1].stage is ToolLifecycleStage.HANDLER_FAILED
    assert "private-failure" not in repr(events)


def test_registry_marks_reconcile_required_output_rejection_as_unknown():
    events: list[ToolLifecycleEvent] = []
    registry = ToolRegistry()
    registry.register(
        _tool_definition(
            external_side_effect=False,
            replay_safety=ReplaySafety.RECONCILE_REQUIRED,
            handler=lambda _value: {"private_output": "sentinel"},
        )
    )

    with pytest.raises(ToolExecutionError, match="Tool output validation failed"):
        registry.invoke(
            "custom.contract",
            {"value": "safe"},
            lifecycle_observer=events.append,
        )

    assert events[-1].stage is ToolLifecycleStage.UNKNOWN_OUTCOME
    assert events[-1].reason_code == "output_schema_validation_failed"
    assert "sentinel" not in repr(events)


def test_registry_observer_failure_never_changes_tool_execution():
    called = []

    def broken_observer(_event):
        raise RuntimeError("observer private failure")

    registry = ToolRegistry()
    registry.register(
        _tool_definition(
            replay_safety=ReplaySafety.RETRY_SAFE,
            handler=lambda value: called.append(value.value) or {"value": "ok"},
        )
    )

    assert registry.invoke(
        "custom.contract",
        {"value": "safe"},
        lifecycle_observer=broken_observer,
    ) == {"value": "ok"}
    assert called == ["safe"]


def test_registry_preserves_handler_policy_decision_without_exposing_reason():
    events: list[ToolLifecycleEvent] = []

    def handler(_value):
        raise ToolPolicyError(
            PolicyDecision.REQUIRE_APPROVAL,
            "private policy diagnostic",
        )

    registry = ToolRegistry()
    registry.register(
        _tool_definition(
            external_side_effect=True,
            replay_safety=ReplaySafety.RECONCILE_REQUIRED,
            handler=handler,
        )
    )

    with pytest.raises(ToolPolicyError) as error:
        registry.invoke(
            "custom.contract",
            {"value": "safe"},
            user_approved=True,
            lifecycle_observer=events.append,
        )

    assert error.value.decision is PolicyDecision.REQUIRE_APPROVAL
    assert str(error.value) == "Tool handler policy denied execution"
    assert [event.stage for event in events] == [
        ToolLifecycleStage.INPUT_VALIDATED,
        ToolLifecycleStage.AUTHORIZATION_GRANTED,
        ToolLifecycleStage.HANDLER_STARTED,
        ToolLifecycleStage.AUTHORIZATION_DENIED,
    ]
    assert events[-1].reason_code == "approval_required"
    assert "private policy diagnostic" not in repr(events)
