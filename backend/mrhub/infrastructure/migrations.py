"""Versioned, transactional SQLite schema migrations."""
from __future__ import annotations

import hashlib
import sqlite3
from dataclasses import dataclass


class MigrationError(RuntimeError):
    """Raised when the database schema cannot be migrated safely."""


@dataclass(frozen=True)
class Migration:
    version: int
    name: str
    statements: tuple[str, ...]
    checksum: str

    @classmethod
    def build(cls, version: int, name: str, statements: tuple[str, ...]) -> Migration:
        payload = f"{version}:{name}\n" + "\n".join(statements)
        return cls(
            version=version,
            name=name,
            statements=statements,
            checksum=hashlib.sha256(payload.encode("utf-8")).hexdigest(),
        )


MIGRATIONS = (
    Migration.build(
        1,
        "core_schema",
        (
            """CREATE TABLE IF NOT EXISTS tasks (
                task_id TEXT PRIMARY KEY,
                task_type TEXT NOT NULL,
                status TEXT NOT NULL,
                risk_class TEXT NOT NULL,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                description TEXT NOT NULL
            )""",
            "CREATE INDEX IF NOT EXISTS idx_tasks_created_at ON tasks(created_at)",
            """CREATE TABLE IF NOT EXISTS audit_events (
                event_id TEXT PRIMARY KEY,
                event_type TEXT NOT NULL,
                outcome TEXT NOT NULL,
                subject_type TEXT NOT NULL,
                subject_id TEXT,
                actor_type TEXT NOT NULL,
                actor_id TEXT,
                created_at TEXT NOT NULL,
                metadata_json TEXT NOT NULL
            )""",
            """CREATE TABLE IF NOT EXISTS auth_users (
                user_id TEXT PRIMARY KEY,
                username TEXT NOT NULL UNIQUE,
                salt TEXT NOT NULL,
                password_hash TEXT NOT NULL,
                created_at TEXT NOT NULL
            )""",
            """CREATE TABLE IF NOT EXISTS auth_sessions (
                session_id TEXT PRIMARY KEY,
                user_id TEXT NOT NULL REFERENCES auth_users(user_id) ON DELETE CASCADE,
                token_hash TEXT NOT NULL UNIQUE,
                expires_at TEXT NOT NULL,
                created_at TEXT NOT NULL
            )""",
            "CREATE INDEX IF NOT EXISTS idx_auth_sessions_expiry ON auth_sessions(expires_at)",
            """CREATE TABLE IF NOT EXISTS task_approvals (
                approval_id TEXT PRIMARY KEY,
                task_id TEXT NOT NULL UNIQUE REFERENCES tasks(task_id),
                decision TEXT NOT NULL CHECK (decision IN ('approved', 'rejected')),
                approver_id TEXT NOT NULL REFERENCES auth_users(user_id),
                action_fingerprint TEXT NOT NULL,
                reason TEXT NOT NULL,
                created_at TEXT NOT NULL
            )""",
            "CREATE INDEX IF NOT EXISTS idx_approvals_created_at ON task_approvals(created_at)",
            "CREATE INDEX IF NOT EXISTS idx_audit_created_at ON audit_events(created_at)",
        ),
    ),
    Migration.build(
        2,
        "worker_execution_state",
        (
            """CREATE TABLE IF NOT EXISTS worker_executions (
                task_id TEXT PRIMARY KEY REFERENCES tasks(task_id),
                attempt_count INTEGER NOT NULL DEFAULT 0,
                result_json TEXT,
                error_code TEXT,
                started_at TEXT,
                finished_at TEXT,
                recovered_at TEXT,
                next_attempt_at TEXT
            )""",
        ),
    ),
    Migration.build(
        3,
        "durable_workflow_recovery_primitives",
        (
            """CREATE TABLE IF NOT EXISTS workflow_runs (
                workflow_id TEXT PRIMARY KEY,
                task_id TEXT UNIQUE REFERENCES tasks(task_id) ON DELETE SET NULL,
                status TEXT NOT NULL CHECK (status IN (
                    'queued', 'running', 'paused', 'waiting_approval',
                    'recovery_required', 'succeeded', 'failed', 'cancelled'
                )),
                request_digest TEXT NOT NULL,
                definition_version INTEGER NOT NULL DEFAULT 1,
                current_step INTEGER NOT NULL DEFAULT 0 CHECK (current_step >= 0),
                last_error_code TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )""",
            ("CREATE INDEX IF NOT EXISTS idx_workflow_runs_status_updated "
             "ON workflow_runs(status, updated_at)"),
            """CREATE TABLE IF NOT EXISTS workflow_steps (
                step_id TEXT PRIMARY KEY,
                workflow_id TEXT NOT NULL REFERENCES workflow_runs(workflow_id) ON DELETE CASCADE,
                step_number INTEGER NOT NULL CHECK (step_number > 0),
                step_kind TEXT NOT NULL,
                step_name TEXT NOT NULL,
                status TEXT NOT NULL CHECK (status IN (
                    'pending', 'running', 'succeeded', 'failed',
                    'retry_wait', 'unknown_outcome', 'cancelled'
                )),
                input_digest TEXT,
                output_digest TEXT,
                error_code TEXT,
                attempt_count INTEGER NOT NULL DEFAULT 0 CHECK (attempt_count >= 0),
                started_at TEXT,
                finished_at TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                UNIQUE(workflow_id, step_number)
            )""",
            ("CREATE INDEX IF NOT EXISTS idx_workflow_steps_status "
             "ON workflow_steps(workflow_id, status, step_number)"),
            """CREATE TABLE IF NOT EXISTS workflow_step_attempts (
                attempt_id TEXT PRIMARY KEY,
                step_id TEXT NOT NULL REFERENCES workflow_steps(step_id) ON DELETE CASCADE,
                attempt_number INTEGER NOT NULL CHECK (attempt_number > 0),
                status TEXT NOT NULL CHECK (status IN (
                    'running', 'succeeded', 'failed', 'unknown_outcome', 'cancelled'
                )),
                error_code TEXT,
                started_at TEXT NOT NULL,
                finished_at TEXT,
                UNIQUE(step_id, attempt_number)
            )""",
            """CREATE TABLE IF NOT EXISTS workflow_checkpoints (
                checkpoint_id TEXT PRIMARY KEY,
                workflow_id TEXT NOT NULL REFERENCES workflow_runs(workflow_id) ON DELETE CASCADE,
                checkpoint_version INTEGER NOT NULL CHECK (checkpoint_version > 0),
                step_number INTEGER NOT NULL CHECK (step_number >= 0),
                state_digest TEXT NOT NULL,
                created_at TEXT NOT NULL,
                UNIQUE(workflow_id, checkpoint_version)
            )""",
            """CREATE TABLE IF NOT EXISTS idempotency_records (
                scope TEXT NOT NULL,
                idempotency_key TEXT NOT NULL,
                request_digest TEXT NOT NULL,
                task_id TEXT REFERENCES tasks(task_id) ON DELETE SET NULL,
                workflow_id TEXT REFERENCES workflow_runs(workflow_id) ON DELETE SET NULL,
                status TEXT NOT NULL CHECK (status IN (
                    'accepted', 'running', 'completed', 'failed', 'unknown_outcome'
                )),
                created_at TEXT NOT NULL,
                expires_at TEXT,
                PRIMARY KEY(scope, idempotency_key)
            )""",
            ("CREATE INDEX IF NOT EXISTS idx_idempotency_expiry "
             "ON idempotency_records(expires_at)"),
        ),
    ),
    Migration.build(
        4,
        "workflow_owner_scope",
        (
            """CREATE TABLE IF NOT EXISTS agent_workflows (
                workflow_id TEXT PRIMARY KEY, status TEXT NOT NULL,
                request_digest TEXT NOT NULL, plan_json TEXT NOT NULL,
                steps_json TEXT NOT NULL, created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )""",
        ),
    ),
    Migration.build(
        5,
        "agent_run_history",
        (
            """CREATE TABLE IF NOT EXISTS agent_runs (
                run_id TEXT PRIMARY KEY,
                request_digest TEXT NOT NULL,
                status TEXT NOT NULL,
                provider_name TEXT,
                model_name TEXT,
                plan_json TEXT NOT NULL,
                tool_names_json TEXT NOT NULL,
                executed_tool_count INTEGER NOT NULL,
                error_code TEXT,
                created_at TEXT NOT NULL
            )""",
            "CREATE INDEX IF NOT EXISTS idx_agent_runs_created_at ON agent_runs(created_at)",
        ),
    ),
    Migration.build(
        6,
        "workflow_submission_idempotency",
        (
            """CREATE TABLE IF NOT EXISTS workflow_submission_keys (
                owner_user_id TEXT NOT NULL REFERENCES auth_users(user_id) ON DELETE CASCADE,
                endpoint TEXT NOT NULL,
                idempotency_key TEXT NOT NULL,
                request_digest TEXT NOT NULL,
                state TEXT NOT NULL CHECK (state IN ('reserved', 'bound', 'failed')),
                workflow_id TEXT,
                task_id TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                PRIMARY KEY (owner_user_id, endpoint, idempotency_key),
                CHECK (
                    (state = 'bound' AND workflow_id IS NOT NULL AND task_id IS NOT NULL)
                    OR (state != 'bound')
                )
            )""",
            "CREATE INDEX IF NOT EXISTS idx_workflow_submission_updated ON workflow_submission_keys(updated_at)",
        ),
    )
)


