"""Authenticated agent planning API."""

from fastapi import APIRouter, Depends, HTTPException

from mrhub.agents.core import AgentCore, AgentPlanRequest
from mrhub.api.dependencies import require_user
from mrhub.api.routes.models import build_model_router
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
