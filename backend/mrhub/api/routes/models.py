"""Authenticated model catalog and explicitly enabled local inference endpoint."""

from time import perf_counter
from typing import Any, Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from mrhub.api.dependencies import require_user
from mrhub.config import get_settings
from mrhub.diagnostics.model_profiles import get_model_profile, list_model_profiles
from mrhub.diagnostics.model_recommender import recommend_model_profiles
from mrhub.diagnostics.resource_advisor import assess_model_resources
from mrhub.providers.base import ProviderError, ProviderRequest
from mrhub.providers.ollama import OllamaProvider
from mrhub.providers.openrouter import OpenRouterProvider
from mrhub.providers.router import ModelRequest, ModelRouter
from mrhub.providers.stub import StubProvider

router = APIRouter(prefix="/models", tags=["models"], dependencies=[Depends(require_user)])


def build_model_router(
    *,
    provider_mode: Literal["all", "local", "remote"] = "all",
    include_stub: bool = True,
) -> ModelRouter:
    """Build an explicit provider set; constrained modes never silently fall back."""
    settings = get_settings()
    model_router = ModelRouter()
    if include_stub and provider_mode == "all":
        model_router.register_provider(StubProvider())
    if provider_mode in {"all", "local"} and settings.local_inference_enabled and settings.local_inference_model:
        model_router.register_provider(
            OllamaProvider(
                model=settings.local_inference_model,
                base_url=settings.local_inference_base_url,
                timeout_seconds=settings.local_inference_timeout_seconds,
            )
        )
    if (
        provider_mode in {"all", "remote"}
        and settings.remote_inference_enabled
        and settings.remote_inference_api_key is not None
        and settings.remote_inference_model
    ):
        model_router.register_provider(
            OpenRouterProvider(
                model=settings.remote_inference_model,
                api_key=settings.remote_inference_api_key.get_secret_value(),
                base_url=settings.remote_inference_base_url,
                timeout_seconds=settings.remote_inference_timeout_seconds,
            )
        )
    return model_router


class RouteModelRequest(BaseModel):
    requires_text: bool = True
    requires_vision: bool = False
    requires_audio: bool = False
    requires_tool_calling: bool = False
    prefer_local: bool = False


class ProviderHealthCheckRequest(BaseModel):
    timeout_seconds: float = Field(default=2.0, ge=0.1, le=5.0)


class GenerateModelRequest(BaseModel):
    input_text: str = Field(min_length=1, max_length=32_000)
    max_output_tokens: int = Field(default=512, ge=1, le=2048)


class AssessModelRequest(BaseModel):
    hardware_report: dict[str, Any]
    model_profile: dict[str, Any]
    system_reserve_gib: float = Field(default=2.0, ge=0, le=64)


class CompareModelsRequest(BaseModel):
    hardware_report: dict[str, Any]
    profile_ids: list[str] = Field(min_length=1, max_length=20)
    system_reserve_gib: float = Field(default=2.0, ge=0, le=64)


class RecommendModelsRequest(BaseModel):
    hardware_report: dict[str, Any]
    profile_ids: list[str] = Field(
        default_factory=lambda: ["small-text-cpu-example", "gpu-model-example"],
        min_length=1,
        max_length=20,
    )
    system_reserve_gib: float = Field(default=2.0, ge=0, le=64)


@router.get("")
def list_models():
    return build_model_router().catalog()


@router.get("/providers")
def list_providers() -> dict[str, object]:
    """List configured adapters without probing or invoking external services."""
    providers = build_model_router().registry.catalog()
    return {
        "providers": [
            {
                "provider": item.provider,
                "model": item.model,
                "capabilities": {
                    "text": item.capability.text,
                    "vision": item.capability.vision,
                    "audio": item.capability.audio,
                    "tool_calling": item.capability.tool_calling,
                },
                "local": item.local,
                "priority": item.priority,
                "registered": True,
                "declared_available": item.available,
                "health_status": "not_checked",
            }
            for item in providers
        ],
        "count": len(providers),
        "health_probes_performed": False,
        "inference_started": False,
    }


@router.post("/select")
def select_model(payload: RouteModelRequest) -> dict[str, str | bool]:
    try:
        selection = build_model_router().select(ModelRequest(**payload.model_dump()))
    except LookupError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    return selection.model_dump()


