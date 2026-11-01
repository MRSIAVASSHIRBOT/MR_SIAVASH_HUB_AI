"""Authenticated agent planning API."""

from fastapi import APIRouter, Depends, HTTPException
from uuid import UUID

from mrhub.agents.core import AgentCore, AgentPlanRequest
from mrhub.api.dependencies import require_user
from mrhub.api.routes.models import build_model_router
from mrhub.agents.repository import AgentRunRepository
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
