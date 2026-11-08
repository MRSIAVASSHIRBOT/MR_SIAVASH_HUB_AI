"""Explicitly enrolled project portfolio metadata and agent context."""

from datetime import UTC, datetime

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
        "service_url": "https://mrsiavasshirbot.github.io/MR_SIAVASH_AI/",
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


def build_project_registry() -> dict[str, object]:
    """Return configured project metadata with explicit non-live status provenance."""
    observed_at = datetime.now(UTC).isoformat()
    projects = []
    for project in PROJECTS:
        status_observations = {
            "repository": {
                "status": "not_configured",
                "source": "project_registry_configuration",
                "observed_at": observed_at,
                "reason_code": "github_integration_not_configured",
            },
            "runtime": {
                "status": "unknown",
                "source": "project_registry_configuration",
                "observed_at": observed_at,
                "reason_code": "runtime_probe_not_configured",
            },
            "infrastructure": {
                "status": "not_configured",
                "source": "project_registry_configuration",
                "observed_at": observed_at,
                "reason_code": "cloudflare_integration_not_configured",
            },
        }
        projects.append(
            {
                **project,
                "repository_status": status_observations["repository"]["status"],
                "runtime_status": status_observations["runtime"]["status"],
                "infrastructure_status": status_observations["infrastructure"]["status"],
                "status_observations": status_observations,
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


def get_project_context(project_id: str) -> dict[str, object] | None:
    """Return only one enrolled project's metadata for an authenticated Agent run."""
    registry = build_project_registry()
    for project in registry["projects"]:
        if project["project_id"] == project_id:
            return {
                "reference": f"project-registry://projects/{project_id}",
                "source": registry["source"],
                "contract_version": registry["contract_version"],
                "observed_at": registry["observed_at"],
                "trust_classification": "server_configured_metadata_not_live_health",
                "content_is_untrusted_data": True,
                "project": project,
            }
    return None
