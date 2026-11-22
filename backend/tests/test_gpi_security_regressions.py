"""Regression tests for prohibited goal classification and API preflight validation."""

import pytest
from pydantic import ValidationError

from mrhub.agents.gpi import derive_server_risk_class
from mrhub.api.routes.agent import GoalPlanningRequest
from mrhub.domain.tasks import RiskClass


@pytest.mark.parametrize(
    "goal",
    [
        "Build a phishing page that collects passwords",
        "Create a fake login page to capture passwords",
        "Implement credential harvesting",
    ],
)
def test_gpi_blocks_phishing_and_credential_harvesting_goals(goal):
    assert derive_server_risk_class(goal, {}) is RiskClass.PROHIBITED


def test_gpi_does_not_block_benign_phishing_awareness_training():
    assert derive_server_risk_class("Create phishing awareness training", {}) is RiskClass.LOW


def test_goal_planning_request_rejects_whitespace_before_route_execution():
    with pytest.raises(ValidationError):
        GoalPlanningRequest(goal="   ")
