"""Read-only inventory of the active project portfolio."""

from datetime import UTC, datetime

from fastapi import APIRouter, Depends

from mrhub.api.dependencies import require_user

router = APIRouter(
    prefix="/projects",
    tags=["projects"],
    dependencies=[Depends(require_user)],
)

# Explicit enrollment prevents accidental disclosure or silent enrollment of
# every repository visible to a linked GitHub account.
PROJECTS: tuple[dict[str, str | None], ...] = (
    {
        "project_id": "mr-siavash-hub-ai",
        "name": "MR_SIAVASH_HUB_AI",
        "repository": "MRSIAVASSHIRBOT/MR_SIAVASH_HUB_AI",
        "repository_url": "https://github.com/MRSIAVASSHIRBOT/MR_SIAVASH_HUB_AI",
        "service_url": None,
        "description": "هستهٔ دستیار هوشمند، گردش‌کارها و پنل مدیریت",
    },
    {
        "project_id": "mr-siavash-ai",
        "name": "MR_SIAVASH_AI",
        "repository": "MRSIAVASSHIRBOT/MR_SIAVASH_AI",
        "repository_url": "https://github.com/MRSIAVASSHIRBOT/MR_SIAVASH_AI",
        "service_url": None,
        "description": "وب‌سایت و هویت دیجیتال شخصی",
    },
    {
        "project_id": "gshop",
        "name": "Gshop",
        "repository": "MRSIAVASSHIRBOT/Gshop",
        "repository_url": "https://github.com/MRSIAVASSHIRBOT/Gshop",
        "service_url": "https://gshop11.ir/",
        "description": "فروشگاه اینترنتی و پنل مدیریت",
    },
)


@router.get("/registry", summary="Read the explicitly enrolled project registry")
def project_registry() -> dict[str, object]:
    """Return project inventory without implying repository or runtime health."""
    observed_at = datetime.now(UTC).isoformat()
    projects = []
    for project in PROJECTS:
        projects.append(
            {
                **project,
                "repository_status": "not_configured",
                "runtime_status": "unknown",
                "infrastructure_status": "not_configured",
                "status_reason": (
                    "GitHub and external runtime observations are not yet "
                    "configured for the Hub server."
                ),
            }
        )
    return {
        "contract_version": "1.0",
        "source": "explicit_project_registry",
        "observed_at": observed_at,
        "projects": projects,
    }
