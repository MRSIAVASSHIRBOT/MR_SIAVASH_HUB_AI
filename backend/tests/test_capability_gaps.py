import pytest

from mrhub.agents.capability_gaps import evaluate_capability_gaps


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


@pytest.mark.parametrize("required", [[" "], [None], ["x" * 81]])
def test_invalid_requirement_names_are_rejected(required):
    with pytest.raises(ValueError):
        evaluate_capability_gaps(required, [])


def test_invalid_catalog_entries_are_rejected():
    with pytest.raises(ValueError):
        evaluate_capability_gaps(["tool"], [{"description": "missing name"}])


def test_too_many_requirements_are_bounded():
    with pytest.raises(ValueError, match="Too many"):
        evaluate_capability_gaps([f"tool.{i}" for i in range(51)], [])
