"""Authenticated bounded media uploads and sandboxed local FFmpeg transcode."""
from __future__ import annotations

import re
import shutil
import sqlite3
import subprocess
import threading
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Request, Response
from fastapi.responses import FileResponse

from mrhub.api.dependencies import require_user
from mrhub.config import get_settings
from mrhub.media.repository import MAX_OUTPUT_BYTES, MAX_UPLOAD_BYTES, MediaAssetRepository
from mrhub.security.audit import AuditLogger
from mrhub.security.auth import AuthenticatedUser

router = APIRouter(prefix="/content/assets", tags=["content-media"], dependencies=[Depends(require_user)])
_FFMPEG_SEMAPHORE = threading.BoundedSemaphore(1)
_ALLOWED_TYPES = {
    "video/mp4",
    "video/quicktime",
    "image/jpeg",
    "image/png",
    "image/webp",
    "audio/mpeg",
    "audio/wav",
}


def _repository() -> MediaAssetRepository:
    return MediaAssetRepository(get_settings().database_path)


def _public_asset(record: dict[str, object]) -> dict[str, object]:
    return {key: value for key, value in record.items() if key != "storage_key"}


def _audit(
    repository: MediaAssetRepository,
    user: AuthenticatedUser,
    event: str,
    asset_id: str,
    reason: str,
    outcome: str = "success",
) -> None:
    AuditLogger(repository.tasks).record(
        event_type=event,
        outcome=outcome,
        subject_type="content_asset",
        subject_id=asset_id,
        actor_type="user",
        actor_id=user.user_id,
        metadata={"reason_code": reason},
    )


def _safe_filename(value: str) -> str:
    basename = value.replace("\\", "/").split("/")[-1]
    cleaned = re.sub(r"[\x00-\x1f\x7f]", "", basename).strip()
    if cleaned in {"", ".", ".."} or len(cleaned) > 255:
        raise HTTPException(status_code=422, detail="Invalid media filename")
    return cleaned


def _signature_matches(media_type: str, content: bytes) -> bool:
    if media_type == "image/jpeg":
        return content.startswith(b"\xff\xd8\xff")
    if media_type == "image/png":
        return content.startswith(b"\x89PNG\r\n\x1a\n")
    if media_type == "image/webp":
        return len(content) >= 12 and content[:4] == b"RIFF" and content[8:12] == b"WEBP"
    if media_type in {"video/mp4", "video/quicktime"}:
        return len(content) >= 12 and content[4:8] == b"ftyp"
    if media_type == "audio/wav":
        return len(content) >= 12 and content[:4] == b"RIFF" and content[8:12] == b"WAVE"
    if media_type == "audio/mpeg":
        return content.startswith(b"ID3") or (
            len(content) >= 2 and content[0] == 0xFF and (content[1] & 0xE0) == 0xE0
        )
    return False


@router.post("", status_code=201)
async def upload_asset(
    request: Request,
    user: Annotated[AuthenticatedUser, Depends(require_user)],
    x_file_name: Annotated[str, Header(alias="X-File-Name")],
) -> dict[str, object]:
    media_type = request.headers.get("content-type", "").split(";", maxsplit=1)[0].strip().lower()
    if media_type not in _ALLOWED_TYPES:
        raise HTTPException(status_code=415, detail="Unsupported media type")
    content_length = request.headers.get("content-length")
    if content_length:
        try:
            if int(content_length) > MAX_UPLOAD_BYTES:
                raise HTTPException(status_code=413, detail="Media upload exceeds the 25 MB limit")
        except ValueError as exc:
            raise HTTPException(status_code=400, detail="Invalid Content-Length") from exc

    chunks: list[bytes] = []
    size = 0
    async for chunk in request.stream():
        size += len(chunk)
        if size > MAX_UPLOAD_BYTES:
            raise HTTPException(status_code=413, detail="Media upload exceeds the 25 MB limit")
        chunks.append(chunk)
    data = b"".join(chunks)
    if not _signature_matches(media_type, data):
        raise HTTPException(status_code=415, detail="Media signature does not match Content-Type")
    filename = _safe_filename(x_file_name)
    repository = _repository()
    try:
        record = await __import__("asyncio").to_thread(
            repository.store_upload, user.user_id, filename, media_type, data
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail="Invalid media upload") from exc
    _audit(repository, user, "content.asset_uploaded", str(record["asset_id"]), "asset_uploaded")
    return _public_asset(record)


@router.get("")
def list_assets(
    user: Annotated[AuthenticatedUser, Depends(require_user)],
    limit: int = Query(default=50, ge=1, le=100),
) -> dict[str, object]:
    assets = _repository().list_assets(user.user_id, limit)
    return {"assets": [_public_asset(asset) for asset in assets], "count": len(assets)}


@router.get("/{asset_id}/file")
def download_asset(
    asset_id: UUID,
    user: Annotated[AuthenticatedUser, Depends(require_user)],
) -> FileResponse:
    repository = _repository()
    record = repository.get(user.user_id, asset_id)
    if record is None:
        raise HTTPException(status_code=404, detail="Media asset not found")
    path = repository.file_path(str(record["storage_key"]))
    if not path.is_file():
        raise HTTPException(status_code=404, detail="Media file is missing")
    return FileResponse(
        path,
        media_type=str(record["media_type"]),
        filename=str(record["original_filename"]),
        headers={"X-Content-Type-Options": "nosniff", "Cache-Control": "no-store"},
    )


