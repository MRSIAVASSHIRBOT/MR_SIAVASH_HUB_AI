"""Model catalog endpoint; no provider calls are made by these routes."""

from fastapi import APIRouter, Depends, HTTPException

from mrhub.api.dependencies import require_user
from pydantic import BaseModel

from mrhub.providers.router import ModelCapability, ModelDescriptor, ModelRequest, ModelRouter

router = APIRouter(prefix="/models", tags=["models"], dependencies=[Depends(require_user)])
router_instance = ModelRouter()
router_instance.register(ModelDescriptor(
    provider="mock", model="mock-text-v1", capability=ModelCapability(),
    available=True, local=True, priority=10,
))


class RouteModelRequest(BaseModel):
    requires_vision: bool = False
    requires_audio: bool = False
    requires_tool_calling: bool = False
    prefer_local: bool = False


@router.get("")
def list_models() -> list[ModelDescriptor]:
    return router_instance.catalog()


@router.post("/select")
def select_model(payload: RouteModelRequest) -> dict[str, str | bool]:
    try:
        selection = router_instance.select(ModelRequest(**payload.model_dump()))
    except LookupError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    return selection.model_dump()
