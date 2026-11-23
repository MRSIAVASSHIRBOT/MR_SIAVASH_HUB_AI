"""Typed, allow-listed tool registry with server-side policy enforcement."""

from __future__ import annotations

import inspect
import re
from collections.abc import Callable
from dataclasses import dataclass
from enum import StrEnum
from typing import TypeVar

from pydantic import BaseModel, ValidationError

from mrhub.domain.tasks import RiskClass
from mrhub.security.policy import ActionRequest, PolicyDecision, PolicyEngine, PolicyResult

InputModel = TypeVar("InputModel", bound=BaseModel)
OutputModel = TypeVar("OutputModel", bound=BaseModel)


class ReplaySafety(StrEnum):
    """Server-owned classification for retrying an interrupted tool invocation."""

    RETRY_SAFE = "retry_safe"
    RECONCILE_REQUIRED = "reconcile_required"


_PERMISSION_PATTERN = re.compile(r"^[a-z][a-z0-9_.:-]{0,79}$")


@dataclass(frozen=True)
class ToolDefinition:
    name: str
    description: str
    input_model: type[BaseModel]
    output_model: type[BaseModel]
    handler: Callable[[BaseModel], BaseModel | dict[str, object]]
    risk_class: RiskClass = RiskClass.LOW
    required_permissions: frozenset[str] = frozenset()
    external_side_effect: bool = False
    replay_safety: ReplaySafety = ReplaySafety.RECONCILE_REQUIRED


class ToolExecutionError(RuntimeError):
    """A registered handler failed; original exception details are not exposed."""


class ToolPolicyError(PermissionError):
    def __init__(self, decision: PolicyDecision, reason: str) -> None:
        super().__init__(reason)
        self.decision = decision


