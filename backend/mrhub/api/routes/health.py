"""Health and readiness endpoints."""

from fastapi import APIRouter

router = APIRouter(tags=["system"])


@router.get("/health", summary="Application liveness")
def health() -> dict[str, str]:
    return {"status": "ok"}
