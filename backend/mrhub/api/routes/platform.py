"""Authenticated read-only catalog of first-party product capability domains."""
from fastapi import APIRouter, Depends, HTTPException

from mrhub.api.dependencies import require_user
from mrhub.platform.catalog import get_domain, list_domains

router = APIRouter(prefix="/platform", tags=["platform"], dependencies=[Depends(require_user)])


@router.get("/domains", summary="List first-party capability domains")
def capability_domains() -> dict[str, object]:
    return {
        "catalog_version": "1.0",
        "domains": list_domains(),
        "maturity_legend": {
            "foundation": "Core infrastructure exists; end-to-end product acceptance may remain open.",
            "partial": "Some reusable foundations exist; the user-facing service is incomplete.",
            "planned": "A documented target domain; implementation has not been claimed.",
        },
    }


@router.get("/domains/{domain_id}", summary="Get one capability domain")
def capability_domain(domain_id: str) -> dict[str, object]:
    domain = get_domain(domain_id)
    if domain is None:
        raise HTTPException(status_code=404, detail="Capability domain not found")
    return domain
