"""Durable owner-scoped persistence for approval-gated video-generation requests.

The repository stores encrypted inputs and fenced lifecycle state. Provider calls
are performed only by the separately registered, lease-owned worker handler.
"""
from __future__ import annotations

import hashlib
import json
import re
from datetime import UTC, datetime, timedelta
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
from mrhub.security.audit import AuditLogger
from mrhub.video_intelligence.generation import (
    GenerationStatus,
    VideoGenerationRequest,
    VideoGenerationResult,
)


class VideoGenerationConflict(ValueError):
    """Raised when an idempotency key is reused for a different request."""


class VideoGenerationReconciliationCooldown(ValueError):
    """Raised when an explicit provider reconciliation is still cooling down."""

    def __init__(self, retry_after_seconds: int) -> None:
        self.retry_after_seconds = max(1, retry_after_seconds)
        super().__init__("Video generation reconciliation is temporarily rate limited")


class VideoGenerationCancellationConflict(ValueError):
    """Raised when a generation is no longer safely pending for cancellation."""


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
        """Load queued work or reconciliation-only state through its linked task."""
        with self.tasks._connection() as connection:
            row = connection.execute(
                """SELECT l.owner_user_id, l.generation_id, j.provider, j.model,
                          j.status, j.provider_job_id, j.progress_percent,
                          j.cancellation_requested_at,
                          p.envelope_version, p.nonce_b64, p.ciphertext_b64
                   FROM video_generation_task_links AS l
                   JOIN video_generation_jobs AS j
                     ON j.generation_id = l.generation_id
                    AND j.owner_user_id = l.owner_user_id
                   LEFT JOIN video_generation_payloads AS p
                     ON p.generation_id = j.generation_id
                    AND p.owner_user_id = j.owner_user_id
                   WHERE l.task_id = ?""",
                (str(task_id),),
            ).fetchone()
        if row is None:
            return None
        job_status = str(row["status"])
        if job_status not in {"queued", "submitting", "unknown_outcome", "running"}:
            raise ValueError("Generation job is not eligible for worker execution")
        if job_status == "running" and not row["provider_job_id"]:
            raise ValueError("Running generation job is missing its provider reference")
        generation_id = str(row["generation_id"])
        owner_user_id = str(row["owner_user_id"])
        payload = None
        if job_status == "queued":
            if any(
                row[field] is None
                for field in ("envelope_version", "nonce_b64", "ciphertext_b64")
            ):
                raise ValueError("Queued generation request payload is unavailable")
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
        loaded = {
            "owner_user_id": owner_user_id,
            "generation_id": generation_id,
            "provider": str(row["provider"]),
            "model": str(row["model"]),
            "status": job_status,
            "provider_job_id": row["provider_job_id"],
            "progress_percent": row["progress_percent"],
            "cancellation_requested": row["cancellation_requested_at"] is not None,
        }
        if payload is not None:
            loaded["request"] = payload
        return loaded

    def enqueue_reconciliation(
        self, owner_user_id: str, generation_id: UUID
    ) -> dict[str, object] | None:
        """Requeue the original task for read-only reconciliation of an ambiguous submit."""
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
            if generation_status not in {"submitting", "unknown_outcome", "running"}:
                raise ValueError("Only submitting, ambiguous, or running generation jobs can be reconciled")
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
            if task_status not in {
                TaskStatus.FAILED.value,
                TaskStatus.SUCCEEDED.value,
                TaskStatus.CANCELLED.value,
            }:
                raise ValueError("Generation task is not eligible for reconciliation")

            limit = connection.execute(
                """SELECT attempt_count, next_allowed_at
                   FROM video_generation_reconciliation_limits
                   WHERE generation_id = ? AND owner_user_id = ?""",
                (str(generation_id), owner_user_id),
            ).fetchone()
            attempt_count = int(limit["attempt_count"]) if limit is not None else 0
            if limit is not None and limit["next_allowed_at"]:
                next_allowed_at = datetime.fromisoformat(str(limit["next_allowed_at"]))
                current_time = datetime.fromisoformat(now)
                remaining = (next_allowed_at - current_time).total_seconds()
                if remaining > 0:
                    raise VideoGenerationReconciliationCooldown(int(remaining + 0.999))

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
            next_attempt_count = attempt_count + 1
            cooldown_seconds = min(30 * (2 ** min(attempt_count, 5)), 900)
            next_allowed_at = (
                datetime.fromisoformat(now) + timedelta(seconds=cooldown_seconds)
            ).isoformat()
            connection.execute(
                """INSERT INTO video_generation_reconciliation_limits (
                       generation_id, owner_user_id, attempt_count,
                       last_attempt_at, next_allowed_at
                   ) VALUES (?, ?, ?, ?, ?)
                   ON CONFLICT(generation_id, owner_user_id) DO UPDATE SET
                       attempt_count = excluded.attempt_count,
                       last_attempt_at = excluded.last_attempt_at,
                       next_allowed_at = excluded.next_allowed_at""",
                (
                    str(generation_id), owner_user_id, next_attempt_count,
                    now, next_allowed_at,
                ),
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
            "queued": {"submitting", "failed", "cancelled"},
            "submitting": {"running", "unknown_outcome", "failed", "cancelled"},
            "unknown_outcome": {"running", "unknown_outcome", "failed", "cancelled"},
            "running": {"running", "unknown_outcome", "failed", "cancelled"},
        }
        if progress_percent is not None and not 0 <= progress_percent <= 100:
            raise ValueError("Generation progress must be between 0 and 100")
        if provider_job_id is not None and (
            not provider_job_id or len(provider_job_id) > 255
        ):
            raise ValueError("Provider job identifier is invalid")
        if error_code is not None and not re.fullmatch(
            r"[a-z0-9][a-z0-9_.-]{0,79}", error_code
        ):
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
                       JOIN tasks t ON t.task_id = e.task_id
                       WHERE e.task_id = ? AND t.status = 'running'
                         AND e.lease_owner = ? AND e.execution_token = ?
                         AND e.lease_expires_at > ?
                     )""",
                (target, provider_job_id, progress_percent, error_code, now,
                 str(generation_id), owner_user_id, current["status"],
                 lease.task_id, lease.owner, lease.fencing_token, now),
            )
            if cursor.rowcount != 1:
                raise ValueError("Worker lease lost before generation state update")
            if target in {"failed", "cancelled"}:
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

    def cancel_pending(
        self, owner_user_id: str, generation_id: UUID
    ) -> dict[str, object] | None:
        """Cancel only before provider submission, atomically with task and payload cleanup.

        Active or ambiguous provider operations remain conflicts here; callers must
        use request_cancellation() so the lease-fenced Worker can confirm the provider
        outcome instead of changing local state optimistically.
        """
        now = self._now()
        with self.tasks._connection() as connection:
            connection.execute("BEGIN IMMEDIATE")
            row = connection.execute(
                """SELECT j.status AS generation_status, l.task_id,
                          t.status AS task_status
                   FROM video_generation_jobs AS j
                   LEFT JOIN video_generation_task_links AS l
                     ON l.generation_id = j.generation_id
                    AND l.owner_user_id = j.owner_user_id
                   LEFT JOIN tasks AS t ON t.task_id = l.task_id
                   WHERE j.generation_id = ? AND j.owner_user_id = ?""",
                (str(generation_id), owner_user_id),
            ).fetchone()
            if row is None:
                return None

            generation_status = str(row["generation_status"])
            if generation_status == "cancelled":
                return {
                    "generation_id": str(generation_id),
                    "status": "cancelled",
                    "cancellation_requested": False,
                }

            if generation_status == "prepared":
                cursor = connection.execute(
                    """UPDATE video_generation_jobs
                       SET status = 'cancelled', error_code = 'cancelled_before_enqueue',
                           updated_at = ?
                       WHERE generation_id = ? AND owner_user_id = ? AND status = 'prepared'""",
                    (now, str(generation_id), owner_user_id),
                )
                if cursor.rowcount != 1:
                    raise VideoGenerationCancellationConflict(
                        "Generation state changed before cancellation"
                    )
            elif generation_status == "queued":
                task_id = row["task_id"]
                task_status = row["task_status"]
                if task_id is None or task_status not in {
                    TaskStatus.WAITING_APPROVAL.value,
                    TaskStatus.QUEUED.value,
                    TaskStatus.CANCELLED.value,
                }:
                    raise VideoGenerationCancellationConflict(
                        "Generation is no longer pending provider submission"
                    )
                if task_status != TaskStatus.CANCELLED.value:
                    task_cursor = connection.execute(
                        """UPDATE tasks SET status = 'cancelled', updated_at = ?
                           WHERE task_id = ? AND status = ?""",
                        (now, task_id, task_status),
                    )
                    if task_cursor.rowcount != 1:
                        raise VideoGenerationCancellationConflict(
                            "Generation task changed before cancellation"
                        )
                generation_cursor = connection.execute(
                    """UPDATE video_generation_jobs
                       SET status = 'cancelled', error_code = 'cancelled_before_submission',
                           updated_at = ?
                       WHERE generation_id = ? AND owner_user_id = ? AND status = 'queued'""",
                    (now, str(generation_id), owner_user_id),
                )
                if generation_cursor.rowcount != 1:
                    raise VideoGenerationCancellationConflict(
                        "Generation state changed before cancellation"
                    )
            else:
                raise VideoGenerationCancellationConflict(
                    "Active or ambiguous provider work requires provider-side cancellation support"
                )

            connection.execute(
                """DELETE FROM video_generation_payloads
                   WHERE generation_id = ? AND owner_user_id = ?""",
                (str(generation_id), owner_user_id),
            )
            audit_event = AuditLogger(self.tasks).build_event(
                event_type="video_generation.cancelled",
                outcome="success",
                subject_type="video_generation",
                subject_id=str(generation_id),
                actor_type="user",
                actor_id=owner_user_id,
                metadata={
                    "reason_code": (
                        "cancelled_before_enqueue"
                        if generation_status == "prepared"
                        else "cancelled_before_submission"
                    ),
                    "previous_status": generation_status,
                    "new_status": "cancelled",
                },
            )
            audit_payload = audit_event.model_dump(mode="json")
            audit_payload["created_at"] = now
            TaskRepository._insert_audit_event(connection, audit_payload)

        return {
            "generation_id": str(generation_id),
            "status": "cancelled",
            "cancellation_requested": False,
        }

    def request_cancellation(
        self, owner_user_id: str, generation_id: UUID
    ) -> dict[str, object] | None:
        """Cancel pending work or queue a provider-confirmed cancellation attempt.

        Active provider work is never marked cancelled by the API. The owner request
        is persisted, then the existing approval-bound task is requeued or allowed
        to observe the flag under its current lease. The Worker must confirm the
        provider's terminal state before the job can become cancelled.
        """
        try:
            pending = self.cancel_pending(owner_user_id, generation_id)
        except VideoGenerationCancellationConflict:
            pass
        else:
            return pending

        now = self._now()
        with self.tasks._connection() as connection:
            connection.execute("BEGIN IMMEDIATE")
            row = connection.execute(
                """SELECT j.status AS generation_status, j.provider_job_id,
                          j.cancellation_requested_at, l.task_id,
                          t.status AS task_status
                   FROM video_generation_jobs AS j
                   LEFT JOIN video_generation_task_links AS l
                     ON l.generation_id = j.generation_id
                    AND l.owner_user_id = j.owner_user_id
                   LEFT JOIN tasks AS t ON t.task_id = l.task_id
                   WHERE j.generation_id = ? AND j.owner_user_id = ?""",
                (str(generation_id), owner_user_id),
            ).fetchone()
            if row is None:
                return None

            generation_status = str(row["generation_status"])
            task_status = row["task_status"]
            if generation_status in {"succeeded", "failed", "cancelled"}:
                return {
                    "generation_id": str(generation_id),
                    "status": generation_status,
                    "cancellation_requested": False,
                    "created": False,
                    "execution": "already_terminal",
                }
            claimed_before_submit = (
                generation_status == "queued"
                and task_status == TaskStatus.RUNNING.value
            )
            if (
                generation_status not in {"submitting", "unknown_outcome", "running"}
                and not claimed_before_submit
            ):
                raise VideoGenerationCancellationConflict(
                    "Generation is not in a cancellable lifecycle state"
                )
            if generation_status == "running" and not row["provider_job_id"]:
                raise VideoGenerationCancellationConflict(
                    "Running generation is missing its provider reference"
                )

            task_id = row["task_id"]
            if task_id is None or task_status is None:
                raise VideoGenerationCancellationConflict(
                    "Generation has no recoverable worker task"
                )

            requeued = False
            if task_status in {TaskStatus.QUEUED.value, TaskStatus.RUNNING.value}:
                next_task_status = str(task_status)
            elif task_status in {
                TaskStatus.FAILED.value,
                TaskStatus.SUCCEEDED.value,
                TaskStatus.CANCELLED.value,
            }:
                cursor = connection.execute(
                    """UPDATE tasks SET status = ?, updated_at = ?
                       WHERE task_id = ? AND status = ?""",
                    (TaskStatus.QUEUED.value, now, task_id, task_status),
                )
                if cursor.rowcount != 1:
                    raise VideoGenerationCancellationConflict(
                        "Generation task changed before cancellation was queued"
                    )
                connection.execute(
                    """UPDATE worker_executions
                       SET attempt_count = 0, result_json = NULL, error_code = NULL,
                           started_at = NULL, finished_at = NULL, recovered_at = ?,
                           next_attempt_at = NULL, lease_owner = NULL,
                           lease_expires_at = NULL, heartbeat_at = NULL
                       WHERE task_id = ?""",
                    (now, task_id),
                )
                next_task_status = TaskStatus.QUEUED.value
                requeued = True
            else:
                raise VideoGenerationCancellationConflict(
                    "Generation task is awaiting an unsupported lifecycle transition"
                )

            was_requested = row["cancellation_requested_at"] is not None
            connection.execute(
                """UPDATE video_generation_jobs
                   SET cancellation_requested_at = COALESCE(cancellation_requested_at, ?),
                       updated_at = ?
                   WHERE generation_id = ? AND owner_user_id = ?
                     AND status IN ('queued', 'submitting', 'unknown_outcome', 'running')""",
                (now, now, str(generation_id), owner_user_id),
            )

            if not was_requested or requeued:
                audit_event = AuditLogger(self.tasks).build_event(
                    event_type="video_generation.cancellation_requested",
                    outcome="accepted",
                    subject_type="video_generation",
                    subject_id=str(generation_id),
                    actor_type="user",
                    actor_id=owner_user_id,
                    metadata={
                        "previous_status": generation_status,
                        "task_requeued": requeued,
                        "provider_job_reference_present": (
                            row["provider_job_id"] is not None
                        ),
                    },
                )
                audit_payload = audit_event.model_dump(mode="json")
                audit_payload["created_at"] = now
                TaskRepository._insert_audit_event(connection, audit_payload)

        return {
            "generation_id": str(generation_id),
            "status": generation_status,
            "cancellation_requested": True,
            "task_id": str(task_id),
            "task_status": next_task_status,
            "created": requeued,
            "execution": (
                "provider_cancellation_queued"
                if requeued
                else "provider_cancellation_active"
            ),
        }

    def list_for_owner(
        self,
        owner_user_id: str,
        *,
        limit: int = 20,
        before_created_at: str | None = None,
        before_generation_id: UUID | None = None,
    ) -> list[dict[str, object]]:
        """Return a bounded, stable, owner-scoped generation history page."""
        if not owner_user_id or len(owner_user_id) > 200:
            raise ValueError("Generation owner identifier is invalid")
        if not 1 <= limit <= 101:
            raise ValueError("Generation history limit must be between 1 and 101")
        if (before_created_at is None) != (before_generation_id is None):
            raise ValueError("Both generation history cursor fields are required")

        query = (
            "SELECT generation_id, source_analysis_id, provider, model, status, "
            "progress_percent, output_asset_id, output_bytes, "
            "output_duration_seconds, output_width, output_height, error_code, "
            "CASE WHEN cancellation_requested_at IS NOT NULL "
            "AND status IN ('queued', 'submitting', 'running', 'unknown_outcome') "
            "THEN 1 ELSE 0 END AS cancellation_requested, "
            "created_at, updated_at FROM video_generation_jobs "
            "WHERE owner_user_id = ?"
        )
        parameters: list[object] = [owner_user_id]
        if before_created_at is not None and before_generation_id is not None:
            query += (
                " AND (created_at < ? OR "
                "(created_at = ? AND generation_id < ?))"
            )
            parameters.extend(
                [before_created_at, before_created_at, str(before_generation_id)]
            )
        query += " ORDER BY created_at DESC, generation_id DESC LIMIT ?"
        parameters.append(limit)

        with self.tasks._connection() as connection:
            rows = connection.execute(query, parameters).fetchall()
        return [
            {
                **dict(row),
                "cancellation_requested": bool(row["cancellation_requested"]),
            }
            for row in rows
        ]

    def get(self, owner_user_id: str, generation_id: UUID) -> dict[str, object] | None:
        with self.tasks._connection() as connection:
            row = connection.execute(
                """SELECT generation_id, source_analysis_id, provider, model, status,
                          provider_job_id, progress_percent, cancellation_requested_at,
                          output_asset_id,
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
                    """SELECT 1 FROM worker_executions e
                       JOIN tasks t ON t.task_id = e.task_id
                       WHERE e.task_id = ? AND t.status = 'running'
                         AND e.lease_owner = ? AND e.execution_token = ?
                         AND e.lease_expires_at > ?""",
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
