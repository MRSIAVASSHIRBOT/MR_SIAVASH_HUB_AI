"""Checkpoint and fail-closed recovery primitives for durable workflows."""

from __future__ import annotations

import hashlib
import re
import sqlite3
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from uuid import UUID, uuid4


class WorkflowRecoveryError(RuntimeError):
    """Raised when a workflow cannot safely advance or recover."""


class RecoveryRequired(WorkflowRecoveryError):
    """Raised when an ambiguous step outcome requires reconciliation."""


@dataclass(frozen=True)
class StepAttempt:
    attempt_id: str
    step_id: str
    step_number: int
    attempt_number: int


@dataclass(frozen=True)
class WorkflowCheckpoint:
    checkpoint_id: str
    workflow_id: str
    checkpoint_version: int
    step_number: int
    state_digest: str
    created_at: str


@dataclass(frozen=True)
class ResumeDecision:
    decision: str
    next_step: int | None
    checkpoint_version: int | None
    reason_code: str | None


class WorkflowRecoveryRepository:
    """Persist step attempts and digest-only checkpoints; never store executable state."""

    _DIGEST_PATTERN = re.compile(r"^[0-9a-f]{64}$")
    _ERROR_PATTERN = re.compile(r"^[a-z0-9_.-]{1,80}$")

    def __init__(
        self,
        database_path: Path,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self.database_path = database_path
        self._clock = clock or (lambda: datetime.now(UTC))

    def _now(self) -> str:
        value = self._clock()
        if value.tzinfo is None:
            raise WorkflowRecoveryError("Recovery clock must return a timezone-aware datetime")
        return value.astimezone(UTC).isoformat()

    def _connect(self) -> sqlite3.Connection:
        self.database_path.parent.mkdir(parents=True, exist_ok=True)
        connection = sqlite3.connect(self.database_path, timeout=5.0)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        connection.execute("PRAGMA busy_timeout = 5000")
        return connection

    @contextmanager
    def _connection(self) -> Iterator[sqlite3.Connection]:
        connection = self._connect()
        try:
            yield connection
            connection.commit()
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

    @classmethod
    def _validate_digest(cls, value: str, label: str) -> None:
        if not cls._DIGEST_PATTERN.fullmatch(value):
            raise WorkflowRecoveryError(f"{label} must be a lowercase SHA-256 hex digest")

    def create_run(
        self,
        request_digest: str,
        steps: list[dict[str, object]],
        *,
        task_id: str | None = None,
        definition_version: int = 1,
    ) -> UUID:
        """Create a queued workflow and its step identities, excluding all payloads."""
        self._validate_digest(request_digest, "Request digest")
        if definition_version < 1:
            raise WorkflowRecoveryError("Definition version must be positive")
        if not steps:
            raise WorkflowRecoveryError("A workflow must contain at least one step")

        normalized: list[tuple[int, str, str]] = []
        seen_numbers: set[int] = set()
        for item in steps:
            number = item.get("step_number")
            kind = item.get("kind")
            name = item.get("name")
            if not isinstance(number, int) or number < 1 or number in seen_numbers:
                raise WorkflowRecoveryError("Workflow step numbers must be unique positive integers")
            if not isinstance(kind, str) or not kind.strip() or len(kind) > 80:
                raise WorkflowRecoveryError("Workflow step kind is invalid")
            if not isinstance(name, str) or not name.strip() or len(name) > 120:
                raise WorkflowRecoveryError("Workflow step name is invalid")
            seen_numbers.add(number)
            normalized.append((number, kind, name))

        workflow_id = uuid4()
        now = self._now()
        with self._connection() as connection:
            connection.execute("BEGIN IMMEDIATE")
            connection.execute(
                """
                INSERT INTO workflow_runs (
                    workflow_id, task_id, status, request_digest,
                    definition_version, current_step, last_error_code,
                    created_at, updated_at
                ) VALUES (?, ?, 'queued', ?, ?, 0, NULL, ?, ?)
                """,
                (
                    str(workflow_id), task_id, request_digest,
                    definition_version, now, now,
                ),
            )
            for number, kind, name in normalized:
                connection.execute(
                    """
                    INSERT INTO workflow_steps (
                        step_id, workflow_id, step_number, step_kind, step_name,
                        status, input_digest, output_digest, error_code,
                        attempt_count, started_at, finished_at, created_at, updated_at
                    ) VALUES (?, ?, ?, ?, ?, 'pending', NULL, NULL, NULL, 0, NULL, NULL, ?, ?)
                    """,
                    (str(uuid4()), str(workflow_id), number, kind, name, now, now),
                )
        return workflow_id

    def start_run(self, workflow_id: UUID) -> None:
        now = self._now()
        with self._connection() as connection:
            cursor = connection.execute(
                """
                UPDATE workflow_runs SET status = 'running', updated_at = ?
                WHERE workflow_id = ? AND status IN ('queued', 'paused')
                """,
                (now, str(workflow_id)),
            )
            if cursor.rowcount != 1:
                raise WorkflowRecoveryError("Workflow is not eligible to start or resume")

    def start_step(self, workflow_id: UUID, step_number: int) -> StepAttempt:
        now = self._now()
        with self._connection() as connection:
            connection.execute("BEGIN IMMEDIATE")

            step = connection.execute(
                """
                SELECT step_id, status, attempt_count FROM workflow_steps
                WHERE workflow_id = ? AND step_number = ?
                """,
                (str(workflow_id), step_number),
            ).fetchone()
            if step is None:
                raise LookupError("Workflow step not found")
            if step["status"] == "unknown_outcome":
                raise RecoveryRequired("Step outcome must be reconciled before resuming")
            if step["status"] not in {"pending", "retry_wait"}:
                raise WorkflowRecoveryError("Step is not eligible to start")
            earlier = connection.execute(
                """
                SELECT COUNT(*) AS total FROM workflow_steps
                WHERE workflow_id = ? AND step_number < ? AND status != 'succeeded'
                """,
                (str(workflow_id), step_number),
            ).fetchone()
            if earlier["total"]:
                raise WorkflowRecoveryError("Earlier workflow steps must succeed first")

            attempt_number = int(step["attempt_count"]) + 1
            attempt_id = str(uuid4())
            connection.execute(
                """
                INSERT INTO workflow_step_attempts (
                    attempt_id, step_id, attempt_number, status,
                    error_code, started_at, finished_at
                ) VALUES (?, ?, ?, 'running', NULL, ?, NULL)
                """,
                (attempt_id, step["step_id"], attempt_number, now),
            )
            connection.execute(
                """
                UPDATE workflow_steps
                SET status = 'running', attempt_count = ?, started_at = ?,
                    finished_at = NULL, error_code = NULL, updated_at = ?
                WHERE step_id = ? AND status IN ('pending', 'retry_wait')
                """,
                (attempt_number, now, now, step["step_id"]),
            )
            connection.execute(
                """
                UPDATE workflow_runs SET current_step = ?, updated_at = ?
                WHERE workflow_id = ? AND status = 'running'
                """,
                (step_number, now, str(workflow_id)),
            )
            return StepAttempt(attempt_id, step["step_id"], step_number, attempt_number)

    def complete_step(
        self,
        workflow_id: UUID,
        attempt: StepAttempt,
        output_digest: str,
    ) -> WorkflowCheckpoint:
        """Commit a validated step result and its digest-only checkpoint atomically."""
        self._validate_digest(output_digest, "Output digest")
        now = self._now()
        with self._connection() as connection:
            connection.execute("BEGIN IMMEDIATE")
            run = connection.execute(
                "SELECT status, request_digest FROM workflow_runs WHERE workflow_id = ?",
                (str(workflow_id),),
            ).fetchone()
            if run is None:
                raise LookupError("Workflow not found")
            if run["status"] != "running":
                raise WorkflowRecoveryError("Workflow is not running")

            step = connection.execute(
                """
                SELECT step_id, status FROM workflow_steps
                WHERE workflow_id = ? AND step_number = ?
                """,
                (str(workflow_id), attempt.step_number),
            ).fetchone()
            if step is None or step["step_id"] != attempt.step_id or step["status"] != "running":
                raise WorkflowRecoveryError("Step ownership changed before completion")
            cursor = connection.execute(
                """
                UPDATE workflow_step_attempts
                SET status = 'succeeded', finished_at = ?
                WHERE attempt_id = ? AND step_id = ? AND status = 'running'
                """,
                (now, attempt.attempt_id, attempt.step_id),
            )
            if cursor.rowcount != 1:
                raise WorkflowRecoveryError("Step attempt is no longer active")

            connection.execute(
                """
                UPDATE workflow_steps
                SET status = 'succeeded', output_digest = ?, finished_at = ?,
                    error_code = NULL, updated_at = ?
                WHERE step_id = ? AND status = 'running'
                """,
                (output_digest, now, now, attempt.step_id),
            )
            latest = connection.execute(
                """
                SELECT checkpoint_version, state_digest FROM workflow_checkpoints
                WHERE workflow_id = ? ORDER BY checkpoint_version DESC LIMIT 1
                """,
                (str(workflow_id),),
            ).fetchone()
            previous_digest = latest["state_digest"] if latest else run["request_digest"]
            version = int(latest["checkpoint_version"]) + 1 if latest else 1
            state_digest = hashlib.sha256(
                f"{previous_digest}:{attempt.step_number}:{output_digest}".encode()
            ).hexdigest()
            checkpoint_id = str(uuid4())
            connection.execute(
                """
                INSERT INTO workflow_checkpoints (
                    checkpoint_id, workflow_id, checkpoint_version,
                    step_number, state_digest, created_at
                ) VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    checkpoint_id, str(workflow_id), version,
                    attempt.step_number, state_digest, now,
                ),
            )
            connection.execute(
                "UPDATE workflow_runs SET updated_at = ? WHERE workflow_id = ?",
                (now, str(workflow_id)),
            )
            return WorkflowCheckpoint(
                checkpoint_id, str(workflow_id), version,
                attempt.step_number, state_digest, now,
            )

    def fail_step(
        self,
        workflow_id: UUID,
        attempt: StepAttempt,
        error_code: str,
        *,
        unknown_outcome: bool = False,
    ) -> None:
        if not self._ERROR_PATTERN.fullmatch(error_code):
            raise WorkflowRecoveryError("Error code must be a bounded safe identifier")
        now = self._now()
        step_status = "unknown_outcome" if unknown_outcome else "failed"
        run_status = "recovery_required" if unknown_outcome else "failed"
        with self._connection() as connection:
            connection.execute("BEGIN IMMEDIATE")
            run = connection.execute(
                "SELECT status FROM workflow_runs WHERE workflow_id = ?",
                (str(workflow_id),),
            ).fetchone()
            if run is None:
                raise LookupError("Workflow not found")
            if run["status"] != "running":
                raise WorkflowRecoveryError("Workflow is not running")
            step = connection.execute(
                """
                SELECT step_id, status FROM workflow_steps
                WHERE workflow_id = ? AND step_number = ?
                """,
                (str(workflow_id), attempt.step_number),
            ).fetchone()
            if step is None or step["step_id"] != attempt.step_id or step["status"] != "running":
                raise WorkflowRecoveryError("Step attempt is no longer active")
            cursor = connection.execute(
                """
                UPDATE workflow_step_attempts
                SET status = ?, error_code = ?, finished_at = ?
                WHERE attempt_id = ? AND step_id = ? AND status = 'running'
                """,
                (step_status, error_code, now, attempt.attempt_id, attempt.step_id),
            )
            if cursor.rowcount != 1:
                raise WorkflowRecoveryError("Step attempt is no longer active")
            connection.execute(
                """
                UPDATE workflow_steps SET status = ?, error_code = ?,
                    finished_at = ?, updated_at = ?
                WHERE step_id = ? AND status = 'running'
                """,
                (step_status, error_code, now, now, attempt.step_id),
            )
            connection.execute(
                """
                UPDATE workflow_runs SET status = ?, last_error_code = ?, updated_at = ?
                WHERE workflow_id = ? AND status = 'running'
                """,
                (run_status, error_code, now, str(workflow_id)),
            )

    def mark_interrupted(self, workflow_id: UUID) -> int:
        """Classify all active attempts as ambiguous; never replay them automatically."""
        now = self._now()
        with self._connection() as connection:
            connection.execute("BEGIN IMMEDIATE")
            rows = connection.execute(
                """
                SELECT step_id, step_number FROM workflow_steps
                WHERE workflow_id = ? AND status = 'running'
                """,
                (str(workflow_id),),
            ).fetchall()
            if not rows:
                return 0
            for row in rows:
                connection.execute(
                    """
                    UPDATE workflow_step_attempts
                    SET status = 'unknown_outcome', error_code = 'worker_interrupted',
                        finished_at = ?
                    WHERE step_id = ? AND status = 'running'
                    """,
                    (now, row["step_id"]),
                )
                connection.execute(
                    """
                    UPDATE workflow_steps
                    SET status = 'unknown_outcome', error_code = 'worker_interrupted',
                        finished_at = ?, updated_at = ?
                    WHERE step_id = ? AND status = 'running'
                    """,
                    (now, now, row["step_id"]),
                )
            connection.execute(
                """
                UPDATE workflow_runs
                SET status = 'recovery_required', last_error_code = 'worker_interrupted',
                    updated_at = ?
                WHERE workflow_id = ? AND status = 'running'
                """,
                (now, str(workflow_id)),
            )
            return len(rows)

    def resolve_unknown_step(
        self,
        workflow_id: UUID,
        step_number: int,
        outcome: str,
        *,
        output_digest: str | None = None,
    ) -> WorkflowCheckpoint | None:
        """Record a reconciled external outcome; this method never invokes the step."""
        if outcome not in {"succeeded", "failed"}:
            raise WorkflowRecoveryError("Reconciled outcome must be succeeded or failed")
        if outcome == "succeeded":
            if output_digest is None:
                raise WorkflowRecoveryError("A reconciled success requires an output digest")
            self._validate_digest(output_digest, "Output digest")
        now = self._now()
        with self._connection() as connection:
            connection.execute("BEGIN IMMEDIATE")
            run = connection.execute(
                "SELECT request_digest, status FROM workflow_runs WHERE workflow_id = ?",
                (str(workflow_id),),
            ).fetchone()
            if run is None:
                raise LookupError("Workflow not found")
            if run["status"] != "recovery_required":
                raise WorkflowRecoveryError("Workflow is not awaiting recovery")
            step = connection.execute(
                """
                SELECT step_id, status FROM workflow_steps
                WHERE workflow_id = ? AND step_number = ?
                """,
                (str(workflow_id), step_number),
            ).fetchone()
            if step is None:
                raise LookupError("Workflow step not found")
            if step["status"] != "unknown_outcome":
                raise WorkflowRecoveryError("Step has no unknown outcome to reconcile")
            cursor = connection.execute(
                """
                UPDATE workflow_step_attempts
                SET status = ?, error_code = NULL, finished_at = ?
                WHERE step_id = ? AND status = 'unknown_outcome'
                """,
                (outcome, now, step["step_id"]),
            )
            if cursor.rowcount != 1:
                raise WorkflowRecoveryError("Unknown step attempt is unavailable")
            connection.execute(
                """
                UPDATE workflow_steps
                SET status = ?, output_digest = ?, error_code = NULL,
                    finished_at = ?, updated_at = ?
                WHERE step_id = ? AND status = 'unknown_outcome'
                """,
                (outcome, output_digest, now, now, step["step_id"]),
            )
            checkpoint = None
            if outcome == "succeeded":
                latest = connection.execute(
                    """
                    SELECT checkpoint_version, state_digest FROM workflow_checkpoints
                    WHERE workflow_id = ? ORDER BY checkpoint_version DESC LIMIT 1
                    """,
                    (str(workflow_id),),
                ).fetchone()
                previous_digest = latest["state_digest"] if latest else run["request_digest"]
                version = int(latest["checkpoint_version"]) + 1 if latest else 1
                state_digest = hashlib.sha256(
                    f"{previous_digest}:{step_number}:{output_digest}".encode()
                ).hexdigest()
                checkpoint_id = str(uuid4())
                connection.execute(
                    """
                    INSERT INTO workflow_checkpoints (
                        checkpoint_id, workflow_id, checkpoint_version,
                        step_number, state_digest, created_at
                    ) VALUES (?, ?, ?, ?, ?, ?)
                    """,
                    (checkpoint_id, str(workflow_id), version, step_number, state_digest, now),
                )
                checkpoint = WorkflowCheckpoint(
                    checkpoint_id, str(workflow_id), version, step_number, state_digest, now
                )
                connection.execute(
                    """
                    UPDATE workflow_runs SET status = 'paused', last_error_code = NULL,
                        updated_at = ? WHERE workflow_id = ?
                    """,
                    (now, str(workflow_id)),
                )
            else:
                connection.execute(
                    """
                    UPDATE workflow_runs SET status = 'failed', last_error_code = 'reconciled_failure',
                        updated_at = ? WHERE workflow_id = ?
                    """,
                    (now, str(workflow_id)),
                )
            return checkpoint

    def finish_run(self, workflow_id: UUID, status: str) -> None:
        if status not in {"succeeded", "failed", "cancelled"}:
            raise WorkflowRecoveryError("Unsupported terminal workflow status")
        now = self._now()
        with self._connection() as connection:
            connection.execute("BEGIN IMMEDIATE")
            if status == "succeeded":
                counts = connection.execute(
                    """
                    SELECT COUNT(*) AS total,
                           SUM(CASE WHEN status = 'succeeded' THEN 1 ELSE 0 END) AS succeeded
                    FROM workflow_steps WHERE workflow_id = ?
                    """,
                    (str(workflow_id),),
                ).fetchone()
                if counts is None or counts["total"] == 0 or counts["total"] != counts["succeeded"]:
                    raise WorkflowRecoveryError("Every workflow step must succeed before completion")
            cursor = connection.execute(
                """
                UPDATE workflow_runs SET status = ?, updated_at = ?
                WHERE workflow_id = ? AND status = 'running'
                """,
                (status, now, str(workflow_id)),
            )
            if cursor.rowcount != 1:
                raise WorkflowRecoveryError("Workflow is not running")

    def latest_checkpoint(self, workflow_id: UUID) -> WorkflowCheckpoint | None:
        with self._connection() as connection:
            row = connection.execute(
                """
                SELECT * FROM workflow_checkpoints
                WHERE workflow_id = ? ORDER BY checkpoint_version DESC LIMIT 1
                """,
                (str(workflow_id),),
            ).fetchone()
        if row is None:
            return None
        return WorkflowCheckpoint(
            row["checkpoint_id"],
            row["workflow_id"],
            row["checkpoint_version"],
            row["step_number"],
            row["state_digest"],
            row["created_at"],
        )

    def resume_decision(
        self,
        workflow_id: UUID,
        supplied_request_digest: str,
        *,
        definition_version: int = 1,
    ) -> ResumeDecision:
        """Return a safe next action without executing or replaying any step."""
        self._validate_digest(supplied_request_digest, "Supplied request digest")
        with self._connection() as connection:
            run = connection.execute(
                "SELECT * FROM workflow_runs WHERE workflow_id = ?",
                (str(workflow_id),),
            ).fetchone()
            if run is None:
                raise LookupError("Workflow not found")
            checkpoint = connection.execute(
                """
                SELECT checkpoint_version, step_number FROM workflow_checkpoints
                WHERE workflow_id = ? ORDER BY checkpoint_version DESC LIMIT 1
                """,
                (str(workflow_id),),
            ).fetchone()
            checkpoint_version = checkpoint["checkpoint_version"] if checkpoint else None
            if run["status"] == "recovery_required":
                return ResumeDecision("reconcile", None, checkpoint_version, run["last_error_code"])
            if run["status"] in {"succeeded", "failed", "cancelled"}:
                return ResumeDecision("terminal", None, checkpoint_version, run["status"])
            if run["status"] == "waiting_approval":
                return ResumeDecision("waiting_approval", None, checkpoint_version, None)
            if run["definition_version"] != definition_version:
                return ResumeDecision(
                    "replan", None, checkpoint_version, "definition_version_mismatch"
                )
            if run["request_digest"] != supplied_request_digest:
                return ResumeDecision("request_input", None, checkpoint_version, "request_digest_mismatch")

            active = connection.execute(
                """
                SELECT step_number FROM workflow_steps
                WHERE workflow_id = ? AND status = 'running'
                ORDER BY step_number LIMIT 1
                """,
                (str(workflow_id),),
            ).fetchone()
            if active is not None:
                return ResumeDecision("in_progress", active["step_number"], checkpoint_version, None)

            failed = connection.execute(
                """
                SELECT step_number, status FROM workflow_steps
                WHERE workflow_id = ? AND status IN ('failed', 'unknown_outcome', 'cancelled')
                ORDER BY step_number LIMIT 1
                """,
                (str(workflow_id),),
            ).fetchone()
            if failed is not None:
                reason = {
                    "failed": "step_failed",
                    "unknown_outcome": "step_outcome_unknown",
                    "cancelled": "step_cancelled",
                }[failed["status"]]
                return ResumeDecision("reconcile", failed["step_number"], checkpoint_version, reason)

            next_step = connection.execute(
                """
                SELECT step_number FROM workflow_steps
                WHERE workflow_id = ? AND status IN ('pending', 'retry_wait')
                ORDER BY step_number LIMIT 1
                """,
                (str(workflow_id),),
            ).fetchone()
            if next_step is not None:
                return ResumeDecision("resume", next_step["step_number"], checkpoint_version, None)
            return ResumeDecision("finish", None, checkpoint_version, "all_steps_succeeded")

    def get_run(self, workflow_id: UUID) -> dict[str, object] | None:
        with self._connection() as connection:
            run = connection.execute(
                "SELECT * FROM workflow_runs WHERE workflow_id = ?",
                (str(workflow_id),),
            ).fetchone()
            if run is None:
                return None
            steps = connection.execute(
                """
                SELECT step_number, step_kind, step_name, status, input_digest,
                       output_digest, error_code, attempt_count, started_at, finished_at
                FROM workflow_steps WHERE workflow_id = ? ORDER BY step_number
                """,
                (str(workflow_id),),
            ).fetchall()
        return {
            "workflow_id": run["workflow_id"],
            "task_id": run["task_id"],
            "status": run["status"],
            "request_digest": run["request_digest"],
            "definition_version": run["definition_version"],
            "current_step": run["current_step"],
            "last_error_code": run["last_error_code"],
            "steps": [dict(row) for row in steps],
            "stored_request": False,
            "stored_step_payloads": False,
            "stored_step_outputs": False,
        }
