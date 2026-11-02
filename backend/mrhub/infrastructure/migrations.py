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
        "agent_run_owner_scope",
        (
            "ALTER TABLE agent_runs ADD COLUMN owner_user_id TEXT REFERENCES auth_users(user_id) ON DELETE SET NULL",
            "CREATE INDEX IF NOT EXISTS idx_agent_runs_owner_created ON agent_runs(owner_user_id, created_at)",
        ),
    ),
    Migration.build(
        7,
        "encrypted_workflow_execution_payloads",
        (
            """CREATE TABLE IF NOT EXISTS workflow_payloads (
                workflow_id TEXT PRIMARY KEY REFERENCES workflow_runs(workflow_id) ON DELETE CASCADE,
                task_id TEXT NOT NULL UNIQUE REFERENCES tasks(task_id) ON DELETE CASCADE,
                owner_user_id TEXT NOT NULL REFERENCES auth_users(user_id) ON DELETE CASCADE,
                envelope_version INTEGER NOT NULL CHECK (envelope_version > 0),
                nonce_b64 TEXT NOT NULL,
                ciphertext_b64 TEXT NOT NULL,
                created_at TEXT NOT NULL
            )""",
            "CREATE INDEX IF NOT EXISTS idx_workflow_payloads_task ON workflow_payloads(task_id)",
        ),
    ),
    Migration.build(
        8,
        "worker_process_heartbeats",
        (
            """CREATE TABLE IF NOT EXISTS worker_instances (
                instance_id TEXT PRIMARY KEY,
                process_id INTEGER NOT NULL,
                started_at TEXT NOT NULL,
                heartbeat_at TEXT NOT NULL,
                stopped_at TEXT,
                status TEXT NOT NULL CHECK (status IN ('running', 'stopped'))
            )""",
            "CREATE INDEX IF NOT EXISTS idx_worker_instances_heartbeat ON worker_instances(status, heartbeat_at)",
        ),
    ),
    Migration.build(
        9,
        "capability_discovery_catalog",
        (
            """CREATE TABLE IF NOT EXISTS capability_candidates (
                candidate_id TEXT PRIMARY KEY,
                canonical_url TEXT NOT NULL UNIQUE,
                display_name TEXT NOT NULL CHECK (length(display_name) BETWEEN 1 AND 160),
                summary TEXT NOT NULL CHECK (length(summary) <= 1000),
                source_kind TEXT NOT NULL CHECK (source_kind IN (
                    'github_repository', 'documentation', 'package', 'api', 'other'
                )),
                license_id TEXT NOT NULL DEFAULT 'unknown',
                integration_type TEXT NOT NULL CHECK (integration_type IN (
                    'connector', 'skill', 'python_package', 'http_api', 'adapter', 'manual'
                )),
                status TEXT NOT NULL CHECK (status IN (
                    'discovered', 'reviewing', 'approved', 'rejected', 'disabled'
                )),
                capabilities_json TEXT NOT NULL,
                evidence_json TEXT NOT NULL,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )""",
            "CREATE INDEX IF NOT EXISTS idx_capability_candidates_status_updated ON capability_candidates(status, updated_at)",
        ),
    ),
    Migration.build(
        10,
        "owner_scoped_memory_and_fts5",
        (
            """CREATE TABLE IF NOT EXISTS memory_entries (
                memory_id TEXT PRIMARY KEY,
                owner_user_id TEXT NOT NULL REFERENCES auth_users(user_id) ON DELETE CASCADE,
                scope TEXT NOT NULL DEFAULT 'private' CHECK (scope = 'private'),
                category TEXT NOT NULL CHECK (length(category) BETWEEN 1 AND 80),
                content TEXT NOT NULL CHECK (length(content) BETWEEN 1 AND 2000),
                provenance TEXT NOT NULL CHECK (length(provenance) BETWEEN 1 AND 300),
                confidence REAL NOT NULL DEFAULT 0.7 CHECK (confidence >= 0.0 AND confidence <= 1.0),
                verification_status TEXT NOT NULL CHECK (
                    verification_status IN ('user_authored', 'user_approved')
                ),
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                expires_at TEXT
            )""",
            "CREATE INDEX IF NOT EXISTS idx_memory_owner_updated ON memory_entries(owner_user_id, updated_at)",
            """CREATE VIRTUAL TABLE IF NOT EXISTS memory_entries_fts USING fts5(
                memory_id UNINDEXED,
                owner_user_id UNINDEXED,
                category,
                content,
                provenance,
                tokenize='unicode61'
            )""",
            """CREATE TRIGGER IF NOT EXISTS memory_entries_ai AFTER INSERT ON memory_entries BEGIN
                INSERT INTO memory_entries_fts(memory_id, owner_user_id, category, content, provenance)
                VALUES (new.memory_id, new.owner_user_id, new.category, new.content, new.provenance);
            END""",
            """CREATE TRIGGER IF NOT EXISTS memory_entries_au AFTER UPDATE ON memory_entries BEGIN
                DELETE FROM memory_entries_fts WHERE memory_id = old.memory_id;
                INSERT INTO memory_entries_fts(memory_id, owner_user_id, category, content, provenance)
                VALUES (new.memory_id, new.owner_user_id, new.category, new.content, new.provenance);
            END""",
            """CREATE TRIGGER IF NOT EXISTS memory_entries_ad AFTER DELETE ON memory_entries BEGIN
                DELETE FROM memory_entries_fts WHERE memory_id = old.memory_id;
            END""",
        ),
    ),
    Migration.build(
        11,
        "owner_scoped_source_backed_knowledge",
        (
            """CREATE TABLE IF NOT EXISTS knowledge_sources (
                source_id TEXT PRIMARY KEY,
                owner_user_id TEXT NOT NULL REFERENCES auth_users(user_id) ON DELETE CASCADE,
                scope TEXT NOT NULL DEFAULT 'private' CHECK (scope = 'private'),
                source_type TEXT NOT NULL CHECK (source_type = 'user_text'),
                canonical_origin TEXT NOT NULL CHECK (length(canonical_origin) BETWEEN 1 AND 500),
                trust_classification TEXT NOT NULL CHECK (
                    trust_classification IN ('user_supplied', 'user_reviewed')
                ),
                sensitivity_classification TEXT NOT NULL DEFAULT 'private'
                    CHECK (sensitivity_classification = 'private'),
                content_hash TEXT NOT NULL CHECK (length(content_hash) = 64),
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )""",
            "CREATE INDEX IF NOT EXISTS idx_knowledge_sources_owner_created ON knowledge_sources(owner_user_id, created_at)",
            """CREATE TABLE IF NOT EXISTS knowledge_documents (
                document_id TEXT PRIMARY KEY,
                source_id TEXT NOT NULL UNIQUE REFERENCES knowledge_sources(source_id) ON DELETE CASCADE,
                owner_user_id TEXT NOT NULL REFERENCES auth_users(user_id) ON DELETE CASCADE,
                title TEXT NOT NULL CHECK (length(title) BETWEEN 1 AND 200),
                language TEXT NOT NULL DEFAULT 'und',
                content TEXT NOT NULL CHECK (length(content) BETWEEN 1 AND 100000),
                content_hash TEXT NOT NULL CHECK (length(content_hash) = 64),
                version INTEGER NOT NULL DEFAULT 1 CHECK (version > 0),
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )""",
            "CREATE INDEX IF NOT EXISTS idx_knowledge_documents_owner_updated ON knowledge_documents(owner_user_id, updated_at)",
            """CREATE TABLE IF NOT EXISTS knowledge_chunks (
                chunk_id TEXT PRIMARY KEY,
                document_id TEXT NOT NULL REFERENCES knowledge_documents(document_id) ON DELETE CASCADE,
                source_id TEXT NOT NULL REFERENCES knowledge_sources(source_id) ON DELETE CASCADE,
                owner_user_id TEXT NOT NULL REFERENCES auth_users(user_id) ON DELETE CASCADE,
                chunk_index INTEGER NOT NULL CHECK (chunk_index >= 0),
                start_offset INTEGER NOT NULL CHECK (start_offset >= 0),
                end_offset INTEGER NOT NULL CHECK (end_offset >= start_offset),
                content TEXT NOT NULL CHECK (length(content) > 0),
                content_hash TEXT NOT NULL CHECK (length(content_hash) = 64),
                created_at TEXT NOT NULL,
                UNIQUE(document_id, chunk_index)
            )""",
            "CREATE INDEX IF NOT EXISTS idx_knowledge_chunks_owner_document ON knowledge_chunks(owner_user_id, document_id, chunk_index)",
            """CREATE VIRTUAL TABLE IF NOT EXISTS knowledge_chunks_fts USING fts5(
                chunk_id UNINDEXED,
                document_id UNINDEXED,
                source_id UNINDEXED,
                owner_user_id UNINDEXED,
                title,
                content,
                tokenize='unicode61'
            )""",
            """CREATE TRIGGER IF NOT EXISTS knowledge_chunks_ai AFTER INSERT ON knowledge_chunks BEGIN
                INSERT INTO knowledge_chunks_fts(
                    chunk_id, document_id, source_id, owner_user_id, title, content
                ) VALUES (
                    new.chunk_id, new.document_id, new.source_id, new.owner_user_id,
                    (SELECT title FROM knowledge_documents WHERE document_id = new.document_id),
                    new.content
                );
            END""",
            """CREATE TRIGGER IF NOT EXISTS knowledge_chunks_au AFTER UPDATE ON knowledge_chunks BEGIN
                DELETE FROM knowledge_chunks_fts WHERE chunk_id = old.chunk_id;
                INSERT INTO knowledge_chunks_fts(
                    chunk_id, document_id, source_id, owner_user_id, title, content
                ) VALUES (
                    new.chunk_id, new.document_id, new.source_id, new.owner_user_id,
                    (SELECT title FROM knowledge_documents WHERE document_id = new.document_id),
                    new.content
                );
            END""",
            """CREATE TRIGGER IF NOT EXISTS knowledge_chunks_ad AFTER DELETE ON knowledge_chunks BEGIN
                DELETE FROM knowledge_chunks_fts WHERE chunk_id = old.chunk_id;
            END""",
        ),
    ),
    Migration.build(
        12,
        "owner_scoped_content_drafts_and_versions",
        (
            """CREATE TABLE IF NOT EXISTS content_drafts (
                draft_id TEXT PRIMARY KEY,
                owner_user_id TEXT NOT NULL REFERENCES auth_users(user_id) ON DELETE CASCADE,
                platform TEXT NOT NULL CHECK (platform IN ('instagram', 'telegram', 'generic')),
                content_type TEXT NOT NULL CHECK (
                    content_type IN ('caption', 'script', 'reel_script', 'post_text', 'video_brief')
                ),
                title TEXT NOT NULL CHECK (length(title) BETWEEN 1 AND 200),
                body TEXT NOT NULL CHECK (length(body) BETWEEN 1 AND 20000),
                hashtags_json TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'draft' CHECK (
                    status IN ('draft', 'approved', 'archived')
                ),
                content_hash TEXT NOT NULL CHECK (length(content_hash) = 64),
                version INTEGER NOT NULL DEFAULT 1 CHECK (version > 0),
                approved_by TEXT REFERENCES auth_users(user_id) ON DELETE SET NULL,
                approved_at TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                CHECK (
                    (status = 'approved' AND approved_by IS NOT NULL AND approved_at IS NOT NULL)
                    OR (status <> 'approved' AND approved_by IS NULL AND approved_at IS NULL)
                )
            )""",
            "CREATE UNIQUE INDEX IF NOT EXISTS uq_content_drafts_owner_hash ON content_drafts(owner_user_id, content_hash)",
            "CREATE INDEX IF NOT EXISTS idx_content_drafts_owner_updated ON content_drafts(owner_user_id, updated_at)",
            """CREATE TABLE IF NOT EXISTS content_draft_versions (
                version_id TEXT PRIMARY KEY,
                draft_id TEXT NOT NULL REFERENCES content_drafts(draft_id) ON DELETE CASCADE,
                owner_user_id TEXT NOT NULL REFERENCES auth_users(user_id) ON DELETE CASCADE,
                version_number INTEGER NOT NULL CHECK (version_number > 0),
                platform TEXT NOT NULL CHECK (platform IN ('instagram', 'telegram', 'generic')),
                content_type TEXT NOT NULL CHECK (
                    content_type IN ('caption', 'script', 'reel_script', 'post_text', 'video_brief')
                ),
                title TEXT NOT NULL CHECK (length(title) BETWEEN 1 AND 200),
                body TEXT NOT NULL CHECK (length(body) BETWEEN 1 AND 20000),
                hashtags_json TEXT NOT NULL,
                content_hash TEXT NOT NULL CHECK (length(content_hash) = 64),
                changed_by TEXT NOT NULL REFERENCES auth_users(user_id),
                created_at TEXT NOT NULL,
                UNIQUE(draft_id, version_number)
            )""",
            "CREATE INDEX IF NOT EXISTS idx_content_draft_versions_owner_draft ON content_draft_versions(owner_user_id, draft_id, version_number)",
        ),
    ),
    Migration.build(
        13,
        "owner_scoped_content_media_assets",
        (
            """CREATE TABLE IF NOT EXISTS content_assets (
                asset_id TEXT PRIMARY KEY,
                owner_user_id TEXT NOT NULL REFERENCES auth_users(user_id) ON DELETE CASCADE,
                source_asset_id TEXT REFERENCES content_assets(asset_id) ON DELETE CASCADE,
                original_filename TEXT NOT NULL CHECK (length(original_filename) BETWEEN 1 AND 255),
                media_type TEXT NOT NULL CHECK (
                    media_type IN (
                        'video/mp4', 'video/quicktime', 'image/jpeg', 'image/png',
                        'image/webp', 'audio/mpeg', 'audio/wav'
                    )
                ),
                storage_key TEXT NOT NULL UNIQUE CHECK (length(storage_key) BETWEEN 1 AND 80),
                file_size INTEGER NOT NULL CHECK (file_size BETWEEN 1 AND 100000000),
                content_hash TEXT NOT NULL CHECK (length(content_hash) = 64),
                processing_status TEXT NOT NULL DEFAULT 'stored' CHECK (
                    processing_status IN ('stored', 'processing', 'processed', 'failed')
                ),
                processing_profile TEXT,
                error_code TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )""",
            "CREATE INDEX IF NOT EXISTS idx_content_assets_owner_created ON content_assets(owner_user_id, created_at)",
            "CREATE INDEX IF NOT EXISTS idx_content_assets_source ON content_assets(source_asset_id)",
            "CREATE UNIQUE INDEX IF NOT EXISTS uq_content_assets_one_derivative ON content_assets(source_asset_id) WHERE source_asset_id IS NOT NULL",
        ),
    ),
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
