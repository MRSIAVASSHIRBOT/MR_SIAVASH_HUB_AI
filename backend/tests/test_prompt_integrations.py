import json

from mrhub.agents.awi_planner import generate_execution_plan
from mrhub.agents.gpi import generate_work_order
from mrhub.prompts.registry import DEFAULT_PROMPT_REGISTRY
from mrhub.providers.base import ProviderHealth, ProviderResponse
from mrhub.providers.router import ModelCapability, ModelDescriptor, ModelRouter


class QueueProvider:
    descriptor = ModelDescriptor(
        provider="prompt-test",
        model="prompt-fixture",
        capability=ModelCapability(text=True),
        available=True,
        local=True,
        priority=1,
    )

    def __init__(self, output: str) -> None:
        self.output = output
        self.requests = []

    def generate(self, request):
        self.requests.append(request)
        return ProviderResponse(
            provider=self.descriptor.provider,
            model=self.descriptor.model,
            output_text=self.output,
        )

    def health(self, timeout_seconds: float = 2.0):
        return ProviderHealth(available=True, reason_code="test_ready")


def _router(output: str):
    router = ModelRouter()
    provider = QueueProvider(output)
    router.register_provider(provider)
    return router, provider


def _work_order_payload():
    return {
        "intent": "Prepare a versioned prompt test",
        "scope": "GPI/AWI planning only",
        "assumptions": [],
        "constraints": ["Do not execute tools"],
        "dependencies": [],
        "required_capabilities": ["text.echo"],
        "acceptance_criteria": ["The prompt version is tracked"],
        "verification_steps": ["Inspect prompt provenance"],
    }


def test_gpi_uses_exact_registered_template_and_emits_safe_provenance():
    router, provider = _router(json.dumps(_work_order_payload()))
    observed = []

    work_order = generate_work_order(
        "Prepare a versioned prompt test",
        router,
        prompt_observer=observed.append,
    )

    assert work_order.goal == "Prepare a versioned prompt test"
    assert len(provider.requests) == 1
    assert len(observed) == 1
    assert observed[0].name == "gpi.work_order"
    assert observed[0].version == 1
    assert observed[0].template_digest == DEFAULT_PROMPT_REGISTRY.resolve(
        "gpi.work_order", 1
    ).digest
    assert "USER GOAL JSON STRING" in provider.requests[0].input_text
    assert "rendered_digest" not in observed[0].metadata()


def test_awi_uses_exact_registered_template_and_emits_safe_provenance():
    gpi_router, _ = _router(json.dumps(_work_order_payload()))
    work_order = generate_work_order(
        "Prepare a versioned prompt test",
        gpi_router,
    )
    awi_payload = {
        "rationale": "One bounded step covers the declared criterion.",
        "steps": [
            {
                "step_id": "verify-prompt",
                "description": "Verify prompt provenance",
                "depends_on": [],
                "required_capabilities": ["text.echo"],
                "verifies_criteria": ["The prompt version is tracked"],
                "verification": "Check registered template name and version",
            }
        ],
    }
    awi_router, provider = _router(json.dumps(awi_payload))
    observed = []

    plan = generate_execution_plan(
        work_order,
        awi_router,
        prompt_observer=observed.append,
    )

    assert plan.steps[0].step_id == "verify-prompt"
    assert len(provider.requests) == 1
    assert len(observed) == 1
    assert observed[0].name == "awi.execution_plan"
    assert observed[0].version == 1
    assert "WORK ORDER JSON" in provider.requests[0].input_text
    assert observed[0].metadata()["template_digest"] == DEFAULT_PROMPT_REGISTRY.resolve(
        "awi.execution_plan", 1
    ).digest
