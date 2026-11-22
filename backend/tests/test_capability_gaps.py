import pytest
from pydantic import BaseModel

from mrhub.agents.capability_gaps import (
    evaluate_capability_gaps,
    evaluate_registered_tool_gaps,
)
from mrhub.tools.registry import ToolDefinition, ToolRegistry


def test_capability_gaps_uses_exact_registered_names():
    report = evaluate_capability_gaps(
        ["browser.search", "filesystem.read", "Browser.Search"],
        [{"name": "browser.search", "description": "search the web"}],
    )
    assert report.required == ("browser.search", "filesystem.read")
    assert report.available == ("browser.search",)
    assert report.missing == ("filesystem.read",)
    assert report.complete is False


def test_descriptions_do_not_satisfy_required_capabilities():
    report = evaluate_capability_gaps(
        ["network.lookup"],
        [{"name": "web_search", "description": "network lookup capability"}],
    )
    assert report.available == ()
    assert report.missing == ("network.lookup",)


def test_report_is_complete_when_all_requirements_are_registered():
    report = evaluate_capability_gaps(
        ["tool.one", "TOOL.TWO"],
        [{"name": "tool.one"}, {"name": "tool.two"}],
    )
    assert report.complete is True
    assert report.missing == ()


@pytest.mark.parametrize(
    ("required", "error"),
    [([" "], ValueError), ([None], TypeError), (["x" * 81], ValueError)],
)
def test_invalid_requirement_names_are_rejected(required, error):
    with pytest.raises(error):
        evaluate_capability_gaps(required, [])


def test_invalid_catalog_entries_are_rejected():
    with pytest.raises(TypeError):
        evaluate_capability_gaps(["tool"], [{"description": "missing name"}])


def test_too_many_requirements_are_bounded():
    with pytest.raises(ValueError, match="Too many"):
        evaluate_capability_gaps([f"tool.{i}" for i in range(51)], [])


def test_duplicate_requirement_stream_is_bounded():
    with pytest.raises(ValueError, match="Too many"):
        evaluate_capability_gaps(["tool.read"] * 51, [])


def test_tool_catalog_size_is_bounded():
    catalog = [{"name": f"tool.{index}"} for index in range(201)]
    with pytest.raises(ValueError, match="Tool catalog exceeds"):
        evaluate_capability_gaps(["tool.read"], catalog)


def test_registered_tool_gaps_reads_live_registry_without_invoking_tools():
    class EmptyModel(BaseModel):
        pass

    invoked = []
    registry = ToolRegistry()
    registry.register(
        ToolDefinition(
            name="browser.search",
            description="Search the web",
            input_model=EmptyModel,
            output_model=EmptyModel,
            handler=lambda _payload: invoked.append(True) or {},
        )
    )
    registry.register(
        ToolDefinition(
            name="system.clock",
            description="Read the local clock",
            input_model=EmptyModel,
            output_model=EmptyModel,
            handler=lambda _payload: {},
        )
    )

    report = evaluate_registered_tool_gaps(
        ["browser.search", "filesystem.read", "BROWSER.SEARCH"],
        registry,
    )

    assert report.required == ("browser.search", "filesystem.read")
    assert report.available == ("browser.search",)
    assert report.missing == ("filesystem.read",)
    assert invoked == []


@pytest.mark.parametrize(
    "required",
    ["tool.read", b"tool.read", bytearray(b"tool.read"), {"tool.read": True}],
)
def test_required_capabilities_reject_scalar_and_mapping_inputs(required):
    with pytest.raises(TypeError, match="required_capabilities must be an iterable"):
        evaluate_capability_gaps(required, [])


@pytest.mark.parametrize(
    "catalog",
    ["tool.read", b"tool.read", bytearray(b"tool.read"), {"name": "tool.read"}],
)
def test_tool_catalog_rejects_scalar_and_mapping_inputs(catalog):
    with pytest.raises(TypeError, match="tool_catalog must be an iterable"):
        evaluate_capability_gaps(["tool.read"], catalog)
