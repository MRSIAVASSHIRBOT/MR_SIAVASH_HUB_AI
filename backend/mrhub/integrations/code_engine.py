"""Optional local code-engine integration."""

from fastapi import APIRouter, Depends

from mrhub.api.dependencies import require_user
from mrhub.config import get_settings
from mrhub.integrations.health_probe import probe_loopback_service

router = APIRouter(
    prefix="/integrations/code-engine",
    tags=["integrations"],
    dependencies=[Depends(require_user)],
)


@router.get("/status", summary="Check local code engine connectivity")
async def code_engine_status() -> dict[str, object]:
    """Probe the separately managed coding service without executing code."""
    settings = get_settings()
    if not settings.code_engine_enabled:
        return {
            "status": "disabled",
            "configured": bool(settings.code_engine_base_url),
        }
    return await probe_loopback_service(
        settings.code_engine_base_url,
        settings.code_engine_health_path,
        timeout_seconds=settings.code_engine_timeout_seconds,
        max_response_bytes=settings.code_engine_max_response_bytes,
    )
