"""Typed, allow-listed tool registry with server-side policy enforcement."""

from __future__ import annotations

import re
from collections.abc import Callable
from dataclasses import dataclass
from typing import TypeVar

from pydantic import BaseModel

from mrhub.domain.tasks import RiskClass
from mrhub.security.policy import ActionRequest, PolicyDecision, PolicyEngine

InputModel = TypeVar("InputModel", bound=BaseModel)
OutputModel = TypeVar("OutputModel", bound=BaseModel)


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


class ToolExecutionError(RuntimeError):
    """A registered handler failed; original exception details are not exposed."""


class ToolPolicyError(PermissionError):
    def __init__(self, decision: PolicyDecision, reason: str) -> None:
        super().__init__(reason)
        self.decision = decision


class ToolRegistry:
    """Only explicitly registered, schema-validated tools can be invoked."""

    NAME_PATTERN = re.compile(r"^[a-z][a-z0-9_.-]{0,79}$")

    def __init__(self, policy: PolicyEngine | None = None) -> None:
        self._tools: dict[str, ToolDefinition] = {}
        self._policy = policy or PolicyEngine()

    def register(self, tool: ToolDefinition) -> None:
        if not self.NAME_PATTERN.fullmatch(tool.name):
            raise ValueError("Invalid tool name")
        if not tool.description.strip() or len(tool.description) > 200:
            raise ValueError("Tool description must contain 1 to 200 characters")
        if tool.name in self._tools:
            raise ValueError("Tool is already registered")
        self._tools[tool.name] = tool

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
        decision = self._policy.evaluate(
            ActionRequest(
                action=f"tool.invoke:{name}",
                risk_class=tool.risk_class,
                granted_permissions=granted_permissions,
                required_permissions=tool.required_permissions,
                external_side_effect=tool.external_side_effect,
                user_approved=user_approved,
            )
        )
        if decision.decision is not PolicyDecision.ALLOW:
            raise ToolPolicyError(decision.decision, decision.reason)

        try:
            raw_result = tool.handler(validated_input)
        except Exception as exc:
            raise ToolExecutionError("Tool handler failed") from exc
        validated_output = tool.output_model.model_validate(raw_result)
        return validated_output.model_dump(mode="json")
