"""Authenticated API for registering and reviewing capability sources."""
from __future__ import annotations

from typing import Annotated, Literal

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field

from mrhub.api.dependencies import require_user
from mrhub.capabilities.github_discovery import (
    GitHubDiscoveryError,
    discover_github_candidate,
)
from mrhub.capabilities.registry import (
    STATUSES,
    CapabilityNotFound,
    CapabilityRegistry,
    CapabilityValidationError,
)
from mrhub.config import get_settings
from mrhub.diagnostics.hardware import collect_hardware_report
from mrhub.security.auth import AuthenticatedUser
from mrhub.tools.builtins import build_tool_registry

router = APIRouter(
    prefix="/capabilities",
    tags=["capabilities"],
    dependencies=[Depends(require_user)],
)


class CapabilityCandidateRequest(BaseModel):
    source_url: str = Field(min_length=1, max_length=2048)
    display_name: str = Field(min_length=1, max_length=160)
    summary: str = Field(default="", max_length=1000)
    source_kind: Literal[
        "github_repository", "documentation", "package", "api", "other"
    ] = "github_repository"
    integration_type: Literal[
        "connector", "skill", "python_package", "http_api", "adapter", "manual"
    ] = "manual"
    capabilities: list[str] = Field(default_factory=list, max_length=50)
    license_id: str = Field(default="unknown", min_length=1, max_length=80)


class GitHubDiscoveryRequest(BaseModel):
    source_url: str = Field(min_length=1, max_length=2048)


class CapabilityTransitionRequest(BaseModel):
    status: Literal["discovered", "reviewing", "approved", "rejected", "disabled"]
    license_id: str | None = Field(default=None, max_length=80)
    evidence: dict[str, str] = Field(default_factory=dict)


class CapabilityRuntimeBindingRequest(BaseModel):
    capability_name: str = Field(
        min_length=1,
        max_length=80,
        pattern=r"^[a-z][a-z0-9_.-]{0,79}$",
    )
    tool_name: str = Field(
        min_length=1,
        max_length=80,
        pattern=r"^[a-z][a-z0-9_.-]{0,79}$",
    )


def get_registry() -> CapabilityRegistry:
    return CapabilityRegistry(get_settings().database_path)


@router.get("/hardware-report")
def get_local_hardware_report(
    _user: Annotated[AuthenticatedUser, Depends(require_user)],
) -> dict[str, object]:
    """Collect a read-only report from the host running this API process.

    The report is returned to the authenticated owner only; it is not persisted,
    uploaded, benchmarked, or used to start/install any software.
    """
    return {
        **collect_hardware_report(),
        "host_scope": "api_process_runtime",
        "persisted": False,
        "transmitted_to_provider": False,
        "execution": "diagnostics_only",
    }


@router.post("/candidates", status_code=status.HTTP_201_CREATED)
def register_candidate(
    payload: CapabilityCandidateRequest,
    _user: Annotated[AuthenticatedUser, Depends(require_user)],
) -> dict[str, object]:
    """Register a source for review; this endpoint never fetches or executes it."""
    try:
        candidate = get_registry().add_candidate(**payload.model_dump())
    except CapabilityValidationError as exc:
        code = 409 if "already in the catalog" in str(exc) else 422
        raise HTTPException(status_code=code, detail=str(exc)) from exc
    return candidate.as_dict()


@router.post("/discover", status_code=status.HTTP_201_CREATED)
def discover_candidate(
    payload: GitHubDiscoveryRequest,
    _user: Annotated[AuthenticatedUser, Depends(require_user)],
) -> dict[str, object]:
    """Fetch bounded public GitHub repository metadata and register it for review."""
    try:
        _candidate, result = discover_github_candidate(payload.source_url, get_registry())
    except GitHubDiscoveryError as exc:
        raise HTTPException(status_code=exc.status_code, detail={"code": exc.code, "message": str(exc)}) from exc
    except CapabilityValidationError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return result


@router.get("/candidates")
def list_candidates(
    _user: Annotated[AuthenticatedUser, Depends(require_user)],
    candidate_status: Literal[
        "discovered", "reviewing", "approved", "rejected", "disabled"
    ] | None = Query(default=None, alias="status"),
    limit: int = Query(default=50, ge=1, le=100),
) -> dict[str, object]:
    items = get_registry().list_candidates(status=candidate_status, limit=limit)
    return {
        "items": [item.as_dict() for item in items],
        "count": len(items),
        "allowed_statuses": sorted(STATUSES),
    }


@router.get("/candidates/{candidate_id}")
def get_candidate(
    candidate_id: str,
    _user: Annotated[AuthenticatedUser, Depends(require_user)],
) -> dict[str, object]:
    try:
        return get_registry().get(candidate_id).as_dict()
    except CapabilityNotFound as exc:
        raise HTTPException(status_code=404, detail="Capability candidate not found") from exc


