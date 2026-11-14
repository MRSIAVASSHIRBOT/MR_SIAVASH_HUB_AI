"""Short-lived, signed public delivery for approved Instagram media assets.

This route is intentionally separate from authenticated media management. It serves only
known image/video assets, requires a valid HMAC and expiry, and never accepts a filesystem path.
"""
from __future__ import annotations

import hashlib
import hmac
import ipaddress
import time
from urllib.parse import urlsplit
from uuid import UUID

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import FileResponse

from mrhub.config import get_settings
from mrhub.media.repository import MAX_OUTPUT_BYTES, MAX_UPLOAD_BYTES, MediaAssetRepository

router = APIRouter(tags=["public-media"])
_ALLOWED_TYPES = {"image/jpeg", "image/png", "video/mp4"}
_MEDIA_SIGNATURES = {
    "image/jpeg": (b"\xff\xd8\xff",),
    "image/png": (b"\x89PNG\r\n\x1a\n",),
}
_MAX_TTL_SECONDS = 900


def _secret() -> bytes:
    value = get_settings().public_media_signing_key
    if value is None or len(value.get_secret_value()) < 32:
        raise HTTPException(status_code=503, detail="public_media_not_configured")
    return value.get_secret_value().encode("utf-8")


def _message(asset_id: str, expires: int) -> bytes:
    return f"v1:{asset_id}:{expires}".encode("ascii")


def sign_asset_url(asset_id: str, *, now: int | None = None) -> str:
    """Build a short-lived HTTPS URL for a UUID media asset, or fail closed."""
    settings = get_settings()
    base = settings.public_media_base_url
    if not base:
        raise ValueError("Public media base URL is not configured")
    parsed = urlsplit(base)
    host = parsed.hostname
    try:
        port = parsed.port
    except ValueError as exc:
        raise ValueError("Invalid public media base URL") from exc
    try:
        address = ipaddress.ip_address(host) if host else None
    except ValueError:
        address = None
    if (
        parsed.scheme != "https" or not host or parsed.username or parsed.password
        or parsed.query or parsed.fragment or port not in (None, 443)
        or host.lower() in {"localhost", "localhost.localdomain"}
        or host.lower().endswith((".local", ".internal", ".test", ".invalid", ".example"))
        or (address is not None and not address.is_global)
    ):
        raise ValueError("Public media base URL must use a public HTTPS hostname")
    expires = (int(time.time()) if now is None else now) + _MAX_TTL_SECONDS
    asset = str(UUID(asset_id))
    signature = hmac.new(_secret(), _message(asset, expires), hashlib.sha256).hexdigest()
    return f"{base.rstrip('/')}/public/media/{asset}?expires={expires}&signature={signature}"


@router.get("/public/media/{asset_id}")
def serve_signed_media(
    asset_id: UUID,
    expires: int = Query(..., ge=1),
    signature: str = Query(..., min_length=64, max_length=64, pattern="^[0-9a-f]{64}$"),
):
    """Serve signed, unexpired JPEG/PNG/MP4 assets; no cookies or session are accepted."""
    now = int(time.time())
    if expires <= now or expires > now + _MAX_TTL_SECONDS:
        raise HTTPException(status_code=403, detail="media_url_expired")
    expected = hmac.new(_secret(), _message(str(asset_id), expires), hashlib.sha256).hexdigest()
    if not hmac.compare_digest(signature, expected):
        raise HTTPException(status_code=403, detail="invalid_media_signature")

    settings = get_settings()
    repository = MediaAssetRepository(settings.database_path)
    with repository.tasks._connection() as connection:
        row = connection.execute(
            "SELECT * FROM content_assets WHERE asset_id = ?",
            (str(asset_id),),
        ).fetchone()
    if row is None or row["media_type"] not in _ALLOWED_TYPES:
        raise HTTPException(status_code=404, detail="media_asset_not_found")
    record = repository._record(row)
    media_type = str(record["media_type"])
    path = repository.file_path(str(record["storage_key"]))
    size = path.stat().st_size if path.is_file() else 0
    max_size = MAX_OUTPUT_BYTES if media_type == "video/mp4" else MAX_UPLOAD_BYTES
    if size != int(record["file_size"]) or not 1 <= size <= max_size:
        raise HTTPException(status_code=404, detail="media_asset_unavailable")
    with path.open("rb") as media_file:
        header = media_file.read(12)
    valid_signature = (
        header.startswith(_MEDIA_SIGNATURES[media_type])
        if media_type in _MEDIA_SIGNATURES
        else len(header) >= 8 and header[4:8] == b"ftyp"
    )
    if not valid_signature:
        raise HTTPException(status_code=404, detail="media_asset_type_mismatch")
    return FileResponse(
        path,
        media_type=media_type,
        headers={
            "X-Content-Type-Options": "nosniff",
            "Cache-Control": "private, no-store",
            "Content-Disposition": "inline",
        },
    )
