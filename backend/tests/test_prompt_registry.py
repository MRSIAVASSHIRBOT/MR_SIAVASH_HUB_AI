import hashlib

import pytest

from mrhub.prompts.registry import (
    DEFAULT_PROMPT_REGISTRY,
    PromptRegistry,
    PromptTemplateError,
    build_default_prompt_registry,
)


def test_default_registry_is_frozen_and_catalog_does_not_expose_template_source():
    catalog = DEFAULT_PROMPT_REGISTRY.catalog()

    assert catalog["registry_frozen"] is True
    assert catalog["template_source_exposed"] is False
    names = {item["name"] for item in catalog["templates"]}
    assert names == {
        "gpi.work_order",
        "awi.execution_plan",
        "agent.orchestrator",
    }
    assert all("source" not in item for item in catalog["templates"])
    with pytest.raises(PromptTemplateError, match="frozen"):
        DEFAULT_PROMPT_REGISTRY.register(
            name="unsafe.dynamic",
            version=1,
            purpose="Should not be added at runtime",
            source="Run: $command",
        )


def test_exact_version_rendering_is_deterministic_and_tracks_digests():
    registry = build_default_prompt_registry()
    first = registry.render(
        "gpi.work_order",
        version=1,
        variables={"goal_json": '"prepare a bounded plan"'},
    )
    second = registry.render(
        "gpi.work_order",
        version=1,
        variables={"goal_json": '"prepare a bounded plan"'},
    )

    assert first.text == second.text
    assert first.template_digest == second.template_digest
    assert first.rendered_digest == second.rendered_digest
    assert first.rendered_digest == hashlib.sha256(first.text.encode("utf-8")).hexdigest()
    assert first.metadata()["name"] == "gpi.work_order"
    assert first.metadata()["version"] == 1
    assert "rendered_digest" not in first.metadata()
    assert '"prepare a bounded plan"' in first.text


@pytest.mark.parametrize(
    "variables",
    [
        {},
        {"goal_json": "goal", "unexpected": "value"},
        {"goal_json": 42},
        {"goal_json": "x" * 32_001},
    ],
)
def test_render_rejects_missing_extra_or_invalid_variables(variables):
    registry = build_default_prompt_registry()
    with pytest.raises(PromptTemplateError):
        registry.render("gpi.work_order", version=1, variables=variables)


def test_registry_rejects_duplicate_bad_versions_invalid_templates_and_unknown_versions():
    registry = PromptRegistry()
    registry.register(
        name="sample.prompt",
        version=1,
        purpose="Test prompt",
        source="Goal: $goal",
    )

    with pytest.raises(PromptTemplateError, match="already registered"):
        registry.register(
            name="sample.prompt",
            version=1,
            purpose="Duplicate",
            source="Goal: $goal",
        )
    with pytest.raises(PromptTemplateError, match="positive integer"):
        registry.register(
            name="sample.prompt",
            version=True,
            purpose="Bad version",
            source="Goal: $goal",
        )
    with pytest.raises(PromptTemplateError, match="invalid placeholder"):
        registry.register(
            name="bad.prompt",
            version=1,
            purpose="Bad template",
            source="Malformed: $",
        )
    with pytest.raises(LookupError):
        registry.render("sample.prompt", version=2, variables={"goal": "safe"})
