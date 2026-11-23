import pytest
from pydantic import ValidationError

from mrhub.domain.tasks import RiskClass
from mrhub.security.policy import ActionRequest, PolicyDecision, PolicyEngine


def test_action_request_is_immutable_and_rejects_unknown_fields():
    request = ActionRequest(
        action="tool.read",
        risk_class=RiskClass.LOW,
        granted_permissions=frozenset({"cloudflare.read"}),
        required_permissions=frozenset({"cloudflare.read"}),
    )

    with pytest.raises(ValidationError):
        request.user_approved = True

    with pytest.raises(ValidationError):
        ActionRequest(
            action="tool.read",
            risk_class=RiskClass.LOW,
            unexpected="not accepted",
        )


@pytest.mark.parametrize(
    "permissions",
    [
        {"Invalid Permission"},
        {"x" * 81},
    ],
)
def test_action_request_rejects_invalid_permission_names(permissions):
    # The internal policy contract accepts only canonical, immutable permission names.
    with pytest.raises(ValidationError):
        ActionRequest(
            action="tool.read",
            risk_class=RiskClass.LOW,
            granted_permissions=frozenset(permissions),
        )


@pytest.mark.parametrize("value", ["false", 0, 1, None])
def test_action_request_rejects_coerced_side_effect_flags(value):
    with pytest.raises(ValidationError):
        ActionRequest(
            action="tool.read",
            risk_class=RiskClass.LOW,
            external_side_effect=value,
        )


def test_policy_engine_requires_server_permission_snapshot_and_approval():
    engine = PolicyEngine()
    request = ActionRequest(
        action="cloudflare.inventory",
        risk_class=RiskClass.HIGH,
        granted_permissions=frozenset({"cloudflare.read"}),
        required_permissions=frozenset({"cloudflare.read"}),
        external_side_effect=True,
        user_approved=False,
    )

    result = engine.evaluate(request)

    assert result.decision is PolicyDecision.REQUIRE_APPROVAL