@router.post("/providers/health-check")
def check_provider_health(payload: ProviderHealthCheckRequest) -> dict[str, object]:
    """Explicitly probe registered providers with a bounded per-provider timeout."""
    providers = build_model_router().registry.providers()
    results = []
    for provider in providers:
        descriptor = provider.descriptor
        provider_name = descriptor.provider
        model_name = descriptor.model
        started = perf_counter()
        try:
            health = provider.health(timeout_seconds=payload.timeout_seconds)
            available = health.available
            reason_code = health.reason_code
        except ProviderError:
            available = False
            reason_code = "provider_probe_error"
        results.append(
            {
                "provider": provider_name,
                "model": model_name,
                "available": available,
                "status": "healthy" if available else "unavailable",
                "reason_code": reason_code,
                "duration_ms": round((perf_counter() - started) * 1000, 2),
            }
        )
    return {
        "results": results,
        "count": len(results),
        "timeout_seconds": payload.timeout_seconds,
        "inference_started": False,
        "downloads_started": False,
    }


@router.get("/profiles")
def list_profiles():
    return list_model_profiles()


@router.get("/profiles/{profile_id}")
def get_profile(profile_id: str):
    profile = get_model_profile(profile_id)
    if profile is None:
        raise HTTPException(status_code=404, detail="Model profile not found")
    return profile


@router.post("/assess")
def assess_model(payload: AssessModelRequest):
    return assess_model_resources(
        payload.hardware_report,
        payload.model_profile,
        system_reserve_gib=payload.system_reserve_gib,
    )


@router.post("/recommend")
def recommend_models(payload: RecommendModelsRequest):
    """Return a ranked, advisory-only resource recommendation."""
    try:
        return recommend_model_profiles(
            payload.hardware_report,
            payload.profile_ids,
            system_reserve_gib=payload.system_reserve_gib,
        )
    except KeyError as exc:
        unknown_ids = list(exc.args[0])
        raise HTTPException(
            status_code=404,
            detail={"message": "Unknown model profile ID(s)", "profile_ids": unknown_ids},
        ) from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.post("/compare")
def compare_models(payload: CompareModelsRequest):
    """Compare registered model profiles without starting inference or downloads."""
    unique_ids = list(dict.fromkeys(payload.profile_ids))
    profiles = {profile_id: get_model_profile(profile_id) for profile_id in unique_ids}
    unknown_ids = [profile_id for profile_id, profile in profiles.items() if profile is None]
    if unknown_ids:
        raise HTTPException(
            status_code=404,
            detail={"message": "Unknown model profile ID(s)", "profile_ids": unknown_ids},
        )

    results = []
    for profile_id in unique_ids:
        profile = profiles[profile_id]
        assessment = assess_model_resources(
            payload.hardware_report,
            {
                "name": profile["name"],
                "minimum_ram_gib": profile["minimum_ram_gib"],
                "recommended_ram_gib": profile["recommended_ram_gib"],
                "requires_gpu": profile["requires_gpu"],
            },
            system_reserve_gib=payload.system_reserve_gib,
        )
        results.append(
            {
                "profile_id": profile_id,
                "profile_verified": profile["verified"],
                "source_kind": profile["source_kind"],
                "assessment": assessment,
            }
        )

    return {
        "results": results,
        "count": len(results),
        "starts_inference": False,
        "downloads_model": False,
        "limitations": [
            "Sample profiles are unverified estimates, not compatibility guarantees.",
            "GPU VRAM and compute capability are not currently measured.",
        ],
    }


@router.post("/generate-remote")
def generate_remote_model(payload: GenerateModelRequest):
    """Send one request to the explicitly configured remote provider; never fall back."""
    settings = get_settings()
    if (
        not settings.remote_inference_enabled
        or settings.remote_inference_api_key is None
        or not settings.remote_inference_model
    ):
        raise HTTPException(
            status_code=503,
            detail="Remote inference is disabled or incompletely configured; no cloud request was made",
        )
    try:
        model_router = build_model_router()
        provider = model_router.registry.get("openrouter", settings.remote_inference_model)
        return provider.generate(
            ProviderRequest(
                input_text=payload.input_text,
                max_output_tokens=payload.max_output_tokens,
            )
        )
    except ProviderError as exc:
        raise HTTPException(status_code=503, detail=exc.code) from exc
    except LookupError as exc:
        raise HTTPException(status_code=503, detail="Configured remote model is unavailable") from exc


@router.post("/generate")
def generate_local_model(payload: GenerateModelRequest):
    settings = get_settings()
    if not settings.local_inference_enabled or not settings.local_inference_model:
        raise HTTPException(
            status_code=503,
            detail="Local inference is disabled or no local model is configured",
        )
    model_router = build_model_router()
    try:
        return model_router.generate(
            ModelRequest(prefer_local=True),
            ProviderRequest(
                input_text=payload.input_text,
                max_output_tokens=payload.max_output_tokens,
            ),
        )
    except ProviderError as exc:
        raise HTTPException(status_code=503, detail=exc.code) from exc
    except LookupError as exc:
        raise HTTPException(status_code=503, detail="Local model is unavailable") from exc
