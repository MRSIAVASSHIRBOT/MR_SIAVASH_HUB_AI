"""Authenticated model catalog and explicitly enabled local inference endpoint."""

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from mrhub.api.dependencies import require_user
from mrhub.config import get_settings
from mrhub.providers.base import ProviderError, ProviderRequest
from mrhub.providers.ollama import OllamaProvider
from mrhub.providers.router import ModelRequest, ModelRouter
from mrhub.providers.stub import StubProvider

router = APIRouter(prefix="/models", tags=["models"], dependencies=[Depends(require_user)])


def build_model_router() -> ModelRouter:
    settings = get_settings()
    model_router = ModelRouter()
    model_router.register_provider(StubProvider())
    if settings.local_inference_enabled and settings.local_inference_model:
        model_router.register_provider(
            OllamaProvider(
                model=settings.local_inference_model,
                base_url=settings.local_inference_base_url,
                timeout_seconds=settings.local_inference_timeout_seconds,
            )
        )
    return model_router


class RouteModelRequest(BaseModel):
    requires_text: bool = True
    requires_vision: bool = False
    requires_audio: bool = False
    requires_tool_calling: bool = False
    prefer_local: bool = False


class GenerateModelRequest(BaseModel):
    input_text: str = Field(min_length=1, max_length=32_000)
    max_output_tokens: int = Field(default=512, ge=1, le=2048)


@router.get("")
def list_models():
    return build_model_router().catalog()


@router.post("/select")
def select_model(payload: RouteModelRequest) -> dict[str, str | bool]:
    try:
        selection = build_model_router().select(ModelRequest(**payload.model_dump()))
    except LookupError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    return selection.model_dump()


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
