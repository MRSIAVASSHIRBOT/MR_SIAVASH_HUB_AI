"""Authenticated metadata-only endpoint for the frozen specialist agent registry."""

from fastapi import APIRouter, Depends, HTTPException, Request

from mrhub.agents.registry import AgentRegistry
from mrhub.api.dependencies import require_user

router = APIRouter(
    prefix="/agent",
    tags=["agent"],
    dependencies=[Depends(require_user)],
)


@router.get("/registry")
def get_agent_registry_manifest(request: Request) -> dict[str, object]:
    """Return reviewed agent metadata without exposing prompts or granting execution."""
    registry = getattr(request.app.state, "agent_registry", None)
    if not isinstance(registry, AgentRegistry) or not registry.frozen:
        raise HTTPException(
            status_code=503,
            detail="Agent registry is not ready",
        )
    return registry.manifest()
