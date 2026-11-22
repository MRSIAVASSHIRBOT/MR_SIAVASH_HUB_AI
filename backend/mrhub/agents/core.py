"""Deterministic planning core connecting model routing, tools, and policy."""

from collections.abc import Callable
import hashlib
import json
from typing import Annotated

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    ValidationError,
    field_validator,
    model_validator,
)

from mrhub.agents.capability_gaps import MAX_NAME_LENGTH, evaluate_capability_gaps
from mrhub.agents.workflow_plan import WorkflowPlanError, WorkflowStep, build_workflow_plan
from mrhub.providers.router import ModelRequest, ModelRouter
from mrhub.security.policy import PolicyDecision, PolicyEngine
from mrhub.tools.registry import ToolExecutionError, ToolPolicyError, ToolRegistry
WorkflowDependencyId = Annotated[
    str, Field(min_length=6, max_length=6, pattern=r"^step-[2-6]$")
]
