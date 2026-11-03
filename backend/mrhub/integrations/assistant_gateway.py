"""Optional local assistant runtime integration."""

from fastapi import APIRouter, Depends

from mrhub.api.dependencies import require_user
from mrhub.config import get_settings
from mrhub.integrations.health_probe import (
    INTEGRATION_CONTRACT_VERSION,
    probe_loopback_service,
)

router = APIRouter(
    prefix="/integrations/assistant-gateway",
    tags=["integrations"],
    dependencies=[Depends(require_user)],
)


@router.get("/status", summary="Check local assistant gateway connectivity")
async def assistant_gateway_status() -> dict[str, object]:
    """Probe the separately managed assistant runtime without exposing its body."""
    settings = get_settings()
    if not settings.assistant_gateway_enabled:
        return {
            "contract_version": INTEGRATION_CONTRACT_VERSION,
            "status": "disabled",
            "configured": bool(settings.assistant_gateway_base_url),
        }
    return await probe_loopback_service(
        settings.assistant_gateway_base_url,
        settings.assistant_gateway_health_path,
        timeout_seconds=settings.assistant_gateway_timeout_seconds,
        max_response_bytes=settings.assistant_gateway_max_response_bytes,
    )
