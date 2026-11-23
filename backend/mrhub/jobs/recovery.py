"""Checkpoint and fail-closed recovery primitives for durable workflows."""

from __future__ import annotations

import hashlib
import json
import re
import sqlite3
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from uuid import UUID, uuid4

from mrhub.domain.tasks import TaskRecord, TaskStatus
from mrhub.jobs.leases import WorkerLease


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
    step_key: str = ""


@dataclass(frozen=True)
class WorkflowCheckpoint:
    checkpoint_id: str
    workflow_id: str
    checkpoint_version: int
    step_number: int
    state_digest: str
    created_at: str
    step_key: str | None = None


@dataclass(frozen=True)
class ResumeDecision:
    decision: str
    next_step: int | None
    checkpoint_version: int | None
    reason_code: str | None
    next_step_id: str | None = None


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

    def _assert_lease(
        self,
        connection: sqlite3.Connection,
        workflow_id: UUID,
        lease: WorkerLease | None,
        now: str,
    ) -> None:
        run = connection.execute(
            "SELECT task_id FROM workflow_runs WHERE workflow_id = ?",
            (str(workflow_id),),
        ).fetchone()
        if run is None:
            if lease is None:
                return
            raise RecoveryRequired("Worker lease does not own this workflow")

        task_id = run["task_id"]
        if task_id is None:
            if lease is not None:
                raise RecoveryRequired("Worker lease does not own this workflow")
            return
        if lease is None:
            raise RecoveryRequired("Worker lease is required for task-linked workflow")
        if task_id != lease.task_id:
            raise RecoveryRequired("Worker lease does not own this workflow")
        current = connection.execute(
            """
            SELECT 1 FROM worker_executions
            WHERE task_id = ? AND lease_owner = ? AND execution_token = ?
              AND lease_expires_at > ?
            """,
            (lease.task_id, lease.owner, lease.fencing_token, now),
        ).fetchone()
        if current is None:
            raise RecoveryRequired("Workflow worker lease was lost")

    def create_run(
        self,
        request_digest: str,
        steps: list[dict[str, object]],
        *,
        task_id: str | None = None,
        task: TaskRecord | None = None,
        definition_version: int = 1,
        owner_user_id: str | None = None,
        payload_envelope: dict[str, object] | None = None,
        workflow_id: UUID | None = None,
        idempotency_binding: dict[str, str] | None = None,
    ) -> UUID:
        """Atomically create workflow/job, encrypted payload, and optional idempotency binding."""
        self._validate_digest(request_digest, "Request digest")
        if task is not None and task_id is not None:
            raise WorkflowRecoveryError("Provide either task or task_id, not both")
        if task is not None and task.status is not TaskStatus.QUEUED:
            raise WorkflowRecoveryError("A linked workflow task must start queued")
        if task is not None:
            task_id = str(task.task_id)
        if definition_version < 1:
            raise WorkflowRecoveryError("Definition version must be positive")
        if not steps:
            raise WorkflowRecoveryError("A workflow must contain at least one step")

        normalized: list[tuple[int, str, str, str | None, str, list[str] | None]] = []
        seen_numbers: set[int] = set()
        seen_keys: set[str] = set()
        for item in steps:
            number = item.get("step_number")
            kind = item.get("kind")
            name = item.get("name")
            input_digest = item.get("input_digest")
            step_key = item.get("step_key", f"step-{number}")
            dependencies = item.get("depends_on")
            if not isinstance(number, int) or isinstance(number, bool) or number < 1 or number in seen_numbers:
                raise WorkflowRecoveryError("Workflow step numbers must be unique positive integers")
            if not isinstance(kind, str) or not kind.strip() or len(kind) > 80:
                raise WorkflowRecoveryError("Workflow step kind is invalid")
            if not isinstance(name, str) or not name.strip() or len(name) > 120:
                raise WorkflowRecoveryError("Workflow step name is invalid")
            if (
                not isinstance(step_key, str)
                or not re.fullmatch(r"[a-z][a-z0-9-]{0,63}", step_key)
                or step_key in seen_keys
            ):
                raise WorkflowRecoveryError("Workflow step identity is invalid or duplicated")
            if dependencies is not None and (
                not isinstance(dependencies, list)
                or any(
                    not isinstance(dependency, str)
                    or not re.fullmatch(r"[a-z][a-z0-9-]{0,63}", dependency)
                    for dependency in dependencies
                )
                or len(dependencies) != len(set(dependencies))
            ):
                raise WorkflowRecoveryError("Workflow step dependencies are invalid")
            if input_digest is not None:
                if not isinstance(input_digest, str):
                    raise WorkflowRecoveryError("Workflow step input digest is invalid")
                self._validate_digest(input_digest, "Workflow step input digest")
            seen_numbers.add(number)
            seen_keys.add(step_key)
            normalized.append((number, kind, name, input_digest, step_key, dependencies))

        # Preserve the historical sequential contract when dependency metadata
        # is omitted. New definitions may declare an independent or explicit DAG.
        by_key = {item[4]: item for item in normalized}
        ordered_numbers = sorted(normalized, key=lambda item: item[0])
        prepared: list[tuple[int, str, str, str | None, str, list[str]]] = []
        for index, item in enumerate(ordered_numbers):
            number, kind, name, input_digest, step_key, dependencies = item
            if dependencies is None:
                dependencies = [ordered_numbers[index - 1][4]] if index else []
            if any(dependency not in by_key for dependency in dependencies):
                raise WorkflowRecoveryError("Workflow step depends on an unknown identity")
            if step_key in dependencies:
                raise WorkflowRecoveryError("Workflow step cannot depend on itself")
            prepared.append((number, kind, name, input_digest, step_key, dependencies))

        # Validate the persisted dependency graph independently of the API planner.
        remaining = {item[4]: set(item[5]) for item in prepared}
        while remaining:
            ready = {key for key, dependencies in remaining.items() if not dependencies}
            if not ready:
                raise WorkflowRecoveryError("Workflow dependency graph contains a cycle")
            for key in ready:
                remaining.pop(key)
            for dependencies in remaining.values():
                dependencies.difference_update(ready)

        workflow_id = workflow_id or uuid4()
        now = self._now()
        with self._connection() as connection:
            connection.execute("BEGIN IMMEDIATE")
            if task is not None:
                connection.execute(
                    """
                    INSERT INTO tasks (
                        task_id, task_type, status, risk_class,
                        created_at, updated_at, description
                    ) VALUES (?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        str(task.task_id),
                        task.task_type,
                        task.status.value,
                        task.risk_class.value,
                        task.created_at.isoformat(),
                        task.updated_at.isoformat(),
                        task.description,
                    ),
                )
                connection.execute(
                    """
                    INSERT INTO worker_executions (task_id, attempt_count)
                    VALUES (?, 0)
                    """,
                    (str(task.task_id),),
                )
            connection.execute(
                """
                INSERT INTO workflow_runs (
                    workflow_id, task_id, status, request_digest,
                    definition_version, current_step, last_error_code,
                    created_at, updated_at, owner_user_id
                ) VALUES (?, ?, 'queued', ?, ?, 0, NULL, ?, ?, ?)
                """,
                (
                    str(workflow_id), task_id, request_digest,
                    definition_version, now, now, owner_user_id,
                ),
            )
            if idempotency_binding is not None:
                scope = idempotency_binding.get("scope")
                key = idempotency_binding.get("key")
                if not isinstance(scope, str) or not scope or not isinstance(key, str) or not key:
                    raise WorkflowRecoveryError("Idempotency binding is invalid")
                if task_id is None:
                    raise WorkflowRecoveryError("Idempotency binding requires a task")
                connection.execute(
                    """
                    INSERT INTO idempotency_records (
                        scope, idempotency_key, request_digest, task_id,
                        workflow_id, status, created_at, expires_at
                    ) VALUES (?, ?, ?, ?, ?, 'accepted', ?, NULL)
                    """,
                    (scope, key, request_digest, task_id, str(workflow_id), now),
                )

            if payload_envelope is not None:
                if task_id is None or task is None or not owner_user_id:
                    raise WorkflowRecoveryError(
                        "Encrypted workflow payload requires a linked task and owner"
                    )
                version = payload_envelope.get("version")
                nonce_b64 = payload_envelope.get("nonce_b64")
                ciphertext_b64 = payload_envelope.get("ciphertext_b64")
                if (
                    not isinstance(version, int) or version < 1
                    or not isinstance(nonce_b64, str) or not nonce_b64
                    or not isinstance(ciphertext_b64, str) or not ciphertext_b64
                ):
                    raise WorkflowRecoveryError("Encrypted workflow payload envelope is invalid")
                connection.execute(
                    """
                    INSERT INTO workflow_payloads (
                        workflow_id, task_id, owner_user_id, envelope_version,
                        nonce_b64, ciphertext_b64, created_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        str(workflow_id), task_id, owner_user_id, version,
                        nonce_b64, ciphertext_b64, now,
                    ),
                )
            for number, kind, name, input_digest, step_key, dependencies in prepared:
                connection.execute(
                    """
                    INSERT INTO workflow_steps (
                        step_id, workflow_id, step_number, step_kind, step_name,
                        status, input_digest, output_digest, error_code,
                        attempt_count, started_at, finished_at, created_at, updated_at,
                        step_key, depends_on_json, dependency_state
                    ) VALUES (?, ?, ?, ?, ?, 'pending', ?, NULL, NULL, 0, NULL, NULL, ?, ?, ?, ?, ?)
                    """,
                    (
                        str(uuid4()), str(workflow_id), number, kind, name,
                        input_digest, now, now, step_key,
                        json.dumps(dependencies, ensure_ascii=False, separators=(",", ":")),
                        "ready" if not dependencies else "pending",
                    ),
                )
        return workflow_id

    def _refresh_dependency_states(
        self, connection: sqlite3.Connection, workflow_id: UUID
    ) -> None:
        """Recompute persisted dependency readiness and propagate blocked descendants."""
        rows = connection.execute(
            """
            SELECT step_key, depends_on_json, status
            FROM workflow_steps WHERE workflow_id = ? ORDER BY step_number
            """,
            (str(workflow_id),),
        ).fetchall()
        by_key = {row["step_key"]: row for row in rows}
        states = {key: "pending" for key in by_key}
        for _ in range(max(1, len(rows))):
            changed = False
            for row in rows:
                key = row["step_key"]
                dependencies = json.loads(row["depends_on_json"])
                if any(
                    dependency not in by_key
                    or by_key[dependency]["status"] in {
                        "failed", "unknown_outcome", "cancelled"
                    }
                    or states.get(dependency) == "blocked"
                    for dependency in dependencies
                ):
                    target = "blocked"
                elif all(
                    by_key[dependency]["status"] == "succeeded"
                    for dependency in dependencies
                ):
                    target = "ready"
                else:
                    target = "pending"
                if states[key] != target:
                    states[key] = target
                    changed = True
            if not changed:
                break
        for key, target in states.items():
            connection.execute(
                """
                UPDATE workflow_steps SET dependency_state = ?
                WHERE workflow_id = ? AND step_key = ?
                """,
                (target, str(workflow_id), key),
            )

    def start_run(self, workflow_id: UUID, *, lease: WorkerLease | None = None) -> None:
        now = self._now()
        with self._connection() as connection:
            connection.execute("BEGIN IMMEDIATE")
            self._assert_lease(connection, workflow_id, lease, now)
            cursor = connection.execute(
                """
                UPDATE workflow_runs SET status = 'running', last_error_code = NULL, updated_at = ?
                WHERE workflow_id = ? AND status IN ('queued', 'paused')
                """,
                (now, str(workflow_id)),
            )
            if cursor.rowcount != 1:
                raise WorkflowRecoveryError("Workflow is not eligible to start or resume")

    def start_step(
        self, workflow_id: UUID, step_number: int | str, *,
        lease: WorkerLease | None = None
    ) -> StepAttempt:
        """Start by persisted identity (string) or legacy numeric position."""
        now = self._now()
        with self._connection() as connection:
            connection.execute("BEGIN IMMEDIATE")
            run = connection.execute(
                "SELECT status FROM workflow_runs WHERE workflow_id = ?",
                (str(workflow_id),),
            ).fetchone()
            if run is None:
                raise LookupError("Workflow not found")
            if run["status"] == "recovery_required":
                raise RecoveryRequired("Workflow requires reconciliation before resuming")
            if run["status"] != "running":
                raise WorkflowRecoveryError("Workflow is not running")
            self._assert_lease(connection, workflow_id, lease, now)

            self._refresh_dependency_states(connection, workflow_id)
            if isinstance(step_number, str):
                step = connection.execute(
                    """
                    SELECT step_id, step_number, step_key, depends_on_json,
                           dependency_state, status, attempt_count
                    FROM workflow_steps WHERE workflow_id = ? AND step_key = ?
                    """,
                    (str(workflow_id), step_number),
                ).fetchone()
            else:
                step = connection.execute(
                    """
                    SELECT step_id, step_number, step_key, depends_on_json,
                           dependency_state, status, attempt_count
                    FROM workflow_steps WHERE workflow_id = ? AND step_number = ?
                    """,
                    (str(workflow_id), step_number),
                ).fetchone()
            if step is None:
                raise LookupError("Workflow step not found")
            if step["status"] == "unknown_outcome":
                raise RecoveryRequired("Step outcome must be reconciled before resuming")
            if step["status"] not in {"pending", "retry_wait"}:
                raise WorkflowRecoveryError("Step is not eligible to start")
            if step["dependency_state"] == "blocked":
                raise WorkflowRecoveryError("Workflow step is blocked by a failed dependency")
            dependencies = json.loads(step["depends_on_json"])
            dependency_rows = connection.execute(
                "SELECT step_key, status FROM workflow_steps WHERE workflow_id = ?",
                (str(workflow_id),),
            ).fetchall()
            dependency_statuses = {row["step_key"]: row["status"] for row in dependency_rows}
            if any(dependency_statuses.get(key) != "succeeded" for key in dependencies):
                raise WorkflowRecoveryError(
                    "Earlier workflow steps or declared dependencies must succeed first"
                )

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
                SET status = 'running', dependency_state = 'ready',
                    attempt_count = ?, started_at = ?,
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
                (step["step_number"], now, str(workflow_id)),
            )
            return StepAttempt(
                attempt_id, step["step_id"], step["step_number"],
                attempt_number, step["step_key"]
            )

    def complete_step(
        self,
        workflow_id: UUID,
        attempt: StepAttempt,
        output_digest: str,
        *,
        lease: WorkerLease | None = None,
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
            self._assert_lease(connection, workflow_id, lease, now)

            step = connection.execute(
                """
                SELECT step_id, step_key, step_number, status FROM workflow_steps
                WHERE workflow_id = ? AND step_id = ?
                """,
                (str(workflow_id), attempt.step_id),
            ).fetchone()
            if (
                step is None
                or step["step_key"] != attempt.step_key
                or step["status"] != "running"
            ):
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
                f"{previous_digest}:{attempt.step_key}:{output_digest}".encode()
            ).hexdigest()
            checkpoint_id = str(uuid4())
            connection.execute(
                """
                INSERT INTO workflow_checkpoints (
                    checkpoint_id, workflow_id, checkpoint_version,
                    step_number, state_digest, created_at, step_key
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    checkpoint_id, str(workflow_id), version,
                    attempt.step_number, state_digest, now, attempt.step_key,
                ),
            )
            connection.execute(
                "UPDATE workflow_runs SET updated_at = ? WHERE workflow_id = ?",
                (now, str(workflow_id)),
            )
            self._refresh_dependency_states(connection, workflow_id)
            return WorkflowCheckpoint(
                checkpoint_id, str(workflow_id), version,
                attempt.step_number, state_digest, now, attempt.step_key,
            )

    def fail_step(
        self,
        workflow_id: UUID,
        attempt: StepAttempt,
        error_code: str,
        *,
        unknown_outcome: bool = False,
        lease: WorkerLease | None = None,
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
            self._assert_lease(connection, workflow_id, lease, now)
            step = connection.execute(
                """
                SELECT step_id, step_key, status FROM workflow_steps
                WHERE workflow_id = ? AND step_id = ?
                """,
                (str(workflow_id), attempt.step_id),
            ).fetchone()
            if (
                step is None
                or step["step_key"] != attempt.step_key
                or step["status"] != "running"
            ):
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
            self._refresh_dependency_states(connection, workflow_id)

    def mark_interrupted(
        self, workflow_id: UUID, *, lease: WorkerLease | None = None
    ) -> int:
        """Classify active attempts; only known-safe steps become retryable."""
        now = self._now()
        with self._connection() as connection:
            connection.execute("BEGIN IMMEDIATE")
            self._assert_lease(connection, workflow_id, lease, now)
            rows = connection.execute(
                """
                SELECT step_id, step_number, step_key, step_kind FROM workflow_steps
                WHERE workflow_id = ? AND status = 'running'
                """,
                (str(workflow_id),),
            ).fetchall()
            if not rows:
                connection.execute(
                    """
                    UPDATE workflow_runs
                    SET status = 'paused', last_error_code = 'worker_interrupted_before_step',
                        updated_at = ?
                    WHERE workflow_id = ? AND status = 'running'
                    """,
                    (now, str(workflow_id)),
                )
                return 0

            has_unknown_outcome = False
            for row in rows:
                safe_to_retry = row["step_kind"] in {"provider_selection", "safe_tool"}
                attempt_status = "failed" if safe_to_retry else "unknown_outcome"
                step_status = "retry_wait" if safe_to_retry else "unknown_outcome"
                if not safe_to_retry:
                    has_unknown_outcome = True
                connection.execute(
                    """
                    UPDATE workflow_step_attempts
                    SET status = ?, error_code = 'worker_interrupted', finished_at = ?
                    WHERE step_id = ? AND status = 'running'
                    """,
                    (attempt_status, now, row["step_id"]),
                )
                connection.execute(
                    """
                    UPDATE workflow_steps
                    SET status = ?, error_code = 'worker_interrupted',
                        finished_at = ?, updated_at = ?
                    WHERE step_id = ? AND status = 'running'
                    """,
                    (step_status, now, now, row["step_id"]),
                )
            run_status = "recovery_required" if has_unknown_outcome else "paused"
            error_code = "worker_interrupted" if has_unknown_outcome else "safe_step_interrupted"
            connection.execute(
                """
                UPDATE workflow_runs
                SET status = ?, last_error_code = ?, updated_at = ?
                WHERE workflow_id = ? AND status = 'running'
                """,
                (run_status, error_code, now, str(workflow_id)),
            )
            self._refresh_dependency_states(connection, workflow_id)
            return len(rows)

    def resolve_unknown_step(
        self,
        workflow_id: UUID,
        step_number: int | str,
        outcome: str,
        *,
        output_digest: str | None = None,
        owner_user_id: str | None = None,
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
                "SELECT request_digest, status FROM workflow_runs WHERE workflow_id = ? AND (? IS NULL OR owner_user_id = ?)",
                (str(workflow_id), owner_user_id, owner_user_id),
            ).fetchone()
            if run is None:
                raise LookupError("Workflow not found")
            if run["status"] != "recovery_required":
                raise WorkflowRecoveryError("Workflow is not awaiting recovery")
            if isinstance(step_number, str):
                step = connection.execute(
                    """
                    SELECT step_id, step_key, step_number, status FROM workflow_steps
                    WHERE workflow_id = ? AND step_key = ?
                    """,
                    (str(workflow_id), step_number),
                ).fetchone()
            else:
                step = connection.execute(
                    """
                    SELECT step_id, step_key, step_number, status FROM workflow_steps
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
                    f"{previous_digest}:{step['step_key']}:{output_digest}".encode()
                ).hexdigest()
                checkpoint_id = str(uuid4())
                connection.execute(
                    """
                    INSERT INTO workflow_checkpoints (
                        checkpoint_id, workflow_id, checkpoint_version,
                        step_number, state_digest, created_at, step_key
                    ) VALUES (?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        checkpoint_id, str(workflow_id), version,
                        step["step_number"], state_digest, now, step["step_key"],
                    ),
                )
                checkpoint = WorkflowCheckpoint(
                    checkpoint_id, str(workflow_id), version,
                    step["step_number"], state_digest, now, step["step_key"]
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
            self._refresh_dependency_states(connection, workflow_id)
            return checkpoint

    def finish_run(
        self, workflow_id: UUID, status: str, *, lease: WorkerLease | None = None
    ) -> None:
        if status not in {"succeeded", "failed", "cancelled"}:
            raise WorkflowRecoveryError("Unsupported terminal workflow status")
        now = self._now()
        with self._connection() as connection:
            connection.execute("BEGIN IMMEDIATE")
            self._assert_lease(connection, workflow_id, lease, now)
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
            if status == "cancelled":
                connection.execute(
                    """
                    UPDATE workflow_step_attempts
                    SET status = 'cancelled', error_code = 'cancelled', finished_at = ?
                    WHERE step_id IN (
                        SELECT step_id FROM workflow_steps
                        WHERE workflow_id = ? AND status = 'running'
                    ) AND status = 'running'
                    """,
                    (now, str(workflow_id)),
                )
                connection.execute(
                    """
                    UPDATE workflow_steps
                    SET status = 'cancelled', error_code = 'cancelled',
                        finished_at = COALESCE(finished_at, ?), updated_at = ?
                    WHERE workflow_id = ?
                      AND status IN ('running', 'pending', 'retry_wait')
                    """,
                    (now, now, str(workflow_id)),
                )
            cursor = connection.execute(
                """
                UPDATE workflow_runs SET status = ?, updated_at = ?
                WHERE workflow_id = ? AND status = 'running'
                """,
                (status, now, str(workflow_id)),
            )
            if cursor.rowcount != 1:
                raise WorkflowRecoveryError("Workflow is not running")
            # A cancelled in-flight prerequisite must immediately block every
            # descendant before terminal state becomes externally observable.
            self._refresh_dependency_states(connection, workflow_id)

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
            row["step_key"],
        )

    def queue_resume(
        self,
        workflow_id: UUID,
        *,
        owner_user_id: str,
        request_digest: str,
        definition_version: int = 1,
    ) -> dict[str, str]:
        """Atomically enqueue a validated resume; the worker remains the executor."""
        self._validate_digest(request_digest, "Supplied request digest")
        now = self._now()
        with self._connection() as connection:
            connection.execute("BEGIN IMMEDIATE")
            run = connection.execute(
                """
                SELECT task_id, status, request_digest, definition_version
                FROM workflow_runs
                WHERE workflow_id = ? AND owner_user_id = ?
                """,
                (str(workflow_id), owner_user_id),
            ).fetchone()
            if run is None or run["task_id"] is None:
                raise LookupError("Workflow not found")
            if run["status"] != "paused":
                raise WorkflowRecoveryError("Workflow is not awaiting a safe resume")
            if run["request_digest"] != request_digest:
                raise WorkflowRecoveryError("Workflow request does not match the stored request")
            if run["definition_version"] != definition_version:
                raise WorkflowRecoveryError("Workflow definition changed; replan before resuming")

            blocked = connection.execute(
                """
                SELECT 1 FROM workflow_steps
                WHERE workflow_id = ?
                  AND (
                    status IN ('failed', 'unknown_outcome', 'cancelled', 'running')
                    OR dependency_state = 'blocked'
                  )
                LIMIT 1
                """,
                (str(workflow_id),),
            ).fetchone()
            if blocked is not None:
                raise WorkflowRecoveryError("Workflow has a step that is not safe to resume")

            task_cursor = connection.execute(
                """
                UPDATE tasks SET status = 'queued', updated_at = ?
                WHERE task_id = ? AND status = 'waiting_approval'
                """,
                (now, run["task_id"]),
            )
            if task_cursor.rowcount != 1:
                raise WorkflowRecoveryError("Workflow job is not awaiting a resume")

            execution_cursor = connection.execute(
                """
                UPDATE worker_executions
                SET error_code = NULL, result_json = NULL, finished_at = NULL,
                    next_attempt_at = NULL
                WHERE task_id = ?
                """,
                (run["task_id"],),
            )
            if execution_cursor.rowcount != 1:
                raise WorkflowRecoveryError("Workflow worker execution record is missing")

            run_cursor = connection.execute(
                """
                UPDATE workflow_runs
                SET last_error_code = 'resume_queued', updated_at = ?
                WHERE workflow_id = ? AND status = 'paused'
                """,
                (now, str(workflow_id)),
            )
            if run_cursor.rowcount != 1:
                raise WorkflowRecoveryError("Workflow state changed while queuing resume")

        return {
            "workflow_id": str(workflow_id),
            "task_id": str(run["task_id"]),
            "status": "queued",
        }

    def resume_decision(
        self,
        workflow_id: UUID,
        supplied_request_digest: str,
        *,
        definition_version: int = 1,
        owner_user_id: str | None = None,
    ) -> ResumeDecision:
        """Return an identity-addressed safe next action without executing a step."""
        self._validate_digest(supplied_request_digest, "Supplied request digest")
        with self._connection() as connection:
            connection.execute("BEGIN IMMEDIATE")
            run = connection.execute(
                "SELECT * FROM workflow_runs WHERE workflow_id = ? AND (? IS NULL OR owner_user_id = ?)",
                (str(workflow_id), owner_user_id, owner_user_id),
            ).fetchone()
            if run is None:
                raise LookupError("Workflow not found")
            self._refresh_dependency_states(connection, workflow_id)
            checkpoint = connection.execute(
                """
                SELECT checkpoint_version, step_number, step_key FROM workflow_checkpoints
                WHERE workflow_id = ? ORDER BY checkpoint_version DESC LIMIT 1
                """,
                (str(workflow_id),),
            ).fetchone()
            checkpoint_version = checkpoint["checkpoint_version"] if checkpoint else None
            if run["status"] == "recovery_required":
                unknown = connection.execute(
                    """
                    SELECT step_number, step_key FROM workflow_steps
                    WHERE workflow_id = ? AND status = 'unknown_outcome'
                    ORDER BY step_number LIMIT 1
                    """,
                    (str(workflow_id),),
                ).fetchone()
                return ResumeDecision(
                    "reconcile",
                    unknown["step_number"] if unknown else None,
                    checkpoint_version,
                    run["last_error_code"] or "step_outcome_unknown",
                    unknown["step_key"] if unknown else None,
                )
            if run["status"] in {"succeeded", "failed", "cancelled"}:
                return ResumeDecision("terminal", None, checkpoint_version, run["status"])
            if run["status"] == "waiting_approval":
                return ResumeDecision("waiting_approval", None, checkpoint_version, None)
            if run["definition_version"] != definition_version:
                return ResumeDecision(
                    "replan", None, checkpoint_version, "definition_version_mismatch"
                )
            if run["request_digest"] != supplied_request_digest:
                return ResumeDecision(
                    "request_input", None, checkpoint_version, "request_digest_mismatch"
                )

            rows = connection.execute(
                """
                SELECT step_number, step_key, depends_on_json, dependency_state, status
                FROM workflow_steps WHERE workflow_id = ? ORDER BY step_number
                """,
                (str(workflow_id),),
            ).fetchall()
            active = next((row for row in rows if row["status"] == "running"), None)
            if active is not None:
                return ResumeDecision(
                    "in_progress", active["step_number"], checkpoint_version,
                    None, active["step_key"],
                )

            failed = next(
                (
                    row for row in rows
                    if row["status"] in {"failed", "unknown_outcome", "cancelled"}
                ),
                None,
            )
            if failed is not None:
                reason = {
                    "failed": "step_failed",
                    "unknown_outcome": "step_outcome_unknown",
                    "cancelled": "step_cancelled",
                }[failed["status"]]
                return ResumeDecision(
                    "reconcile", failed["step_number"], checkpoint_version,
                    reason, failed["step_key"],
                )

            by_key = {row["step_key"]: row for row in rows}
            eligible = []
            pending = []
            for row in rows:
                if row["status"] not in {"pending", "retry_wait"}:
                    continue
                pending.append(row)
                dependencies = json.loads(row["depends_on_json"])
                if (
                    row["dependency_state"] != "blocked"
                    and all(
                        dependency in by_key
                        and by_key[dependency]["status"] == "succeeded"
                        for dependency in dependencies
                    )
                ):
                    eligible.append(row)
            if eligible:
                next_step = eligible[0]
                return ResumeDecision(
                    "resume", next_step["step_number"], checkpoint_version,
                    None, next_step["step_key"],
                )
            if pending:
                blocked = next(
                    (row for row in pending if row["dependency_state"] == "blocked"),
                    pending[0],
                )
                return ResumeDecision(
                    "blocked", blocked["step_number"], checkpoint_version,
                    "dependencies_not_satisfied", blocked["step_key"],
                )
            return ResumeDecision("finish", None, checkpoint_version, "all_steps_succeeded")

    def delete_encrypted_payload(
        self, workflow_id: UUID, *, owner_user_id: str
    ) -> bool:
        """Delete retained ciphertext after a terminal outcome for its owner."""
        with self._connection() as connection:
            cursor = connection.execute(
                """
                DELETE FROM workflow_payloads
                WHERE workflow_id = ? AND owner_user_id = ?
                  AND EXISTS (
                    SELECT 1 FROM workflow_runs
                    WHERE workflow_runs.workflow_id = workflow_payloads.workflow_id
                      AND workflow_runs.status IN ('succeeded', 'failed', 'cancelled')
                  )
                """,
                (str(workflow_id), owner_user_id),
            )
            return cursor.rowcount == 1

    def request_cancellation(
        self, workflow_id: UUID, *, owner_user_id: str
    ) -> dict[str, str]:
        """Cancel queued work or request cooperative cancellation of a running workflow."""
        now = self._now()
        with self._connection() as connection:
            connection.execute("BEGIN IMMEDIATE")
            run = connection.execute(
                """
                SELECT workflow_id, task_id, status FROM workflow_runs
                WHERE workflow_id = ? AND owner_user_id = ?
                """,
                (str(workflow_id), owner_user_id),
            ).fetchone()
            if run is None or run["task_id"] is None:
                raise LookupError("Workflow not found")
            status = run["status"]
            task_id = run["task_id"]
            if status in {"succeeded", "failed", "cancelled"}:
                return {"workflow_id": str(workflow_id), "status": status}
            if status in {"queued", "paused"}:
                # A paused workflow may have a queued resume request. Fence both
                # that queued job and an unclaimed recovery-waiting job atomically.
                task_cursor = connection.execute(
                    """
                    UPDATE tasks SET status = 'cancelled', updated_at = ?
                    WHERE task_id = ? AND status IN ('queued', 'running', 'waiting_approval')
                    """,
                    (now, task_id),
                )
                if task_cursor.rowcount != 1:
                    raise WorkflowRecoveryError("Task state changed during cancellation")
                run_cursor = connection.execute(
                    """
                    UPDATE workflow_runs SET status = 'cancelled', last_error_code = NULL,
                        updated_at = ?
                    WHERE workflow_id = ? AND status = ?
                    """,
                    (now, str(workflow_id), status),
                )
                if run_cursor.rowcount != 1:
                    raise WorkflowRecoveryError("Workflow state changed during cancellation")
                connection.execute(
                    """
                    UPDATE workflow_steps
                    SET status = 'cancelled', error_code = 'cancelled',
                        finished_at = COALESCE(finished_at, ?), updated_at = ?
                    WHERE workflow_id = ? AND status IN ('pending', 'retry_wait')
                    """,
                    (now, now, str(workflow_id)),
                )
                self._refresh_dependency_states(connection, workflow_id)
                connection.execute(
                    "DELETE FROM workflow_payloads WHERE workflow_id = ?",
                    (str(workflow_id),),
                )
            elif status == "running":
                # Persist cancellation intent without prematurely terminalizing the
                # task. The current worker can observe the request and finalize it;
                # if it crashes, stale-worker recovery can still reconcile the run.
                cursor = connection.execute(
                    """
                    UPDATE worker_executions SET error_code = 'cancellation_requested'
                    WHERE task_id = ? AND EXISTS (
                        SELECT 1 FROM tasks WHERE task_id = ? AND status = 'running'
                    )
                    """,
                    (task_id, task_id),
                )
                if cursor.rowcount != 1:
                    raise WorkflowRecoveryError("Running task state changed during cancellation")
            else:
                raise WorkflowRecoveryError("Workflow cannot be cancelled in its current state")
            if status in {"queued", "paused"}:
                connection.execute(
                    "UPDATE idempotency_records SET status = 'failed' WHERE task_id = ? AND status IN ('accepted', 'running')",
                    (task_id,),
                )
            return {
                "workflow_id": str(workflow_id),
                "task_id": task_id,
                "status": "cancelled" if status in {"queued", "paused"} else "cancellation_requested",
            }

    def replace_encrypted_payload(
        self,
        workflow_id: UUID,
        *,
        owner_user_id: str,
        task_id: str,
        payload_envelope: dict[str, object],
    ) -> bool:
        """Atomically replace an owner's encrypted envelope without exposing plaintext."""
        version = payload_envelope.get("version")
        nonce_b64 = payload_envelope.get("nonce_b64")
        ciphertext_b64 = payload_envelope.get("ciphertext_b64")
        if (
            not isinstance(version, int) or version < 1
            or not isinstance(nonce_b64, str) or not nonce_b64
            or not isinstance(ciphertext_b64, str) or not ciphertext_b64
        ):
            raise WorkflowRecoveryError("Encrypted workflow payload envelope is invalid")
        with self._connection() as connection:
            cursor = connection.execute(
                """
                UPDATE workflow_payloads
                SET envelope_version = ?, nonce_b64 = ?, ciphertext_b64 = ?,
                    created_at = ?
                WHERE workflow_id = ? AND task_id = ? AND owner_user_id = ?
                """,
                (
                    version, nonce_b64, ciphertext_b64, self._now(),
                    str(workflow_id), task_id, owner_user_id,
                ),
            )
            return cursor.rowcount == 1

    def get_encrypted_payload(
        self, workflow_id: UUID, *, owner_user_id: str
    ) -> dict[str, object] | None:
        """Return encrypted bytes only for the matching owner; never decrypt here."""
        with self._connection() as connection:
            row = connection.execute(
                """
                SELECT workflow_id, task_id, owner_user_id, envelope_version,
                       nonce_b64, ciphertext_b64, created_at
                FROM workflow_payloads
                WHERE workflow_id = ? AND owner_user_id = ?
                """,
                (str(workflow_id), owner_user_id),
            ).fetchone()
        if row is None:
            return None
        return {
            "workflow_id": row["workflow_id"],
            "task_id": row["task_id"],
            "owner_user_id": row["owner_user_id"],
            "version": row["envelope_version"],
            "nonce_b64": row["nonce_b64"],
            "ciphertext_b64": row["ciphertext_b64"],
            "created_at": row["created_at"],
        }

    def list_runs(
        self, *, owner_user_id: str, limit: int = 50
    ) -> list[dict[str, object]]:
        """List bounded workflow metadata for one owner without exposing payloads."""
        if not owner_user_id.strip():
            raise WorkflowRecoveryError("Workflow owner is required")
        if not 1 <= limit <= 100:
            raise WorkflowRecoveryError("Workflow list limit must be between 1 and 100")
        with self._connection() as connection:
            rows = connection.execute(
                """
                SELECT workflow_id FROM workflow_runs
                WHERE owner_user_id = ?
                ORDER BY updated_at DESC, created_at DESC
                LIMIT ?
                """,
                (owner_user_id, limit),
            ).fetchall()
        workflows = [
            self.get_run(UUID(row["workflow_id"]), owner_user_id=owner_user_id)
            for row in rows
        ]
        return [workflow for workflow in workflows if workflow is not None]

    def get_run(self, workflow_id: UUID, *, owner_user_id: str | None = None) -> dict[str, object] | None:
        with self._connection() as connection:
            run = connection.execute(
                "SELECT * FROM workflow_runs WHERE workflow_id = ? AND (? IS NULL OR owner_user_id = ?)",
                (str(workflow_id), owner_user_id, owner_user_id),
            ).fetchone()
            if run is None:
                return None
            steps = connection.execute(
                """
                SELECT step_number, step_key, depends_on_json, dependency_state,
                       step_kind, step_name, status, input_digest,
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
            "steps": [
                {
                    **dict(row),
                    "depends_on": json.loads(row["depends_on_json"]),
                }
                for row in steps
            ],
            "stored_request": False,
            "stored_step_payloads": False,
            "stored_step_outputs": False,
        }
