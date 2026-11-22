"""Tests for GPI work-order generation and AWI plan validation."""

import json

import pytest

from mrhub.agents.awi_planner import ExecutionPlan, PlanningError, generate_execution_plan
from mrhub.agents.gpi import (
    WorkOrderGenerationError,
    derive_server_risk_class,
    generate_work_order,
)
from mrhub.domain.tasks import RiskClass
from mrhub.providers.base import ProviderHealth, ProviderResponse
from mrhub.providers.router import ModelCapability, ModelDescriptor, ModelRouter


class QueueProvider:
    def __init__(self, outputs: list[str]) -> None:
        self.outputs = list(outputs)
        self.descriptor = ModelDescriptor(
            provider="test", model="queue-v1",
            capability=ModelCapability(text=True), available=True,
            local=True, priority=1,
        )
        self.calls = 0

    def generate(self, request):
        self.calls += 1
        return ProviderResponse(
            provider="test", model="queue-v1",
            output_text=self.outputs.pop(0),
        )

    def health(self, timeout_seconds: float = 2.0):
        return ProviderHealth(available=True, reason_code="test_ready")


def router_for(*outputs: str) -> tuple[ModelRouter, QueueProvider]:
    router = ModelRouter()
    provider = QueueProvider(list(outputs))
    router.register_provider(provider)
    return router, provider


def valid_work_order_payload(**overrides):
    payload = {
        "intent": "Create a tested implementation plan",
        "scope": "Backend-only, no external actions",
        "assumptions": [],
        "constraints": ["Planning only"],
        "dependencies": [],
        "required_capabilities": ["text.echo"],
        "acceptance_criteria": ["The plan is validated"],
        "verification_steps": ["Run focused tests"],
    }
    payload.update(overrides)
    return payload


def test_gpi_generation_uses_original_goal_and_server_risk():
    router, _ = router_for(json.dumps(valid_work_order_payload(goal="model altered this")))
    work_order = generate_work_order("  Build a safe plan  ", router)
    assert work_order.goal == "Build a safe plan"
    assert work_order.risk_class is RiskClass.LOW


def test_gpi_does_not_trust_model_risk_class():
    payload = valid_work_order_payload(risk_class="low")
    router, _ = router_for(json.dumps(payload))
    work_order = generate_work_order("Deploy this to production", router)
    assert work_order.risk_class is RiskClass.HIGH


def test_gpi_rejects_non_json_and_invalid_schema():
    router, _ = router_for("not-json")
    with pytest.raises(WorkOrderGenerationError):
        generate_work_order("Make a plan", router)
    router, _ = router_for(json.dumps({"intent": "missing required fields"}))
    with pytest.raises(WorkOrderGenerationError):
        generate_work_order("Make a plan", router)


def test_gpi_rejects_blank_goal_without_provider_call():
    router, provider = router_for("{}")
    with pytest.raises(WorkOrderGenerationError):
        generate_work_order("   ", router)
    assert provider.calls == 0


def test_risk_classifier_is_conservative_for_external_changes():
    assert derive_server_risk_class("Send email to the customer", {}) is RiskClass.HIGH
    assert derive_server_risk_class("Review personal data handling", {}) is RiskClass.MODERATE


def test_execution_plan_rejects_cycles_and_unknown_dependencies():
    with pytest.raises(ValueError):
        ExecutionPlan.model_validate({
            "rationale": "cycle",
            "steps": [
                {"step_id": "a", "description": "A", "depends_on": ["b"],
                 "verifies_criteria": ["x"], "verification": "check"},
                {"step_id": "b", "description": "B", "depends_on": ["a"],
                 "verifies_criteria": ["x"], "verification": "check"},
            ],
        })
    with pytest.raises(ValueError):
        ExecutionPlan.model_validate({
            "rationale": "unknown",
            "steps": [{"step_id": "a", "description": "A", "depends_on": ["missing"],
                       "verifies_criteria": ["x"], "verification": "check"}],
        })


def test_awi_plan_requires_complete_criteria_and_capability_coverage():
    work_order_payload = valid_work_order_payload()
    router, _ = router_for(json.dumps({
        "rationale": "One bounded step",
        "steps": [{
            "step_id": "validate",
            "description": "Validate the result",
            "depends_on": [],
            "required_capabilities": ["text.echo"],
            "verifies_criteria": ["The plan is validated"],
            "verification": "Run focused tests and inspect results",
        }],
    }))
    work_order_router, _ = router_for(json.dumps(work_order_payload))
    work_order = generate_work_order("Build a tested implementation plan", work_order_router)
    plan = generate_execution_plan(work_order, router)
    assert len(plan.steps) == 1
    assert plan.steps[0].required_capabilities == ["text.echo"]


def test_awi_plan_rejects_missing_acceptance_criterion():
    router, _ = router_for(json.dumps({
        "rationale": "Incomplete",
        "steps": [{
            "step_id": "validate", "description": "Validate",
            "depends_on": [], "required_capabilities": ["text.echo"],
            "verifies_criteria": [], "verification": "Check",
        }],
    }))
    work_order_router, _ = router_for(json.dumps(valid_work_order_payload()))
    work_order = generate_work_order("Build a plan", work_order_router)
    with pytest.raises(PlanningError):
        generate_execution_plan(work_order, router)
