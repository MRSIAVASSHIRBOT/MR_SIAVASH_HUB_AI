"""Durable owner-scoped persistence for explicit video-generation requests.

Jobs remain prepared until a separately configured worker/provider handoff is
available. This repository never invokes a provider or starts background work.
"""
from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path
from uuid import UUID, uuid4

from mrhub.infrastructure.database import TaskRepository
from mrhub.jobs.payload_envelope import (
    EncryptedPayload,
    decrypt_payload,
    encrypt_payload,
    load_payload_key,
)
from mrhub.video_intelligence.generation import (
    GenerationStatus,
    VideoGenerationRequest,
    VideoGenerationResult,
)


class VideoGenerationConflict(ValueError):
    """Raised when an idempotency key is reused for a different request."""


class VideoGenerationJobRepository:
    """Persist encrypted generation inputs and owner-scoped job metadata."""

    def __init__(self, database_path: Path) -> None:
        self.database_path = database_path
        self.tasks = TaskRepository(database_path)
        self.tasks.initialize()

    @staticmethod
    def _now() -> str:
        return datetime.now(UTC).isoformat()

    def submit(
        self,
        owner_user_id: str,
        source_analysis_id: UUID,
        provider: str,
        model: str,
        request: VideoGenerationRequest,
    ) -> tuple[dict[str, object], bool]:
        if not owner_user_id or len(owner_user_id) > 200:
            raise ValueError("Generation owner identifier is invalid")
        provider = provider.strip()
        model = model.strip()
        if not provider or len(provider) > 80 or not model or len(model) > 120:
            raise ValueError("Generation provider selection is invalid")

        request_data = request.model_dump(mode="json")
        idempotency_key = str(request_data.pop("idempotency_key")).strip()
        if not idempotency_key or len(idempotency_key) > 255:
            raise ValueError("Idempotency-Key must contain 1 to 255 characters")
        canonical = json.dumps(
            {
                "source_analysis_id": str(source_analysis_id),
                "provider": provider,
                "model": model,
                "request": request_data,
            },
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
        digest = hashlib.sha256(canonical).hexdigest()
        generation_id = uuid4()
        now = self._now()
        envelope = encrypt_payload(
            request_data,
            workflow_id=str(generation_id),
            task_id=str(generation_id),
            owner_user_id=owner_user_id,
            key=load_payload_key(),
        )

        with self.tasks._connection() as connection:
            connection.execute("BEGIN IMMEDIATE")
            source = connection.execute(
                """SELECT 1 FROM video_analysis_runs
                   WHERE analysis_id = ? AND owner_user_id = ? AND status = 'completed'""",
                (str(source_analysis_id), owner_user_id),
            ).fetchone()
            if source is None:
                raise ValueError("A completed source analysis owned by this user is required")

            existing = connection.execute(
                """SELECT i.request_digest, j.generation_id, j.status, j.created_at
                   FROM video_generation_idempotency AS i
                   JOIN video_generation_jobs AS j ON j.generation_id = i.generation_id
                   WHERE i.owner_user_id = ? AND i.idempotency_key = ?""",
                (owner_user_id, idempotency_key),
            ).fetchone()
            if existing is not None:
                if existing["request_digest"] != digest:
                    raise VideoGenerationConflict(
                        "Idempotency key conflicts with an earlier generation request"
                    )
                return {
                    "generation_id": existing["generation_id"],
                    "status": existing["status"],
                    "created_at": existing["created_at"],
                    "provider": provider,
                    "model": model,
                    "execution": "not_started",
                }, False

            connection.execute(
                """INSERT INTO video_generation_jobs (
                    generation_id, owner_user_id, source_analysis_id, provider, model,
                    status, provider_job_id, progress_percent, output_asset_id,
                    output_bytes, output_duration_seconds, output_width, output_height,
                    error_code, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, 'prepared', NULL, NULL, NULL,
                          NULL, NULL, NULL, NULL, NULL, ?, ?)""",
                (
                    str(generation_id), owner_user_id, str(source_analysis_id),
                    provider, model, now, now,
                ),
            )
            connection.execute(
                """INSERT INTO video_generation_payloads (
                    generation_id, owner_user_id, envelope_version,
                    nonce_b64, ciphertext_b64, created_at
                ) VALUES (?, ?, ?, ?, ?, ?)""",
                (
                    str(generation_id), owner_user_id, envelope.version,
                    envelope.nonce_b64, envelope.ciphertext_b64, now,
                ),
            )
            connection.execute(
                """INSERT INTO video_generation_idempotency (
                    owner_user_id, idempotency_key, request_digest,
                    generation_id, created_at
                ) VALUES (?, ?, ?, ?, ?)""",
                (owner_user_id, idempotency_key, digest, str(generation_id), now),
            )

        return {
            "generation_id": str(generation_id),
            "status": "prepared",
            "created_at": now,
            "provider": provider,
            "model": model,
            "execution": "not_started",
        }, True

    def get(self, owner_user_id: str, generation_id: UUID) -> dict[str, object] | None:
        with self.tasks._connection() as connection:
            row = connection.execute(
                """SELECT generation_id, source_analysis_id, provider, model, status,
                          provider_job_id, progress_percent, output_asset_id,
                          output_bytes, output_duration_seconds, output_width,
                          output_height, error_code, created_at, updated_at
                   FROM video_generation_jobs
                   WHERE generation_id = ? AND owner_user_id = ?""",
                (str(generation_id), owner_user_id),
            ).fetchone()
        return dict(row) if row is not None else None

    def load_for_handoff(
        self, owner_user_id: str, generation_id: UUID
    ) -> dict[str, object] | None:
        with self.tasks._connection() as connection:
            row = connection.execute(
                """SELECT p.envelope_version, p.nonce_b64, p.ciphertext_b64,
                          j.source_analysis_id, j.provider, j.model, j.status
                   FROM video_generation_payloads AS p
                   JOIN video_generation_jobs AS j
                     ON j.generation_id = p.generation_id
                    AND j.owner_user_id = p.owner_user_id
                   WHERE p.generation_id = ? AND p.owner_user_id = ?""",
                (str(generation_id), owner_user_id),
            ).fetchone()
        if row is None:
            return None
        if row["status"] != "prepared":
            raise ValueError("Only prepared generation jobs can be handed off")
        payload = decrypt_payload(
            EncryptedPayload(
                version=int(row["envelope_version"]),
                nonce_b64=str(row["nonce_b64"]),
                ciphertext_b64=str(row["ciphertext_b64"]),
            ),
            workflow_id=str(generation_id),
            task_id=str(generation_id),
            owner_user_id=owner_user_id,
            key=load_payload_key(),
        )
        return {
            "generation_id": str(generation_id),
            "source_analysis_id": row["source_analysis_id"],
            "provider": row["provider"],
            "model": row["model"],
            "request": payload,
        }

    def load_for_reconciliation(
        self, owner_user_id: str, generation_id: UUID
    ) -> dict[str, object] | None:
        """Load the retained request only for an unknown provider outcome."""
        with self.tasks._connection() as connection:
            row = connection.execute(
                """SELECT p.envelope_version, p.nonce_b64, p.ciphertext_b64,
                          j.source_analysis_id, j.provider, j.model, j.status
                   FROM video_generation_payloads AS p
                   JOIN video_generation_jobs AS j
                     ON j.generation_id = p.generation_id
                    AND j.owner_user_id = p.owner_user_id
                   WHERE p.generation_id = ? AND p.owner_user_id = ?""",
                (str(generation_id), owner_user_id),
            ).fetchone()
        if row is None:
            return None
        if row["status"] != "unknown_outcome":
            raise ValueError("Only unknown-outcome jobs can be reconciled")
        payload = decrypt_payload(
            EncryptedPayload(
                version=int(row["envelope_version"]),
                nonce_b64=str(row["nonce_b64"]),
                ciphertext_b64=str(row["ciphertext_b64"]),
            ),
            workflow_id=str(generation_id),
            task_id=str(generation_id),
            owner_user_id=owner_user_id,
            key=load_payload_key(),
        )
        return {
            "generation_id": str(generation_id),
            "source_analysis_id": row["source_analysis_id"],
            "provider": row["provider"],
            "model": row["model"],
            "request": payload,
        }

    def complete_with_output(
        self,
        owner_user_id: str,
        generation_id: UUID,
        output_asset_id: str,
        storage_key: str,
        output_path: Path,
        output_filename: str,
        result: VideoGenerationResult,
    ) -> dict[str, object] | None:
        """Validate and atomically register a generated MP4 against its owner job."""
        from mrhub.media.repository import MAX_OUTPUT_BYTES, MediaAssetRepository
        from mrhub.video_intelligence.service import probe_video

        if result.status is not GenerationStatus.SUCCEEDED:
            raise ValueError("Only successful provider results can register media")
        if (
            not output_filename
            or output_filename in {".", ".."}
            or len(output_filename) > 255
            or Path(output_filename).name != output_filename
            or any(ord(character) < 32 for character in output_filename)
        ):
            raise ValueError("Generated output filename is invalid")
        media = MediaAssetRepository(self.database_path)
        expected_path = media.file_path(storage_key)
        if expected_path.resolve() != output_path.resolve():
            raise ValueError("Generated output path does not match its internal storage key")
        if not output_path.is_file():
            raise ValueError("Generated output file is missing")
        size = output_path.stat().st_size
        if size <= 0 or size > MAX_OUTPUT_BYTES or size != result.output_bytes:
            raise ValueError("Generated output size does not match bounded provider metadata")

        metadata = probe_video(output_path)
        if (
            metadata.metadata_status != "available"
            or metadata.duration_seconds is None
            or metadata.width is None
            or metadata.height is None
        ):
            raise ValueError("Generated output failed independent media validation")
        duration = float(metadata.duration_seconds)
        if (
            duration <= 0
            or duration > 60
            or metadata.width != result.width
            or metadata.height != result.height
            or abs(duration - float(result.duration_seconds)) > max(0.25, duration * 0.05)
        ):
            raise ValueError("Generated output metadata does not match provider result")

        digest = hashlib.sha256()
        with output_path.open("rb") as file:
            for chunk in iter(lambda: file.read(1024 * 1024), b""):
                digest.update(chunk)
        now = self._now()
        with self.tasks._connection() as connection:
            connection.execute("BEGIN IMMEDIATE")
            job = connection.execute(
                """SELECT provider, model, status, provider_job_id, output_asset_id
                   FROM video_generation_jobs
                   WHERE generation_id = ? AND owner_user_id = ?""",
                (str(generation_id), owner_user_id),
            ).fetchone()
            if job is None:
                return None
            if (
                job["provider"] != result.provider
                or job["model"] != result.model
                or job["provider_job_id"] != result.provider_job_id
            ):
                raise ValueError("Provider result does not match the selected generation job")
            if job["status"] == "succeeded":
                if job["output_asset_id"] != output_asset_id:
                    raise ValueError("Generation job already has a different output asset")
                existing = connection.execute(
                    """SELECT * FROM content_assets
                       WHERE asset_id = ? AND owner_user_id = ?""",
                    (output_asset_id, owner_user_id),
                ).fetchone()
                return MediaAssetRepository._record(existing) if existing is not None else None
            if job["status"] not in {"submitting", "running", "unknown_outcome"}:
                raise ValueError("Generation job is not eligible for output registration")

            connection.execute(
                """INSERT INTO content_assets (
                    asset_id, owner_user_id, source_asset_id, original_filename,
                    media_type, storage_key, file_size, content_hash,
                    processing_status, processing_profile, error_code, created_at, updated_at
                ) VALUES (?, ?, NULL, ?, 'video/mp4', ?, ?, ?, 'processed',
                          'video_ai_generated', NULL, ?, ?)""",
                (
                    output_asset_id, owner_user_id, output_filename, storage_key,
                    size, digest.hexdigest(), now, now,
                ),
            )
            connection.execute(
                """UPDATE video_generation_jobs
                   SET status = 'succeeded', output_asset_id = ?, output_bytes = ?,
                       output_duration_seconds = ?, output_width = ?, output_height = ?,
                       progress_percent = 100, error_code = NULL, updated_at = ?
                   WHERE generation_id = ? AND owner_user_id = ?""",
                (
                    output_asset_id, size, duration, metadata.width, metadata.height,
                    now, str(generation_id), owner_user_id,
                ),
            )
            connection.execute(
                """DELETE FROM video_generation_payloads
                   WHERE generation_id = ? AND owner_user_id = ?""",
                (str(generation_id), owner_user_id),
            )
            asset = connection.execute(
                """SELECT * FROM content_assets
                   WHERE asset_id = ? AND owner_user_id = ?""",
                (output_asset_id, owner_user_id),
            ).fetchone()
        return MediaAssetRepository._record(asset) if asset is not None else None

    def transition(
        self,
        owner_user_id: str,
        generation_id: UUID,
        target: str,
        *,
        provider_job_id: str | None = None,
        progress_percent: int | None = None,
        error_code: str | None = None,
    ) -> dict[str, object] | None:
        allowed = {
            "prepared": {"queued", "cancelled"},
            "queued": {"submitting", "cancelled"},
            "submitting": {"running", "failed", "unknown_outcome", "cancelled"},
            "running": {"failed", "unknown_outcome", "cancelled"},
            "unknown_outcome": {"running", "failed", "cancelled"},
            "succeeded": set(),
            "failed": set(),
            "cancelled": set(),
        }
        if target not in allowed:
            raise ValueError("Invalid video-generation status")
        if progress_percent is not None and not 0 <= progress_percent <= 100:
            raise ValueError("Generation progress must be between 0 and 100")
        if provider_job_id is not None and (not provider_job_id or len(provider_job_id) > 255):
            raise ValueError("Provider job identifier is invalid")
        if error_code is not None and (not error_code or len(error_code) > 80):
            raise ValueError("Generation error code is invalid")

        now = self._now()
        with self.tasks._connection() as connection:
            connection.execute("BEGIN IMMEDIATE")
            row = connection.execute(
                """SELECT status FROM video_generation_jobs
                   WHERE generation_id = ? AND owner_user_id = ?""",
                (str(generation_id), owner_user_id),
            ).fetchone()
            if row is None:
                return None
            current = str(row["status"])
            if target not in allowed[current]:
                raise ValueError(f"Invalid generation transition: {current} -> {target}")
            if target in {"succeeded", "failed", "cancelled"}:
                connection.execute(
                    """DELETE FROM video_generation_payloads
                       WHERE generation_id = ? AND owner_user_id = ?""",
                    (str(generation_id), owner_user_id),
                )
            connection.execute(
                """UPDATE video_generation_jobs
                   SET status = ?, provider_job_id = COALESCE(?, provider_job_id),
                       progress_percent = COALESCE(?, progress_percent),
                       error_code = ?, updated_at = ?
                   WHERE generation_id = ? AND owner_user_id = ? AND status = ?""",
                (
                    target, provider_job_id, progress_percent, error_code, now,
                    str(generation_id), owner_user_id, current,
                ),
            )
        return self.get(owner_user_id, generation_id)