@router.post("/{asset_id}/transcode")
def transcode_video(
    asset_id: UUID,
    user: Annotated[AuthenticatedUser, Depends(require_user)],
) -> dict[str, object]:
    repository = _repository()
    binary = shutil.which("ffmpeg")
    if binary is None:
        raise HTTPException(status_code=503, detail="ffmpeg_unavailable")
    existing = repository.get(user.user_id, asset_id)
    if existing is None:
        raise HTTPException(status_code=404, detail="Media asset not found")
    if existing["source_asset_id"] is not None or existing["media_type"] not in {
        "video/mp4",
        "video/quicktime",
    }:
        raise HTTPException(status_code=422, detail="Only original MP4/QuickTime video assets can be transcoded")
    input_path = repository.file_path(str(existing["storage_key"]))
    if not input_path.is_file():
        raise HTTPException(status_code=404, detail="Media file is missing")
    if not _FFMPEG_SEMAPHORE.acquire(blocking=False):
        raise HTTPException(status_code=429, detail="ffmpeg_busy")
    output_asset_id, output_key, output_path = repository.new_output_target()
    started = repository.begin_processing(user.user_id, asset_id)
    if started is None:
        _FFMPEG_SEMAPHORE.release()
        raise HTTPException(status_code=409, detail="Media asset is already processed or processing")
    command = [
        binary,
        "-nostdin",
        "-hide_banner",
        "-loglevel",
        "error",
        "-protocol_whitelist",
        "file,pipe",
        "-y",
        "-i",
        str(input_path),
        "-t",
        "60",
        "-vf",
        "scale='min(1280,iw)':-2",
        "-map",
        "0:v:0",
        "-map",
        "0:a:0?",
        "-c:v",
        "libx264",
        "-preset",
        "veryfast",
        "-crf",
        "23",
        "-c:a",
        "aac",
        "-b:a",
        "128k",
        "-movflags",
        "+faststart",
        "-fs",
        str(MAX_OUTPUT_BYTES),
        "-f",
        "mp4",
        str(output_path),
    ]
    environment = {
        "PATH": str(__import__("pathlib").Path(binary).parent),
        "HOME": str(repository.storage_root),
        "TMPDIR": str(repository.storage_root),
        "LANG": "C",
        "LC_ALL": "C",
    }
    try:
        try:
            result = subprocess.run(
                command,
                shell=False,
                check=False,
                capture_output=True,
                timeout=120,
                env=environment,
            )
        except subprocess.TimeoutExpired as exc:
            output_path.unlink(missing_ok=True)
            repository.fail_processing(user.user_id, asset_id, "ffmpeg_timeout")
            _audit(repository, user, "content.asset_transcode_failed", str(asset_id), "ffmpeg_timeout", "failure")
            raise HTTPException(status_code=504, detail="ffmpeg_timeout") from exc
        except OSError as exc:
            output_path.unlink(missing_ok=True)
            repository.fail_processing(user.user_id, asset_id, "ffmpeg_unavailable")
            _audit(repository, user, "content.asset_transcode_failed", str(asset_id), "ffmpeg_unavailable", "failure")
            raise HTTPException(status_code=503, detail="ffmpeg_unavailable") from exc

        if result.returncode != 0:
            output_path.unlink(missing_ok=True)
            repository.fail_processing(user.user_id, asset_id, "ffmpeg_failed")
            _audit(repository, user, "content.asset_transcode_failed", str(asset_id), "ffmpeg_failed", "failure")
            raise HTTPException(status_code=422, detail="ffmpeg_failed")
        if not output_path.is_file() or output_path.stat().st_size <= 0 or output_path.stat().st_size > MAX_OUTPUT_BYTES:
            output_path.unlink(missing_ok=True)
            repository.fail_processing(user.user_id, asset_id, "invalid_output")
            _audit(repository, user, "content.asset_transcode_failed", str(asset_id), "invalid_output", "failure")
            raise HTTPException(status_code=422, detail="invalid_ffmpeg_output")

        try:
            output = repository.register_transcoded_output(
                user.user_id,
                asset_id,
                output_asset_id,
                output_key,
                output_path,
                f"{str(existing['original_filename']).rsplit('.', maxsplit=1)[0]}-720p.mp4",
            )
        except Exception as exc:
            output_path.unlink(missing_ok=True)
            repository.fail_processing(user.user_id, asset_id, "output_registration_failed")
            _audit(repository, user, "content.asset_transcode_failed", str(asset_id), "output_registration_failed", "failure")
            raise HTTPException(status_code=500, detail="output_registration_failed") from exc
        _audit(repository, user, "content.asset_transcoded", str(output["asset_id"]), "video_mp4_720p")
        return {"status": "succeeded", "asset": _public_asset(output)}
    finally:
        _FFMPEG_SEMAPHORE.release()


@router.get("/{asset_id}")
def get_asset(
    asset_id: UUID,
    user: Annotated[AuthenticatedUser, Depends(require_user)],
) -> dict[str, object]:
    record = _repository().get(user.user_id, asset_id)
    if record is None:
        raise HTTPException(status_code=404, detail="Media asset not found")
    return _public_asset(record)


@router.delete("/{asset_id}", status_code=204)
def delete_asset(
    asset_id: UUID,
    user: Annotated[AuthenticatedUser, Depends(require_user)],
) -> Response:
    repository = _repository()
    try:
        keys = repository.delete(user.user_id, asset_id)
    except sqlite3.IntegrityError as exc:
        raise HTTPException(
            status_code=409,
            detail="Media asset is attached to a content draft",
        ) from exc
    if keys is None:
        raise HTTPException(status_code=404, detail="Media asset not found")
    cleanup_failed = False
    for key in keys:
        try:
            repository.file_path(key).unlink(missing_ok=True)
        except OSError:
            cleanup_failed = True
    _audit(
        repository,
        user,
        "content.asset_deleted",
        str(asset_id),
        "asset_deleted_cleanup_pending" if cleanup_failed else "asset_deleted",
        "failure" if cleanup_failed else "success",
    )
    return Response(status_code=204)
