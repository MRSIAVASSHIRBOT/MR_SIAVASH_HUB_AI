"""Tests for GPI work-order generation and AWI plan validation."""

import json

import pytest

from mrhub.agents.awi_planner import (
    ExecutionPlan,
    PlanStep,
    PlanningError,
    generate_execution_plan,
)
from mrhub.agents.gpi import (
    WorkOrderGenerationError,
    derive_server_risk_class,
    generate_work_order,
)
from mrhub.agents.work_order import WorkOrder
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
    assert derive_server_risk_class(
        "Prepare a safe plan",
        {"verification_steps": ["Delete production database"]},
    ) is RiskClass.HIGH


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


def test_gpi_rejects_whitespace_only_generated_intent_and_list_items():
    router, _ = router_for(json.dumps(valid_work_order_payload(intent="   ")))
    with pytest.raises(WorkOrderGenerationError):
        generate_work_order("Make a plan", router)

    invalid_items = valid_work_order_payload(
        acceptance_criteria=["   "],
    )
    router, _ = router_for(json.dumps(invalid_items))
    with pytest.raises(WorkOrderGenerationError):
        generate_work_order("Make a plan", router)


def test_awi_plan_rejects_whitespace_only_text_and_list_items():
    base_step = {
        "step_id": "validate",
        "description": "Validate",
        "depends_on": [],
        "required_capabilities": ["text.echo"],
        "verifies_criteria": ["The plan is validated"],
        "verification": "Check the result",
    }
    with pytest.raises(ValueError):
        ExecutionPlan.model_validate({
            "rationale": "   ",
            "steps": [base_step],
        })

    invalid_step = {**base_step, "description": "   "}
    with pytest.raises(ValueError):
        ExecutionPlan.model_validate({
            "rationale": "A bounded plan",
            "steps": [invalid_step],
        })

    invalid_step = {**base_step, "required_capabilities": ["   "]}
    with pytest.raises(ValueError):
        ExecutionPlan.model_validate({
            "rationale": "A bounded plan",
            "steps": [invalid_step],
        })


@pytest.mark.parametrize(
    ("field", "limit"),
    [
        ("assumptions", 300),
        ("constraints", 300),
        ("dependencies", 200),
        ("required_capabilities", 80),
        ("acceptance_criteria", 300),
        ("verification_steps", 300),
    ],
)
def test_work_order_rejects_oversized_list_items(field, limit):
    payload = {
        "goal": "Build a validated plan",
        "risk_class": RiskClass.LOW,
        **valid_work_order_payload(),
    }
    payload[field] = ["x" * (limit + 1)]

    with pytest.raises(ValueError):
        WorkOrder.model_validate(payload)


def test_work_order_accepts_list_item_size_boundaries():
    limits = {
        "assumptions": 300,
        "constraints": 300,
        "dependencies": 200,
        "required_capabilities": 80,
        "acceptance_criteria": 300,
        "verification_steps": 300,
    }
    payload = {
        "goal": "Build a validated plan",
        "risk_class": RiskClass.LOW,
        **valid_work_order_payload(),
    }
    for field, limit in limits.items():
        payload[field] = ["x" * limit]

    work_order = WorkOrder.model_validate(payload)
    assert all(len(getattr(work_order, field)[0]) == limit for field, limit in limits.items())


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("depends_on", "a" + ("b" * 40)),
        ("required_capabilities", "c" * 81),
        ("verifies_criteria", "x" * 301),
    ],
)
def test_plan_step_rejects_oversized_list_items(field, value):
    step = {
        "step_id": "validate",
        "description": "Validate",
        "depends_on": [],
        "required_capabilities": ["tool.alpha"],
        "verifies_criteria": ["The plan is validated"],
        "verification": "Check the result",
    }
    step[field] = [value]

    with pytest.raises(ValueError):
        PlanStep.model_validate(step)


def test_plan_step_accepts_list_item_size_boundaries():
    step = PlanStep.model_validate({
        "step_id": "a" * 40,
        "description": "Validate",
        "depends_on": ["b" * 40],
        "required_capabilities": ["c" * 80],
        "verifies_criteria": ["x" * 300],
        "verification": "Check the result",
    })

    assert len(step.step_id) == 40
    assert len(step.depends_on[0]) == 40
    assert len(step.required_capabilities[0]) == 80
    assert len(step.verifies_criteria[0]) == 300