class ToolRegistry:
    """Only explicitly registered, schema-validated tools can be invoked."""

    NAME_PATTERN = re.compile(r"^[a-z][a-z0-9_.-]{0,79}$")
    MAX_REQUIRED_PERMISSIONS = 32

    def __init__(self, policy: PolicyEngine | None = None) -> None:
        self._tools: dict[str, ToolDefinition] = {}
        self._policy = policy if policy is not None else PolicyEngine()

    @staticmethod
    def _validate_schema_model(model: object, field_name: str) -> None:
        if not isinstance(model, type) or not issubclass(model, BaseModel):
            raise TypeError(f"{field_name} must be a Pydantic BaseModel subclass")

    @classmethod
    def _validate_definition(cls, tool: ToolDefinition) -> None:
        if not isinstance(tool.name, str) or not cls.NAME_PATTERN.fullmatch(tool.name):
            raise ValueError("Invalid tool name")
        if (
            not isinstance(tool.description, str)
            or not tool.description.strip()
            or len(tool.description) > 200
        ):
            raise ValueError("Tool description must contain 1 to 200 characters")

        cls._validate_schema_model(tool.input_model, "input_model")
        cls._validate_schema_model(tool.output_model, "output_model")

        if not callable(tool.handler):
            raise TypeError("Tool handler must be callable")
        handler_call = type(tool.handler).__call__
        if (
            inspect.iscoroutinefunction(tool.handler)
            or inspect.iscoroutinefunction(handler_call)
            or inspect.isasyncgenfunction(tool.handler)
            or inspect.isasyncgenfunction(handler_call)
        ):
            raise ValueError("Tool handlers must be synchronous")

        if not isinstance(tool.risk_class, RiskClass):
            raise TypeError("Tool risk_class must be a server-defined RiskClass")
        if type(tool.external_side_effect) is not bool:
            raise ValueError("Tool external_side_effect must be a boolean")

        if not isinstance(tool.replay_safety, ReplaySafety):
            raise TypeError("Tool replay_safety must be a server-defined ReplaySafety value")

        if not isinstance(tool.required_permissions, frozenset):
            raise TypeError("Tool required_permissions must be an immutable frozenset")
        if len(tool.required_permissions) > cls.MAX_REQUIRED_PERMISSIONS:
            raise ValueError(
                f"Tool required_permissions cannot exceed {cls.MAX_REQUIRED_PERMISSIONS} entries"
            )
        if any(
            not isinstance(permission, str)
            or _PERMISSION_PATTERN.fullmatch(permission) is None
            for permission in tool.required_permissions
        ):
            raise ValueError("Tool required_permissions contain an invalid permission name")

    def register(self, tool: ToolDefinition) -> None:
        if not isinstance(tool, ToolDefinition):
            raise TypeError("Only ToolDefinition instances can be registered")
        self._validate_definition(tool)
        if tool.name in self._tools:
            raise ValueError("Tool is already registered")
        # Register only after every contract check succeeds.
        self._tools[tool.name] = tool

    @property
    def policy(self) -> PolicyEngine:
        """Return the policy engine used for every registry decision."""
        return self._policy

    def evaluate_policy(
        self,
        name: str,
        *,
        granted_permissions: frozenset[str] = frozenset(),
        user_approved: bool = False,
    ) -> PolicyResult:
        """Evaluate the registered tool using this registry's policy authority."""
        tool = self.get(name)
        return self._policy.evaluate(
            ActionRequest(
                action=f"tool.invoke:{name}",
                risk_class=tool.risk_class,
                granted_permissions=granted_permissions,
                required_permissions=tool.required_permissions,
                external_side_effect=tool.external_side_effect,
                user_approved=user_approved,
            )
        )

    def get(self, name: str) -> ToolDefinition:
        try:
            return self._tools[name]
        except KeyError as exc:
            raise LookupError("Tool is not registered") from exc

    def scoped(self, allowed_names: frozenset[str] | set[str]) -> ToolRegistry:
        """Return a registry restricted to reviewed names while preserving policy."""
        scoped_registry = ToolRegistry(self._policy)
        for name in sorted(allowed_names):
            scoped_registry.register(self.get(name))
        return scoped_registry

    def catalog(self) -> list[dict[str, object]]:
        return [
            {
                "name": tool.name,
                "description": tool.description,
                "risk_class": tool.risk_class.value,
                "required_permissions": sorted(tool.required_permissions),
                "external_side_effect": tool.external_side_effect,
                "replay_safety": tool.replay_safety.value,
                "input_schema": tool.input_model.model_json_schema(),
                "output_schema": tool.output_model.model_json_schema(),
            }
            for tool in sorted(self._tools.values(), key=lambda item: item.name)
        ]

    def invoke(
        self,
        name: str,
        payload: dict[str, object],
        *,
        granted_permissions: frozenset[str] = frozenset(),
        user_approved: bool = False,
    ) -> dict[str, object]:
        tool = self.get(name)
        validated_input = tool.input_model.model_validate(payload)
        decision = self.evaluate_policy(
            name,
            granted_permissions=granted_permissions,
            user_approved=user_approved,
        )
        if decision.decision is not PolicyDecision.ALLOW:
            raise ToolPolicyError(decision.decision, decision.reason)

        handler_failed = False
        try:
            raw_result = tool.handler(validated_input)
            if inspect.isawaitable(raw_result) or inspect.isasyncgen(raw_result):
                # The synchronous registry cannot safely drive asynchronous work.
                # Cancel scheduled awaitables and close un-awaited coroutines.
                cancel = getattr(raw_result, "cancel", None)
                if callable(cancel):
                    cancel()
                close = getattr(raw_result, "close", None)
                if callable(close):
                    close()
                handler_failed = True
        except ToolPolicyError:
            # Domain-specific authorization checks (e.g. a device's exact granted
            # scope) retain the normal policy-denied response and audit path.
            raise
        except Exception:  # noqa: BLE001 - sanitize arbitrary untrusted tool failures
            # Leave the exception handler before raising so the original error
            # (which may retain credentials or private request data) is not kept
            # as this public boundary's __context__ or __cause__.
            handler_failed = True
        if handler_failed:
            raise ToolExecutionError("Tool handler failed")

        output_invalid = False
        try:
            validated_output = tool.output_model.model_validate(raw_result)
        except ValidationError:
            # ValidationError can include the rejected output value. Do not retain it.
            output_invalid = True
        if output_invalid:
            raise ToolExecutionError("Tool output validation failed")
        return validated_output.model_dump(mode="json")
