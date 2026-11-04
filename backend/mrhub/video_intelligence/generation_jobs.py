"""Durable owner-scoped persistence for approval-gated video-generation requests.

The repository stores encrypted inputs and fenced lifecycle state. Provider calls
are performed only by the separately registered, lease-owned worker handler.
"""
from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path
from uuid import UUID, uuid4

from mrhub.domain.tasks import RiskClass, TaskRecord, TaskStatus
from mrhub.infrastructure.database import TaskRepository
from mrhub.jobs.leases import WorkerLease
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

    def enqueue(self, owner_user_id: str, generation_id: UUID) -> dict[str, object] | None:
        """Atomically bind a prepared generation to one durable worker task."""
        now = self._now()
        with self.tasks._connection() as connection:
            connection.execute("BEGIN IMMEDIATE")
            job = connection.execute(
                """SELECT status, provider, model FROM video_generation_jobs
                   WHERE generation_id = ? AND owner_user_id = ?""",
                (str(generation_id), owner_user_id),
            ).fetchone()
            if job is None:
                return None
            existing = connection.execute(
                """SELECT task_id FROM video_generation_task_links
                   WHERE generation_id = ? AND owner_user_id = ?""",
                (str(generation_id), owner_user_id),
            ).fetchone()
            if existing is not None:
                return {"generation_id": str(generation_id), "task_id": existing["task_id"], "status": str(job["status"]), "created": False}
            if job["status"] != "prepared":
                raise ValueError("Only prepared generation jobs can be enqueued")
            task = TaskRecord(
                task_type="video.generation",
                risk_class=RiskClass.HIGH,
                description=(
                    f"Owner-requested generation {generation_id} "
                    f"via {job['provider']}/{job['model']}"
                ),
            )
            connection.execute(
                """INSERT INTO tasks (
                    task_id, task_type, status, risk_class, created_at, updated_at, description
                ) VALUES (?, ?, 'waiting_approval', ?, ?, ?, ?)""",
                (str(task.task_id), task.task_type, task.risk_class.value,
                 task.created_at.isoformat(), task.updated_at.isoformat(), task.description),
            )
            connection.execute(
                """INSERT INTO video_generation_task_links (
                    generation_id, owner_user_id, task_id, created_at
                ) VALUES (?, ?, ?, ?)""",
                (str(generation_id), owner_user_id, str(task.task_id), now),
            )
            connection.execute(
                """UPDATE video_generation_jobs SET status = 'queued', updated_at = ?
                   WHERE generation_id = ? AND owner_user_id = ? AND status = 'prepared'""",
                (now, str(generation_id), owner_user_id),
            )
        return {"generation_id": str(generation_id), "task_id": str(task.task_id), "status": "queued", "created": True}

    def load_for_worker(self, task_id: UUID) -> dict[str, object] | None:
        """Decrypt one queued job only through its linked durable task."""
        with self.tasks._connection() as connection:
            row = connection.execute(
                """SELECT l.owner_user_id, l.generation_id, j.provider, j.model,
                          j.status, j.provider_job_id, j.progress_percent,
                          p.envelope_version, p.nonce_b64, p.ciphertext_b64
                   FROM video_generation_task_links AS l
                   JOIN video_generation_jobs AS j
                     ON j.generation_id = l.generation_id
                    AND j.owner_user_id = l.owner_user_id
                   JOIN video_generation_payloads AS p
                     ON p.generation_id = j.generation_id
                    AND p.owner_user_id = j.owner_user_id
                   WHERE l.task_id = ?""",
                (str(task_id),),
            ).fetchone()
        if row is None:
            return None
        job_status = str(row["status"])
        if job_status not in {"queued", "unknown_outcome", "running"}:
            raise ValueError("Generation job is not eligible for worker execution")
        if job_status == "running" and not row["provider_job_id"]:
            raise ValueError("Running generation job is missing its provider reference")
        generation_id = str(row["generation_id"])
        owner_user_id = str(row["owner_user_id"])
        payload = decrypt_payload(
            EncryptedPayload(
                version=int(row["envelope_version"]),
                nonce_b64=str(row["nonce_b64"]),
                ciphertext_b64=str(row["ciphertext_b64"]),
            ),
            workflow_id=generation_id,
            task_id=generation_id,
            owner_user_id=owner_user_id,
            key=load_payload_key(),
        )
        return {
            "owner_user_id": owner_user_id,
            "generation_id": generation_id,
            "provider": str(row["provider"]),
            "model": str(row["model"]),
            "status": job_status,
            "provider_job_id": row["provider_job_id"],
            "progress_percent": row["progress_percent"],
            "request": payload,
        }

    def enqueue_reconciliation(
        self, owner_user_id: str, generation_id: UUID
    ) -> dict[str, object] | None:
        """Requeue the original approved task for read-only provider reconciliation."""
        now = self._now()
        with self.tasks._connection() as connection:
            connection.execute("BEGIN IMMEDIATE")
            row = connection.execute(
                """SELECT j.status AS generation_status, j.provider_job_id,
                          l.task_id, t.status AS task_status
                   FROM video_generation_jobs AS j
                   JOIN video_generation_task_links AS l
                     ON l.generation_id = j.generation_id
                    AND l.owner_user_id = j.owner_user_id
                   JOIN tasks AS t ON t.task_id = l.task_id
                   WHERE j.generation_id = ? AND j.owner_user_id = ?""",
                (str(generation_id), owner_user_id),
            ).fetchone()
            if row is None:
                return None
            generation_status = str(row["generation_status"])
            if generation_status not in {"unknown_outcome", "running"}:
                raise ValueError("Only ambiguous or running generation jobs can be reconciled")
            if generation_status == "running" and not row["provider_job_id"]:
                raise ValueError("Running generation job is missing its provider reference")
            task_status = str(row["task_status"])
            task_id = str(row["task_id"])
            if task_status in {TaskStatus.QUEUED.value, TaskStatus.RUNNING.value}:
                return {
                    "generation_id": str(generation_id),
                    "task_id": task_id,
                    "status": task_status,
                    "created": False,
                }
            if task_status not in {TaskStatus.FAILED.value, TaskStatus.SUCCEEDED.value}:
                raise ValueError("Generation task is not eligible for reconciliation")
            cursor = connection.execute(
                """UPDATE tasks SET status = ?, updated_at = ?
                   WHERE task_id = ? AND status = ?""",
                (TaskStatus.QUEUED.value, now, task_id, task_status),
            )
            if cursor.rowcount != 1:
                raise ValueError("Generation task changed before reconciliation was queued")
            connection.execute(
                """UPDATE worker_executions
                   SET attempt_count = 0, result_json = NULL, error_code = NULL,
                       started_at = NULL, finished_at = NULL, recovered_at = ?,
                       next_attempt_at = NULL, lease_owner = NULL,
                       lease_expires_at = NULL, heartbeat_at = NULL
                   WHERE task_id = ?""",
                (now, task_id),
            )
        return {
            "generation_id": str(generation_id),
            "task_id": task_id,
            "status": TaskStatus.QUEUED.value,
            "created": True,
        }

    def transition_under_lease(
        self,
        owner_user_id: str,
        generation_id: UUID,
        target: str,
        *,
        lease: WorkerLease,
        provider_job_id: str | None = None,
        progress_percent: int | None = None,
        error_code: str | None = None,
    ) -> dict[str, object] | None:
        """Change a generation state only while its task fencing token is current."""
        if lease.task_id == "" or not lease.owner or lease.fencing_token < 1:
            raise ValueError("A valid worker lease is required")
        now = self._now()
        allowed = {
            "queued": {"submitting", "failed"},
            "submitting": {"running", "unknown_outcome", "failed"},
            "unknown_outcome": {"running", "unknown_outcome", "failed"},
            "running": {"running", "unknown_outcome", "failed"},
        }
        if progress_percent is not None and not 0 <= progress_percent <= 100:
            raise ValueError("Generation progress must be between 0 and 100")
        if provider_job_id is not None and (
            not provider_job_id or len(provider_job_id) > 255
        ):
            raise ValueError("Provider job identifier is invalid")
        if error_code is not None and (not error_code or len(error_code) > 80):
            raise ValueError("Generation error code is invalid")
        with self.tasks._connection() as connection:
            connection.execute("BEGIN IMMEDIATE")
            link = connection.execute(
                """SELECT task_id FROM video_generation_task_links
                   WHERE generation_id = ? AND owner_user_id = ?""",
                (str(generation_id), owner_user_id),
            ).fetchone()
            if link is None or link["task_id"] != lease.task_id:
                raise ValueError("Worker lease does not own this generation task")
            current = connection.execute(
                """SELECT status FROM video_generation_jobs
                   WHERE generation_id = ? AND owner_user_id = ?""",
                (str(generation_id), owner_user_id),
            ).fetchone()
            if current is None:
                return None
            if target not in allowed.get(str(current["status"]), set()):
                raise ValueError("Invalid fenced generation state transition")
            cursor = connection.execute(
                """UPDATE video_generation_jobs SET status = ?,
                       provider_job_id = COALESCE(?, provider_job_id),
                       progress_percent = COALESCE(?, progress_percent),
                       error_code = ?, updated_at = ?
                   WHERE generation_id = ? AND owner_user_id = ? AND status = ?
                     AND EXISTS (
                       SELECT 1 FROM worker_executions e
                       WHERE e.task_id = ? AND e.lease_owner = ?
                         AND e.execution_token = ? AND e.lease_expires_at > ?
                     )""",
                (target, provider_job_id, progress_percent, error_code, now,
                 str(generation_id), owner_user_id, current["status"],
                 lease.task_id, lease.owner, lease.fencing_token, now),
            )
            if cursor.rowcount != 1:
                raise ValueError("Worker lease lost before generation state update")
            if target == "failed":
                connection.execute(
                    """DELETE FROM video_generation_payloads
                       WHERE generation_id = ? AND owner_user_id = ?""",
                    (str(generation_id), owner_user_id),
                )
        return self.get(owner_user_id, generation_id)


    def fail_unapproved_task(self, task_id: UUID) -> bool:
        """Fail a queued generation task that lacks a valid owner approval."""
        now = self._now()
        with self.tasks._connection() as connection:
            connection.execute("BEGIN IMMEDIATE")
            row = connection.execute(
                """SELECT l.generation_id, l.owner_user_id
                   FROM video_generation_task_links AS l
                   WHERE l.task_id = ?""",
                (str(task_id),),
            ).fetchone()
            if row is None:
                return False
            cursor = connection.execute(
                """UPDATE video_generation_jobs
                   SET status = 'failed', error_code = 'approval_missing_or_stale',
                       updated_at = ?
                   WHERE generation_id = ? AND owner_user_id = ? AND status = 'queued'""",
                (now, row["generation_id"], row["owner_user_id"]),
            )
            if cursor.rowcount == 1:
                connection.execute(
                    """DELETE FROM video_generation_payloads
                       WHERE generation_id = ? AND owner_user_id = ?""",
                    (row["generation_id"], row["owner_user_id"]),
                )
        return cursor.rowcount == 1

    def reject_pending_task(self, task_id: UUID, owner_user_id: str) -> bool:
        """Purge an owner-rejected generation payload before any provider dispatch."""
        now = self._now()
        with self.tasks._connection() as connection:
            connection.execute("BEGIN IMMEDIATE")
            link = connection.execute(
                """SELECT generation_id FROM video_generation_task_links
                   WHERE task_id = ? AND owner_user_id = ?""",
                (str(task_id), owner_user_id),
            ).fetchone()
            if link is None:
                return False
            generation_id = str(link["generation_id"])
            cursor = connection.execute(
                """UPDATE video_generation_jobs
                   SET status = 'failed', error_code = 'owner_rejected_before_submission',
                       updated_at = ?
                   WHERE generation_id = ? AND owner_user_id = ? AND status = 'queued'""",
                (now, generation_id, owner_user_id),
            )
            if cursor.rowcount == 1:
                connection.execute(
                    """DELETE FROM video_generation_payloads
                       WHERE generation_id = ? AND owner_user_id = ?""",
                    (generation_id, owner_user_id),
                )
        return cursor.rowcount == 1

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
        *,
        lease: WorkerLease | None = None,
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
            if lease is not None:
                link = connection.execute(
                    """SELECT task_id FROM video_generation_task_links
                       WHERE generation_id = ? AND owner_user_id = ?""",
                    (str(generation_id), owner_user_id),
                ).fetchone()
                current_lease = connection.execute(
                    """SELECT 1 FROM worker_executions
                       WHERE task_id = ? AND lease_owner = ? AND execution_token = ?
                         AND lease_expires_at > ?""",
                    (lease.task_id, lease.owner, lease.fencing_token, now),
                ).fetchone()
                if (
                    link is None
                    or link["task_id"] != lease.task_id
                    or current_lease is None
                ):
                    raise ValueError("Worker lease lost before generation output registration")
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
