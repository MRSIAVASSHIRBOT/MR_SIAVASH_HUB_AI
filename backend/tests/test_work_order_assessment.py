import pytest
from mrhub.agents.work_order import (
    WorkOrder,
    assess_work_order_capabilities,
)
from mrhub.domain.tasks import RiskClass
from mrhub.security.audit import AuditLogger


def make_work_order(required_capabilities: list[str]) -> WorkOrder:
    return WorkOrder(
        goal="Prepare a bounded plan",
        intent="Check capability coverage before planning",
        acceptance_criteria=["Missing capabilities are reported"],
        verification_steps=["Run the work-order tests"],
        required_capabilities=required_capabilities,
        risk_class=RiskClass.LOW,
    )


def test_assessment_matches_registered_tool_names_case_insensitively():
    report = assess_work_order_capabilities(
        make_work_order(["browser.search", "filesystem.read", "BROWSER.SEARCH"]),
        [
            {"name": "browser.search", "description": "Search the web"},
            {"name": "system.clock", "description": "Read clock"},
        ],
    )

    assert report.required == ("browser.search", "filesystem.read")
    assert report.available == ("browser.search",)
    assert report.missing == ("filesystem.read",)
    assert report.complete is False


def test_descriptions_do_not_satisfy_capability_requirements():
    report = assess_work_order_capabilities(
        make_work_order(["network.lookup"]),
        [{"name": "web.search", "description": "Provides network lookup"}],
    )

    assert report.available == ()
    assert report.missing == ("network.lookup",)


def test_empty_capability_requirements_are_complete_but_not_authorized():
    report = assess_work_order_capabilities(make_work_order([]), [])

    assert report.complete is True
    assert report.required == ()
    assert report.available == ()
    assert report.missing == ()


@pytest.mark.parametrize(
    ("catalog", "error"),
    [
        ([None], TypeError),
        ([{"description": "missing name"}], TypeError),
        ([{"name": ""}], ValueError),
        ([{"name": "x" * 81}], ValueError),
    ],
)
def test_assessment_rejects_malformed_tool_catalog(catalog, error):
    with pytest.raises(error):
        assess_work_order_capabilities(make_work_order(["tool.read"]), catalog)


def test_assessment_bounds_registered_tool_catalog_size():
    catalog = [{"name": f"tool.{index}"} for index in range(201)]

    with pytest.raises(ValueError, match="supported limit"):
        assess_work_order_capabilities(make_work_order(["tool.read"]), catalog)


def test_work_order_declared_risk_does_not_change_capability_assessment():
    order = make_work_order(["browser.search"]).model_copy(
        update={"risk_class": RiskClass.HIGH}
    )

    report = assess_work_order_capabilities(
        order,
        [{"name": "browser.search"}],
    )

    assert report.complete is True
    assert order.risk_class is RiskClass.HIGH



def test_audit_allowlists_only_bounded_work_order_assessment_metadata():
    event = AuditLogger(None).build_event(
        event_type="agent.work_order_assessed",
        outcome="capability_gaps",
        metadata={
            "required_capability_count": 2,
            "available_capability_count": 1,
            "missing_capability_count": 1,
            "declared_risk_class": "moderate",
            "declared_risk_is_authoritative": False,
            "goal": "must not be retained",
        },
    )

    assert event.metadata == {
        "required_capability_count": 2,
        "available_capability_count": 1,
        "missing_capability_count": 1,
        "declared_risk_class": "moderate",
        "declared_risk_is_authoritative": False,
    }
