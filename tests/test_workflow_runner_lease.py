import sqlite3
from threading import Event

import pytest
from pydantic import BaseModel

from mrhub.agents.core import AgentCore, AgentPlanRequest
from mrhub.agents.workflow_runner import AgentWorkflowRunner
from mrhub.domain.tasks import RiskClass
from mrhub.infrastructure.database import TaskRepository
from mrhub.jobs.leases import LeaseError, WorkerLease
from mrhub.providers.router import ModelRouter
from mrhub.providers.stub import StubProvider
from mrhub.tools.registry import ToolDefinition, ToolRegistry


@pytest.mark.parametrize(
    "heartbeat_error",
    [
        sqlite3.OperationalError("database is locked"),
        LeaseError("lease clock is invalid"),
    ],
)
def test_local_workflow_runner_fails_closed_when_heartbeat_raises(
    tmp_path, monkeypatch, heartbeat_error
):
    repository = TaskRepository(tmp_path / "workflow-runner.sqlite3")
    repository.initialize()
    runner = AgentWorkflowRunner(repository, core=None, lease_seconds=1)
    lease = WorkerLease(
        task_id="task-1",
        owner="worker-1",
        fencing_token=1,
        expires_at="2026-11-03T00:01:00+00:00",
    )
    lease_lost = Event()

    class FailingLeaseManager:
        def heartbeat(self, _lease):
            raise heartbeat_error

    monkeypatch.setattr(runner, "lease_manager", FailingLeaseManager())
    runner._heartbeat_loop(lease, Event(), lease_lost)

    assert lease_lost.is_set()



def test_durable_step_metadata_tracks_topological_order_and_external_tool_identity():
    class EmptyInput(BaseModel):
        pass

    class EmptyOutput(BaseModel):
        accepted: bool

    registry = ToolRegistry()
    registry.register(
        ToolDefinition(
            name="publish.external",
            description="Publish one external action",
            input_model=EmptyInput,
            output_model=EmptyOutput,
            handler=lambda _payload: {"accepted": True},
            risk_class=RiskClass.LOW,
            external_side_effect=True,
        )
    )
    registry.register(
        ToolDefinition(
            name="state.read",
            description="Read one safe state value",
            input_model=EmptyInput,
            output_model=EmptyOutput,
            handler=lambda _payload: {"accepted": True},
        )
    )
    router = ModelRouter()
    router.register_provider(StubProvider())
    core = AgentCore(router, registry)
    request = AgentPlanRequest(
        goal="Run the safe read before the external publish",
        tools=[
            {
                "name": "publish.external",
                "payload": {},
                "depends_on": ["step-3"],
            },
            {
                "name": "state.read",
                "payload": {},
                "depends_on": [],
            },
        ],
    )
    plan = core.plan(request)

    runner = object.__new__(AgentWorkflowRunner)
    runner.core = core
    step_specs, tools_by_execution_step = runner._durable_step_metadata(
        request, plan
    )

    assert step_specs == [
        {
            "step_number": 1,
            "kind": "provider_selection",
            "name": "provider_selection",
            "input_digest": None,
        },
        {
            "step_number": 2,
            "kind": "safe_tool",
            "name": "state.read",
            "input_digest": core.workflow_step_input_digest(3, request.tools[1]),
        },
        {
            "step_number": 3,
            "kind": "external_tool",
            "name": "publish.external",
            "input_digest": core.workflow_step_input_digest(2, request.tools[0]),
        },
    ]
    assert tools_by_execution_step[2].name == "state.read"
    assert tools_by_execution_step[2].external_side_effect is False
    assert tools_by_execution_step[3].name == "publish.external"
    assert tools_by_execution_step[3].external_side_effect is True