def _build_runtime_tool_catalog(owner_user_id: str):
    try:
        return build_tool_registry(owner_user_id=owner_user_id)
    except Exception as exc:  # noqa: BLE001 - fail closed without exposing config details.
        raise HTTPException(
            status_code=503,
            detail="The registered runtime tool catalog is temporarily unavailable.",
        ) from exc


def _runtime_binding_response(binding, tool=None) -> dict[str, object]:
    runtime_tool: dict[str, object] | None = None
    if tool is not None:
        runtime_tool = {
            "name": tool.name,
            "risk_class": tool.risk_class.value,
            "required_permissions": sorted(tool.required_permissions),
            "external_side_effect": tool.external_side_effect,
            "replay_safety": tool.replay_safety.value,
        }
    return {
        **binding.as_dict(),
        "runtime_tool": runtime_tool,
        "runtime_tool_available": tool is not None,
        "binding_mode": "metadata_reference_only",
        "tool_execution_started": False,
        "permissions_granted": False,
        "source_code_loaded": False,
    }


@router.post(
    "/candidates/{candidate_id}/runtime-bindings",
    status_code=status.HTTP_201_CREATED,
)
def bind_candidate_runtime_tool(
    candidate_id: str,
    payload: CapabilityRuntimeBindingRequest,
    user: Annotated[AuthenticatedUser, Depends(require_user)],
) -> dict[str, object]:
    """Record a link to an existing Hub ToolDefinition; never load candidate code."""
    registry = get_registry()
    try:
        candidate = registry.get(candidate_id)
        if candidate.status != "approved":
            raise CapabilityValidationError(
                "Only an approved capability candidate can bind to a runtime tool"
            )
        tools = _build_runtime_tool_catalog(user.user_id)
        tool = tools.get(payload.tool_name)
        binding = registry.bind_runtime_tool(
            candidate_id,
            capability_name=payload.capability_name,
            tool_name=payload.tool_name,
            bound_by_user_id=user.user_id,
            available_tool_names=frozenset(item["name"] for item in tools.catalog()),
        )
    except CapabilityNotFound as exc:
        raise HTTPException(status_code=404, detail="Capability candidate not found") from exc
    except CapabilityValidationError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except LookupError as exc:
        raise HTTPException(
            status_code=409,
            detail="The requested runtime tool is not registered by the Hub.",
        ) from exc
    return _runtime_binding_response(binding, tool)


@router.get("/candidates/{candidate_id}/runtime-bindings")
def list_candidate_runtime_bindings(
    candidate_id: str,
    user: Annotated[AuthenticatedUser, Depends(require_user)],
) -> dict[str, object]:
    """Show binding metadata and whether its exact tool still exists in this runtime."""
    registry = get_registry()
    try:
        candidate = registry.get(candidate_id)
        tools = _build_runtime_tool_catalog(user.user_id)
        catalog = {item["name"]: item for item in tools.catalog()}
        bindings = registry.list_runtime_bindings(candidate_id)
    except CapabilityNotFound as exc:
        raise HTTPException(status_code=404, detail="Capability candidate not found") from exc

    items = []
    for binding in bindings:
        try:
            tool = tools.get(binding.tool_name)
        except LookupError:
            tool = None
        items.append(_runtime_binding_response(binding, tool))
    return {
        "candidate_id": candidate_id,
        "candidate_status": candidate.status,
        "items": items,
        "count": len(items),
        "available_runtime_tool_count": len(catalog),
        "binding_mode": "metadata_reference_only",
        "permissions_granted": False,
        "tool_execution_started": False,
    }


@router.delete("/candidates/{candidate_id}/runtime-bindings/{binding_id}")
def remove_candidate_runtime_binding(
    candidate_id: str,
    binding_id: str,
    user: Annotated[AuthenticatedUser, Depends(require_user)],
) -> dict[str, object]:
    """Remove only the binding recorded by the current authenticated owner."""
    try:
        deleted = get_registry().remove_runtime_binding(
            candidate_id,
            binding_id,
            requested_by_user_id=user.user_id,
        )
    except CapabilityNotFound as exc:
        raise HTTPException(status_code=404, detail="Capability candidate not found") from exc
    if not deleted:
        raise HTTPException(status_code=404, detail="Capability runtime binding not found")
    return {
        "candidate_id": candidate_id,
        "binding_id": binding_id,
        "deleted": True,
        "permissions_changed": False,
        "tool_execution_started": False,
    }


@router.post("/candidates/{candidate_id}/transition")
def transition_candidate(
    candidate_id: str,
    payload: CapabilityTransitionRequest,
    _user: Annotated[AuthenticatedUser, Depends(require_user)],
) -> dict[str, object]:
    try:
        candidate = get_registry().transition(
            candidate_id,
            payload.status,
            license_id=payload.license_id,
            evidence=payload.evidence,
        )
    except CapabilityNotFound as exc:
        raise HTTPException(status_code=404, detail="Capability candidate not found") from exc
    except CapabilityValidationError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return candidate.as_dict()
