"""Explicitly enrolled project portfolio metadata and bounded Agent context."""

import sqlite3
from datetime import UTC, datetime

from fastapi import HTTPException

from mrhub.api.routes.health import health as read_local_health
from mrhub.api.routes.health import readiness as read_local_readiness
from mrhub.integrations.github_status import get_repository_status

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
    {
        "project_id": "mr-siavash-el-ai",
        "name": "MR_SIAVASH_EL_AI",
        "repository": "MRSIAVASSHIRBOT/MR_SIAVASH_EL_AI",
        "repository_url": "https://github.com/MRSIAVASSHIRBOT/MR_SIAVASH_EL_AI",
        "service_url": None,
        "description": "رابط تلگرامی هوش مصنوعی با حافظه و اجرای کنترل‌شده از طریق Hub",
    },
)


def _hub_runtime_observation() -> dict[str, object]:
    """Observe this Hub process through its own read-only health/readiness checks."""
    observed_at = datetime.now(UTC).isoformat()
    try:
        liveness = read_local_health()
        readiness = read_local_readiness()
    except HTTPException as exc:
        failed = exc.status_code >= 500
        return {
            "status": "failing" if failed else "unknown",
            "source": "local_health_and_readiness",
            "observed_at": observed_at,
            "reason_code": "hub_readiness_failed" if failed else "hub_readiness_unavailable",
            "details": {
                "liveness": "unknown",
                "database": "unavailable",
                "schema_version": None,
                "worker": "unknown",
                "worker_heartbeat_age_seconds": None,
            },
        }
    except (OSError, sqlite3.Error, TypeError, ValueError):
        return {
            "status": "unknown",
            "source": "local_health_and_readiness",
            "observed_at": observed_at,
            "reason_code": "hub_runtime_observation_failed",
            "details": {
                "liveness": "unknown",
                "database": "unknown",
                "schema_version": None,
                "worker": "unknown",
                "worker_heartbeat_age_seconds": None,
            },
        }

    worker = readiness.get("worker")
    database = readiness.get("database")
    schema_version = readiness.get("schema_version")
    heartbeat_age = readiness.get("worker_heartbeat_age_seconds")
    details = {
        "liveness": liveness.get("status") if isinstance(liveness, dict) else "unknown",
        "database": database if isinstance(database, str) else "unknown",
        "schema_version": schema_version
        if isinstance(schema_version, int) and not isinstance(schema_version, bool)
        else None,
        "worker": worker if isinstance(worker, str) else "unknown",
        "worker_heartbeat_age_seconds": heartbeat_age
        if isinstance(heartbeat_age, int) and not isinstance(heartbeat_age, bool) and heartbeat_age >= 0
        else None,
    }

    if details["liveness"] != "ok" or readiness.get("status") != "ready" or database != "ready":
        status = "failing"
        reason_code = "hub_runtime_not_ready"
    elif worker != "running":
        status = "degraded"
        reason_code = "hub_worker_not_detected"
    else:
        status = "healthy"
        reason_code = "hub_runtime_and_worker_healthy"

    return {
        "status": status,
        "source": "local_health_and_readiness",
        "observed_at": observed_at,
        "reason_code": reason_code,
        "details": details,
    }


def build_project_registry(*, include_live_status: bool = False) -> dict[str, object]:
    """Build the owner inventory; only the dashboard opts into live public GitHub reads.

    Agent context deliberately uses the default static mode to avoid external
    requests during model inference and to keep the evidence payload deterministic.
    """
    observed_at = datetime.now(UTC).isoformat()
    hub_runtime = _hub_runtime_observation() if include_live_status else None
    projects = []
    for project in PROJECTS:
        if include_live_status:
            github_status = get_repository_status(str(project["repository"]))
            repository_observation = {
                "status": github_status["status"],
                "source": github_status["source"],
                "observed_at": github_status["observed_at"],
                "reason_code": github_status["reason_code"],
            }
            repository_details = github_status
            status_reason = (
                "GitHub metadata is read-only and public; runtime and Cloudflare "
                "observations remain independently unconfigured."
            )
        else:
            repository_observation = {
                "status": "not_configured",
                "source": "project_registry_configuration",
                "observed_at": observed_at,
                "reason_code": "github_live_status_not_requested",
            }
            repository_details = None
            status_reason = (
                "This project context contains configured metadata only; "
                "it is not a live repository or runtime health observation."
            )

        if include_live_status and project["project_id"] == "mr-siavash-hub-ai":
            runtime_observation = hub_runtime
            status_reason = (
                "GitHub metadata is read-only; Hub runtime uses local /health, /ready "
                "and worker heartbeat checks; Cloudflare observations remain unconfigured."
            )
        else:
            runtime_observation = {
                "status": "unknown",
                "source": "project_registry_configuration",
                "observed_at": observed_at,
                "reason_code": "runtime_probe_not_configured",
            }
            if include_live_status:
                status_reason = (
                    "GitHub metadata is read-only; this project's runtime and Cloudflare "
                    "observations remain independently unconfigured."
                )

        status_observations = {
            "repository": repository_observation,
            "runtime": runtime_observation,
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
                "repository_status": repository_observation["status"],
                "runtime_status": status_observations["runtime"]["status"],
                "infrastructure_status": status_observations["infrastructure"]["status"],
                "status_observations": status_observations,
                "repository_details": repository_details,
                "status_reason": status_reason,
            }
        )
    return {
        "contract_version": "1.0",
        "source": "explicit_project_registry",
        "observed_at": observed_at,
        "projects": projects,
    }


def get_project_context(project_id: str) -> dict[str, object] | None:
    """Return one enrolled project's static, explicitly untrusted metadata."""
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
