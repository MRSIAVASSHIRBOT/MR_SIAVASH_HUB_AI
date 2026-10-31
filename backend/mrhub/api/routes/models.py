"""Model catalog endpoint; only an explicit local stub adapter is registered."""

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from mrhub.api.dependencies import require_user
from mrhub.providers.router import ModelRequest, ModelRouter
from mrhub.providers.stub import StubProvider

router = APIRouter(prefix="/models", tags=["models"], dependencies=[Depends(require_user)])
router_instance = ModelRouter()
router_instance.register_provider(StubProvider())


class RouteModelRequest(BaseModel):
    requires_text: bool = True
    requires_vision: bool = False
    requires_audio: bool = False
    requires_tool_calling: bool = False
    prefer_local: bool = False


@router.get("")
def list_models():
    return router_instance.catalog()


@router.post("/select")
def select_model(payload: RouteModelRequest) -> dict[str, str | bool]:
    try:
        selection = router_instance.select(ModelRequest(**payload.model_dump()))
    except LookupError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    return selection.model_dump()
