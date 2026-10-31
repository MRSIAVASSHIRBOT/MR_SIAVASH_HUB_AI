"""Policy inspection endpoint for the local operator console."""

from fastapi import APIRouter
from pydantic import BaseModel, Field

from mrhub.domain.tasks import RiskClass
from mrhub.security.policy import ActionRequest, PolicyEngine, PolicyResult

router = APIRouter(prefix="/policy", tags=["policy"])
engine = PolicyEngine()


class EvaluatePolicyRequest(BaseModel):
    action: str = Field(min_length=1, max_length=100, pattern=r"^[a-zA-Z0-9_.:-]+$")
    risk_class: RiskClass
    granted_permissions: set[str] = set()
    required_permissions: set[str] = set()
    external_side_effect: bool = False
    user_approved: bool = False


@router.post("/evaluate", response_model=PolicyResult)
def evaluate_policy(payload: EvaluatePolicyRequest) -> PolicyResult:
    return engine.evaluate(ActionRequest(**payload.model_dump()))
