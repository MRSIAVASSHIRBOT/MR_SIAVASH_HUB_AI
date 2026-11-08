"""Authenticated read-only inventory of explicitly enrolled projects."""

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
    """Return configured inventory without implying repository or runtime health."""
    return build_project_registry()
