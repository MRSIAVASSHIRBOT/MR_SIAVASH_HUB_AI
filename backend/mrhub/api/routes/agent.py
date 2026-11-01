"""Authenticated agent planning API."""

import hashlib
import json
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException

from mrhub.agents.core import AgentCore, AgentPlanRequest
from mrhub.agents.repository import AgentRunRepository
from mrhub.agents.workflow_repository import AgentWorkflowRepository
from mrhub.api.dependencies import require_user
from mrhub.api.routes.models import build_model_router
from mrhub.config import get_settings
from mrhub.tools.builtins import build_tool_registry

router = APIRouter(prefix="/agent", tags=["agent"], dependencies=[Depends(require_user)])


@router.post("/plan")
def create_agent_plan(request: AgentPlanRequest) -> dict[str, object]:
    core = AgentCore(build_model_router(), build_tool_registry())
    try:
        return core.plan(request)
    except LookupError as exc:
        raise HTTPException(
            status_code=503,
            detail="No registered provider satisfies the requested capabilities",
        ) from exc

@router.post("/execute")
def execute_agent_tools(request: AgentPlanRequest) -> dict[str, object]:
    """Run only explicitly requested tools that pass the server policy checks."""
    core = AgentCore(build_model_router(), build_tool_registry())
    try:
        execution = core.execute(request)
        repository = AgentRunRepository(get_settings().database_path)
        run = repository.record(request.model_dump(mode="json"), execution)
        return {**execution, "run": run}
    except LookupError as exc:
        raise HTTPException(
            status_code=503,
            detail="No registered provider satisfies the requested capabilities",
        ) from exc

@router.get("/runs/{run_id}")
def get_agent_run(run_id: UUID) -> dict[str, object]:
    repository = AgentRunRepository(get_settings().database_path)
    repository.initialize()
    run = repository.get(run_id)
    if run is None:
        raise HTTPException(status_code=404, detail="Agent run not found")
    return run



def _workflow_digest(request: AgentPlanRequest) -> str:
    """Fingerprint non-sensitive request metadata only."""
    metadata = {
        "goal_length": len(request.goal),
        "tool_names": [tool.name for tool in request.tools],
        "requires_text": request.requires_text,
        "requires_vision": request.requires_vision,
        "requires_audio": request.requires_audio,
        "requires_tool_calling": request.requires_tool_calling,
        "prefer_local": request.prefer_local,
    }
    encoded = json.dumps(metadata, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


@router.post("/workflows")
def execute_agent_workflow(request: AgentPlanRequest) -> dict[str, object]:
    """Execute an allowed workflow while persisting each step transition."""
    core = AgentCore(build_model_router(), build_tool_registry())
    try:
        plan = core.plan(request)
        repository = AgentWorkflowRepository(get_settings().database_path)
        workflow = repository.create(_workflow_digest(request), plan)
        if workflow["status"] == "blocked":
            return {"workflow": workflow, "execution": None}
        workflow_id = UUID(str(workflow["workflow_id"]))
        repository.start(workflow_id)
        execution = core.execute(
            request,
            on_step=lambda number, status, error: repository.record_step(
                workflow_id, number, status, error
            ),
        )
        terminal_status = (
            "succeeded" if execution["execution_completed"]
            else "failed" if execution.get("execution_started")
            else "blocked"
        )
        repository.finish(workflow_id, terminal_status)
        return {
            "workflow": repository.get(workflow_id),
            "execution": {
                "execution_completed": execution["execution_completed"],
                "model_inference_started": execution["model_inference_started"],
                "tools_executed": execution["tools_executed"],
                "error_code": execution.get("error_code"),
                "executed_tool_count": len(execution["results"]),
            },
        }
    except LookupError as exc:
        raise HTTPException(
            status_code=503,
            detail="No registered provider satisfies the requested capabilities",
        ) from exc


@router.get("/workflows/{workflow_id}")
def get_agent_workflow(workflow_id: UUID) -> dict[str, object]:
    repository = AgentWorkflowRepository(get_settings().database_path)
    repository.initialize()
    workflow = repository.get(workflow_id)
    if workflow is None:
        raise HTTPException(status_code=404, detail="Agent workflow not found")
    return workflow
