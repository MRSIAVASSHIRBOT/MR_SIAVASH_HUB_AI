"""Owner-scoped durable video-analysis job persistence."""

from __future__ import annotations

import hashlib
import json
import sqlite3
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
from mrhub.video_intelligence.schemas import VideoAnalysisRequest

MAX_ACTIVE_VIDEO_ANALYSES_PER_OWNER = 2
MAX_ACTIVE_VIDEO_ANALYSES_GLOBAL = 25


class VideoAnalysisConflict(ValueError):
    """Raised when an idempotency key is reused for another analysis."""


class VideoAnalysisCapacityExceeded(ValueError):
    """Raised when bounded video-analysis admission capacity is exhausted."""


class VideoAnalysisJobRepository:
    """Persist encrypted requests and owner-scoped analysis status."""

    def __init__(self, database_path: Path) -> None:
        self.database_path = database_path
        self.tasks = TaskRepository(database_path)
        self.tasks.initialize()

    @staticmethod
    def _now() -> str:
        return datetime.now(UTC).isoformat()

    @staticmethod
    def _scope(owner_user_id: str) -> str:
        return f"video-analysis:{owner_user_id}"

    def submit(
        self, owner_user_id: str, request: VideoAnalysisRequest, idempotency_key: str
    ) -> tuple[dict[str, object], bool]:
        key = idempotency_key.strip()
        if not key or len(key) > 255:
            raise ValueError("Idempotency-Key must contain 1 to 255 characters")
        request_data = request.model_dump(mode="json")
        canonical = json.dumps(
            request_data, ensure_ascii=False, sort_keys=True, separators=(",", ":")
        ).encode("utf-8")
        digest = hashlib.sha256(canonical).hexdigest()
        analysis_id = uuid4()
        task = TaskRecord(
            task_type="video.analysis",
            risk_class=RiskClass.LOW,
            description="Owner-requested bounded video analysis",
        )
        now = self._now()
        scope = self._scope(owner_user_id)

        with self.tasks._connection() as connection:
            connection.execute("BEGIN IMMEDIATE")
            existing = connection.execute(
                "SELECT * FROM idempotency_records WHERE scope = ? AND idempotency_key = ?",
                (scope, key),
            ).fetchone()
            if existing is not None:
                if existing["request_digest"] != digest:
                    raise VideoAnalysisConflict("Idempotency key conflicts with an earlier request")
                if not existing["task_id"]:
                    raise VideoAnalysisConflict("Idempotency reservation is incomplete")
                row = connection.execute(
                    """SELECT analysis_id, task_id, status, created_at
                       FROM video_analysis_runs
                       WHERE task_id = ? AND owner_user_id = ?""",
                    (existing["task_id"], owner_user_id),
                ).fetchone()
                if row is None:
                    raise VideoAnalysisConflict("Existing analysis is unavailable")
                return self._record(row), False

            active_owner = connection.execute(
                """SELECT COUNT(*) AS total
                   FROM video_analysis_runs AS r
                   JOIN tasks AS t ON t.task_id = r.task_id
                   WHERE r.owner_user_id = ?
                     AND r.status IN ('accepted', 'running')
                     AND t.status IN (?, ?, ?)""",
                (
                    owner_user_id,
                    TaskStatus.QUEUED.value,
                    TaskStatus.RUNNING.value,
                    TaskStatus.WAITING_APPROVAL.value,
                ),
            ).fetchone()
            if int(active_owner["total"]) >= MAX_ACTIVE_VIDEO_ANALYSES_PER_OWNER:
                raise VideoAnalysisCapacityExceeded("Owner video-analysis capacity reached")

            active_global = connection.execute(
                """SELECT COUNT(*) AS total
                   FROM video_analysis_runs AS r
                   JOIN tasks AS t ON t.task_id = r.task_id
                   WHERE r.status IN ('accepted', 'running')
                     AND t.status IN (?, ?, ?)""",
                (
                    TaskStatus.QUEUED.value,
                    TaskStatus.RUNNING.value,
                    TaskStatus.WAITING_APPROVAL.value,
                ),
            ).fetchone()
            if int(active_global["total"]) >= MAX_ACTIVE_VIDEO_ANALYSES_GLOBAL:
                raise VideoAnalysisCapacityExceeded("Global video-analysis capacity reached")

            envelope = encrypt_payload(
                request_data,
                workflow_id=str(analysis_id),
                task_id=str(task.task_id),
                owner_user_id=owner_user_id,
                key=load_payload_key(),
            )

            connection.execute(
                """INSERT INTO tasks (
                    task_id, task_type, status, risk_class, created_at, updated_at, description
                ) VALUES (?, ?, ?, ?, ?, ?, ?)""",
                (
                    str(task.task_id), task.task_type, task.status.value,
                    task.risk_class.value, task.created_at.isoformat(),
                    task.updated_at.isoformat(), task.description,
                ),
            )
            connection.execute(
                """INSERT INTO video_analysis_runs (
                    analysis_id, task_id, owner_user_id, mode, status,
                    result_json, error_code, created_at, updated_at
                ) VALUES (?, ?, ?, ?, 'accepted', NULL, NULL, ?, ?)""",
                (
                    str(analysis_id), str(task.task_id), owner_user_id,
                    request.mode.value, now, now,
                ),
            )
            connection.execute(
                """INSERT INTO video_analysis_payloads (
                    analysis_id, task_id, owner_user_id, envelope_version,
                    nonce_b64, ciphertext_b64, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?)""",
                (
                    str(analysis_id), str(task.task_id), owner_user_id,
                    envelope.version, envelope.nonce_b64, envelope.ciphertext_b64, now,
                ),
            )
            connection.execute(
                """INSERT INTO idempotency_records (
                    scope, idempotency_key, request_digest, task_id,
                    workflow_id, status, created_at, expires_at
                ) VALUES (?, ?, ?, ?, NULL, 'accepted', ?, NULL)""",
                (scope, key, digest, str(task.task_id), now),
            )
        return {
            "analysis_id": str(analysis_id),
            "task_id": str(task.task_id),
            "status": "accepted",
            "created_at": now,
        }, True

    @staticmethod
    def _record(row: sqlite3.Row) -> dict[str, object]:
        return {
            "analysis_id": row["analysis_id"],
            "task_id": row["task_id"],
            "status": row["status"],
            "created_at": row["created_at"],
        }

    def get(self, owner_user_id: str, analysis_id: UUID) -> dict[str, object] | None:
        with self.tasks._connection() as connection:
            row = connection.execute(
                """SELECT analysis_id, task_id, status, created_at, updated_at,
                          result_json, error_code
                   FROM video_analysis_runs
                   WHERE analysis_id = ? AND owner_user_id = ?""",
                (str(analysis_id), owner_user_id),
            ).fetchone()
        if row is None:
            return None
        return {
            "analysis_id": row["analysis_id"],
            "status": row["status"],
            "created_at": row["created_at"],
            "updated_at": row["updated_at"],
            "result": json.loads(row["result_json"]) if row["result_json"] else None,
            "error_code": row["error_code"],
        }

    def owner_for_task(self, task_id: UUID) -> str | None:
        with self.tasks._connection() as connection:
            row = connection.execute(
                "SELECT owner_user_id FROM video_analysis_runs WHERE task_id = ?",
                (str(task_id),),
            ).fetchone()
        return str(row["owner_user_id"]) if row is not None else None

    def load_for_worker(self, task_id: UUID) -> tuple[str, UUID, dict[str, object]] | None:
        with self.tasks._connection() as connection:
            row = connection.execute(
                """SELECT r.analysis_id, r.owner_user_id, p.envelope_version,
                          p.nonce_b64, p.ciphertext_b64
                   FROM video_analysis_runs AS r
                   JOIN video_analysis_payloads AS p
                     ON p.analysis_id = r.analysis_id
                    AND p.task_id = r.task_id
                    AND p.owner_user_id = r.owner_user_id
                   WHERE r.task_id = ?""",
                (str(task_id),),
            ).fetchone()
        if row is None:
            return None
        analysis_id = UUID(row["analysis_id"])
        payload = decrypt_payload(
            EncryptedPayload(
                version=int(row["envelope_version"]),
                nonce_b64=str(row["nonce_b64"]),
                ciphertext_b64=str(row["ciphertext_b64"]),
            ),
            workflow_id=str(analysis_id),
            task_id=str(task_id),
            owner_user_id=str(row["owner_user_id"]),
            key=load_payload_key(),
        )
        return str(row["owner_user_id"]), analysis_id, payload

    def mark_running(
        self, task_id: UUID, owner_user_id: str, *, lease: WorkerLease
    ) -> bool:
        if lease.task_id != str(task_id):
            raise ValueError("Worker lease does not belong to this analysis task")
        now = self._now()
        with self.tasks._connection() as connection:
            cursor = connection.execute(
                """UPDATE video_analysis_runs SET status = 'running', updated_at = ?
                   WHERE task_id = ? AND owner_user_id = ? AND status = 'accepted'
                     AND EXISTS (
                       SELECT 1 FROM worker_executions AS e
                       WHERE e.task_id = ? AND e.lease_owner = ?
                         AND e.execution_token = ? AND e.lease_expires_at > ?
                     )""",
                (
                    now, str(task_id), owner_user_id, str(task_id),
                    lease.owner, lease.fencing_token, now,
                ),
            )
        return cursor.rowcount == 1

    def finish(
        self, task_id: UUID, owner_user_id: str, *,
        status: str, result: dict[str, object] | None = None,
        error_code: str | None = None,
        lease: WorkerLease,
    ) -> None:
        if status not in {"completed", "failed", "cancelled"}:
            raise ValueError("Invalid terminal video-analysis status")
        if lease.task_id != str(task_id):
            raise ValueError("Worker lease does not belong to this analysis task")
        with self.tasks._connection() as connection:
            row = connection.execute(
                """SELECT analysis_id FROM video_analysis_runs
                   WHERE task_id = ? AND owner_user_id = ?""",
                (str(task_id), owner_user_id),
            ).fetchone()
            if row is None:
                return
            now = self._now()
            cursor = connection.execute(
                """UPDATE video_analysis_runs
                   SET status = ?, result_json = ?, error_code = ?, updated_at = ?
                   WHERE task_id = ? AND owner_user_id = ?
                     AND EXISTS (
                       SELECT 1 FROM worker_executions AS e
                       WHERE e.task_id = ? AND e.lease_owner = ?
                         AND e.execution_token = ? AND e.lease_expires_at > ?
                     )""",
                (
                    status,
                    json.dumps(result, ensure_ascii=False, sort_keys=True) if result is not None else None,
                    error_code[:80] if error_code else None,
                    now, str(task_id), owner_user_id, str(task_id),
                    lease.owner, lease.fencing_token, now,
                ),
            )
            if cursor.rowcount != 1:
                return
            connection.execute(
                "DELETE FROM video_analysis_payloads WHERE analysis_id = ? AND owner_user_id = ?",
                (row["analysis_id"], owner_user_id),
            )
            connection.execute(
                """UPDATE idempotency_records SET status = ?
                   WHERE scope = ? AND task_id = ?""",
                (
                    "completed" if status == "completed" else (
                        "failed" if status == "failed" else "unknown_outcome"
                    ),
                    self._scope(owner_user_id), str(task_id),
                ),
            )
