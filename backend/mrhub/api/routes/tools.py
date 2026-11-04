"""Authenticated tool catalog and explicitly allow-listed invocation API."""

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict, Field, ValidationError

from mrhub.api.dependencies import require_user
from mrhub.security.policy import PolicyDecision
from mrhub.tools.builtins import build_tool_registry
from mrhub.tools.registry import ToolPolicyError

router = APIRouter(prefix="/tools", tags=["tools"], dependencies=[Depends(require_user)])


class ToolInvokeRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    payload: dict[str, object] = Field(default_factory=dict)


@router.get("")
def list_tools() -> list[dict[str, object]]:
    return build_tool_registry().catalog()


@router.post("/{tool_name}/invoke")
def invoke_tool(tool_name: str, request: ToolInvokeRequest) -> dict[str, object]:
    try:
        result = build_tool_registry().invoke(tool_name, request.payload)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail="Tool is not registered") from exc
    except ValidationError as exc:
        raise HTTPException(status_code=422, detail="Tool input validation failed") from exc
    except ToolPolicyError as exc:
        status_code = 409 if exc.decision is PolicyDecision.REQUIRE_APPROVAL else 403
        raise HTTPException(
            status_code=status_code,
            detail={
                "decision": exc.decision.value,
                "reason": str(exc),
            },
        ) from exc
    return {"tool": tool_name, "result": result, "executed": True}
