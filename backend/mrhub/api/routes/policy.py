"""Policy inspection endpoint for the local operator console."""

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from mrhub.api.dependencies import require_user
from mrhub.domain.tasks import RiskClass
from mrhub.security.policy import ActionRequest, PolicyEngine, PolicyResult

router = APIRouter(prefix="/policy", tags=["policy"], dependencies=[Depends(require_user)])
engine = PolicyEngine()


class EvaluatePolicyRequest(BaseModel):
    action: str = Field(min_length=1, max_length=100, pattern=r"^[a-zA-Z0-9_.:-]+$")
    risk_class: RiskClass
    granted_permissions: set[str] = Field(default_factory=set)
    required_permissions: set[str] = Field(default_factory=set)
    external_side_effect: bool = False


@router.post("/evaluate", response_model=PolicyResult)
def evaluate_policy(payload: EvaluatePolicyRequest) -> PolicyResult:
    return engine.evaluate(ActionRequest(**payload.model_dump(), user_approved=False))
