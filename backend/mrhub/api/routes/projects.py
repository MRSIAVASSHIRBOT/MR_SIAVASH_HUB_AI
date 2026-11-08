"""Authenticated read-only inventory of the enrolled project portfolio."""

from fastapi import APIRouter, Depends

from mrhub.api.dependencies import require_user
from mrhub.projects.registry import build_project_registry

router = APIRouter(
    prefix="/projects",
    tags=["projects"],
    dependencies=[Depends(require_user)],
)


@router.get("/registry", summary="Read the explicitly enrolled project registry")
def project_registry() -> dict[str, object]:
    """Return bounded public GitHub observations and independent unknown states."""
    return build_project_registry(include_live_status=True)
