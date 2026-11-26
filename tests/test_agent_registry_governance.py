import json

import pytest

from mrhub.agents.registry import AgentProfile, AgentRegistry, build_default_agent_registry
from mrhub.tools.builtins import build_tool_registry
from mrhub.tools.registry import ToolRegistry


def _profile(
    *, version: int = 1, instructions: str = "Private reviewed instructions"
) -> AgentProfile:
    return AgentProfile(
        name="test_specialist",
        description="A bounded test specialist.",
        instructions=instructions,
        allowed_tools=frozenset(),
        max_turns=2,
        version=version,
    )


def test_registry_freeze_prevents_further_registration_and_mapping_mutation():
    registry = AgentRegistry()
    profile = _profile()
    registry.register(profile)

    assert registry.freeze() is registry
    assert registry.frozen is True
    with pytest.raises(RuntimeError, match="frozen"):
        registry.register(_profile(version=2))
    with pytest.raises(TypeError):
        registry._agents["injected"] = profile


def test_registry_manifest_is_metadata_only_and_has_stable_profile_digest():
    first = build_default_agent_registry(build_tool_registry())
    second = build_default_agent_registry(build_tool_registry())

    manifest = first.manifest()
    assert manifest["schema_version"] == "agent_registry_manifest.v1"
    assert manifest["registry_frozen"] is True
    assert manifest["registry_mutable"] is False
    assert manifest["runtime_registration_enabled"] is False
    assert manifest["execution_authorized"] is False
    assert manifest["instructions_exposed"] is False
    assert manifest["agent_count"] == 6
    assert [item["name"] for item in manifest["agents"]] == sorted(
        item["name"] for item in manifest["agents"]
    )
    assert {
        item["name"]: item["profile_digest"] for item in manifest["agents"]
    } == {
        item["name"]: item["profile_digest"] for item in second.manifest()["agents"]
    }
    assert all(len(item["profile_digest"]) == 64 for item in manifest["agents"])
    encoded = json.dumps(manifest, ensure_ascii=False)
    assert "Private reviewed instructions" not in encoded
    assert '"instructions"' not in encoded


def test_profile_digest_changes_when_reviewed_instruction_changes():
    original = AgentRegistry()
    revised = AgentRegistry()
    original.register(_profile(instructions="Version one reviewed instruction"))
    revised.register(_profile(instructions="Version two reviewed instruction"))
    original.freeze()
    revised.freeze()

    original_digest = original.manifest()["agents"][0]["profile_digest"]
    revised_digest = revised.manifest()["agents"][0]["profile_digest"]
    assert original_digest != revised_digest


@pytest.mark.parametrize("version", [0, -1, True])
def test_registry_rejects_invalid_profile_versions(version):
    registry = AgentRegistry()
    with pytest.raises(ValueError, match="version"):
        registry.register(_profile(version=version))


def test_registry_requires_immutable_tool_scope():
    registry = AgentRegistry()
    profile = AgentProfile(
        name="mutable_scope",
        description="Reject mutable tool grants.",
        instructions="Do not allow mutable tool grants.",
        allowed_tools={"text.echo"},
    )
    with pytest.raises(ValueError, match="immutable"):
        registry.register(profile)



def test_registry_metadata_composition_does_not_require_optional_integrations():
    registry = build_default_agent_registry()

    assert registry.frozen is True
    with pytest.raises(LookupError, match="Tool is not registered"):
        registry.scoped_tools("text_helper", ToolRegistry())