class SchemaMigrator:
    """Applies immutable schema versions and detects migration-history drift."""

    def __init__(self, connection: sqlite3.Connection) -> None:
        self.connection = connection

    def migrate(self) -> list[int]:
        applied_now: list[int] = []
        connection = self.connection
        connection.execute(
            """CREATE TABLE IF NOT EXISTS schema_migrations (
                version INTEGER PRIMARY KEY,
                name TEXT NOT NULL,
                checksum TEXT NOT NULL,
                applied_at TEXT NOT NULL
            )"""
        )
        connection.commit()

        known_versions = {migration.version for migration in MIGRATIONS}
        recorded_versions = {
            row["version"]
            for row in connection.execute("SELECT version FROM schema_migrations")
        }
        unknown_versions = recorded_versions - known_versions
        if unknown_versions:
            raise MigrationError(
                f"Database contains unsupported migration versions: {sorted(unknown_versions)}"
            )

        for migration in MIGRATIONS:
            connection.execute("BEGIN IMMEDIATE")
            try:
                existing = connection.execute(
                    "SELECT name, checksum FROM schema_migrations WHERE version = ?",
                    (migration.version,),
                ).fetchone()
                if existing is not None:
                    if existing["name"] != migration.name or existing["checksum"] != migration.checksum:
                        raise MigrationError(
                            f"Applied migration {migration.version} does not match its recorded checksum"
                        )
                    connection.commit()
                    continue

                later = connection.execute(
                    "SELECT MAX(version) AS version FROM schema_migrations"
                ).fetchone()["version"]
                if later is not None and later >= migration.version:
                    raise MigrationError("Migration history is not strictly increasing")

                for statement in migration.statements:
                    connection.execute(statement)

                if migration.version == 1:
                    self._ensure_column("audit_events", "actor_id", "TEXT")
                elif migration.version == 2:
                    self._ensure_column("worker_executions", "recovered_at", "TEXT")
                    self._ensure_column("worker_executions", "next_attempt_at", "TEXT")
                elif migration.version == 3:
                    self._ensure_column("worker_executions", "lease_owner", "TEXT")
                    self._ensure_column("worker_executions", "lease_expires_at", "TEXT")
                    self._ensure_column("worker_executions", "heartbeat_at", "TEXT")
                    self._ensure_column("worker_executions", "execution_token", "INTEGER NOT NULL DEFAULT 0")
                elif migration.version == 4:
                    self._ensure_column("workflow_runs", "owner_user_id", "TEXT REFERENCES auth_users(user_id) ON DELETE SET NULL")
                    self._ensure_column("agent_workflows", "owner_user_id", "TEXT REFERENCES auth_users(user_id) ON DELETE SET NULL")
                    connection.execute("CREATE INDEX IF NOT EXISTS idx_workflow_runs_owner ON workflow_runs(owner_user_id, created_at)")

                from datetime import UTC, datetime

                connection.execute(
                    """INSERT INTO schema_migrations (version, name, checksum, applied_at)
                    VALUES (?, ?, ?, ?)""",
                    (
                        migration.version,
                        migration.name,
                        migration.checksum,
                        datetime.now(UTC).isoformat(),
                    ),
                )
                connection.commit()
                applied_now.append(migration.version)
            except Exception:
                connection.rollback()
                raise
        return applied_now

    def _ensure_column(self, table: str, column: str, definition: str) -> None:
        columns = {
            row["name"]
            for row in self.connection.execute(f"PRAGMA table_info({table})")
        }
        if column not in columns:
            self.connection.execute(
                f"ALTER TABLE {table} ADD COLUMN {column} {definition}"
            )
