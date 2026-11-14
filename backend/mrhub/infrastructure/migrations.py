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
    Migration.build(
        14,
        "durable_content_publish_schedules",
        (
            """CREATE TABLE IF NOT EXISTS content_publish_schedules (
                schedule_id TEXT PRIMARY KEY,
                owner_user_id TEXT NOT NULL REFERENCES auth_users(user_id) ON DELETE CASCADE,
                draft_id TEXT NOT NULL REFERENCES content_drafts(draft_id) ON DELETE CASCADE,
                platform TEXT NOT NULL CHECK (platform IN ('instagram', 'telegram', 'generic')),
                scheduled_at TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'scheduled' CHECK (
                    status IN ('scheduled', 'publishing', 'published', 'cancelled', 'failed', 'unknown_outcome')
                ),
                draft_version INTEGER NOT NULL CHECK (draft_version > 0),
                content_hash TEXT NOT NULL CHECK (length(content_hash) = 64),
                idempotency_key TEXT NOT NULL UNIQUE,
                attempt_count INTEGER NOT NULL DEFAULT 0 CHECK (attempt_count >= 0),
                last_error_code TEXT,
                provider_post_id TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                published_at TEXT
            )""",
            "CREATE INDEX IF NOT EXISTS idx_content_publish_schedules_due ON content_publish_schedules(status, scheduled_at)",
            "CREATE INDEX IF NOT EXISTS idx_content_publish_schedules_owner ON content_publish_schedules(owner_user_id, scheduled_at)",
            "CREATE UNIQUE INDEX IF NOT EXISTS uq_content_publish_schedules_active_draft ON content_publish_schedules(owner_user_id, draft_id) WHERE status IN ('scheduled', 'publishing', 'unknown_outcome')",
        ),
    ),
    Migration.build(
        15,
        "content_schedule_retry_timing",
        (
            "ALTER TABLE content_publish_schedules ADD COLUMN next_attempt_at TEXT",
            "CREATE INDEX IF NOT EXISTS idx_content_publish_schedules_retry_due ON content_publish_schedules(status, next_attempt_at, scheduled_at)",
        ),
    ),
    Migration.build(
        16,
        "durable_worker_emergency_stop",
        (
            """CREATE TABLE IF NOT EXISTS worker_control (
                control_id INTEGER PRIMARY KEY CHECK (control_id = 1),
                stopped INTEGER NOT NULL CHECK (stopped IN (0, 1)),
                reason TEXT,
                changed_by TEXT,
                changed_at TEXT NOT NULL
            )""",
            "INSERT OR IGNORE INTO worker_control (control_id, stopped, reason, changed_by, changed_at) VALUES (1, 0, NULL, NULL, CURRENT_TIMESTAMP)",
        ),
    ),
    Migration.build(
        17,
        "knowledge_source_freshness_metadata",
        (
            """ALTER TABLE knowledge_sources ADD COLUMN freshness_status TEXT NOT NULL
                DEFAULT 'unknown' CHECK (
                    freshness_status IN ('unknown', 'owner_reviewed_current', 'stale')
                )""",
            "ALTER TABLE knowledge_sources ADD COLUMN freshness_checked_at TEXT",
            "ALTER TABLE knowledge_sources ADD COLUMN freshness_checked_by TEXT REFERENCES auth_users(user_id) ON DELETE SET NULL",
            "CREATE INDEX IF NOT EXISTS idx_knowledge_sources_freshness ON knowledge_sources(owner_user_id, freshness_status, updated_at)",
        ),
    ),
    Migration.build(
        18,
        "content_draft_media_asset_binding",
        (
            "ALTER TABLE content_drafts ADD COLUMN media_asset_id TEXT REFERENCES content_assets(asset_id) ON DELETE RESTRICT",
            "ALTER TABLE content_draft_versions ADD COLUMN media_asset_id TEXT REFERENCES content_assets(asset_id) ON DELETE RESTRICT",
        ),
    ),
    Migration.build(
        19,
        "durable_media_file_cleanup_queue",
        (
            """CREATE TABLE IF NOT EXISTS media_file_cleanup (
                cleanup_id TEXT PRIMARY KEY,
                owner_user_id TEXT NOT NULL,
                storage_key TEXT NOT NULL UNIQUE CHECK (length(storage_key) BETWEEN 1 AND 80),
                attempt_count INTEGER NOT NULL DEFAULT 0 CHECK (attempt_count >= 0),
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )""",
            "CREATE INDEX IF NOT EXISTS idx_media_file_cleanup_owner_retry ON media_file_cleanup(owner_user_id, attempt_count, updated_at, created_at)",
        ),
    ),
    Migration.build(
        20,
        "owner_scoped_video_brand_profiles",
        (
            """CREATE TABLE IF NOT EXISTS video_brand_profiles (
                profile_id TEXT PRIMARY KEY,
                owner_user_id TEXT NOT NULL REFERENCES auth_users(user_id) ON DELETE CASCADE,
                brand_name TEXT NOT NULL CHECK (length(brand_name) BETWEEN 1 AND 80),
                handle TEXT CHECK (handle IS NULL OR length(handle) <= 80),
                logo_asset_id TEXT REFERENCES content_assets(asset_id) ON DELETE SET NULL,
                colors_json TEXT NOT NULL,
                font_preferences_json TEXT NOT NULL,
                tone TEXT CHECK (tone IS NULL OR length(tone) <= 240),
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                UNIQUE(owner_user_id, brand_name)
            )""",
            "CREATE INDEX IF NOT EXISTS idx_video_brand_profiles_owner_updated ON video_brand_profiles(owner_user_id, updated_at)",
        ),
    ),
    Migration.build(
        21,
        "durable_owner_scoped_video_analysis_jobs",
        (
            """CREATE TABLE IF NOT EXISTS video_analysis_runs (
                analysis_id TEXT PRIMARY KEY,
                task_id TEXT NOT NULL UNIQUE REFERENCES tasks(task_id) ON DELETE CASCADE,
                owner_user_id TEXT NOT NULL REFERENCES auth_users(user_id) ON DELETE CASCADE,
                mode TEXT NOT NULL CHECK (mode IN ('faithful_style_reconstruction', 'creative_style_fusion')),
                status TEXT NOT NULL CHECK (status IN ('accepted', 'running', 'completed', 'failed', 'cancelled')),
                result_json TEXT,
                error_code TEXT CHECK (error_code IS NULL OR length(error_code) <= 80),
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )""",
            "CREATE INDEX IF NOT EXISTS idx_video_analysis_owner_created ON video_analysis_runs(owner_user_id, created_at)",
            """CREATE TABLE IF NOT EXISTS video_analysis_payloads (
                analysis_id TEXT PRIMARY KEY REFERENCES video_analysis_runs(analysis_id) ON DELETE CASCADE,
                task_id TEXT NOT NULL UNIQUE REFERENCES tasks(task_id) ON DELETE CASCADE,
                owner_user_id TEXT NOT NULL REFERENCES auth_users(user_id) ON DELETE CASCADE,
                envelope_version INTEGER NOT NULL CHECK (envelope_version > 0),
                nonce_b64 TEXT NOT NULL,
                ciphertext_b64 TEXT NOT NULL,
                created_at TEXT NOT NULL
            )""",
            "CREATE INDEX IF NOT EXISTS idx_video_analysis_payloads_task ON video_analysis_payloads(task_id)",
        ),
    ),
    Migration.build(
        22,
        "durable_owner_scoped_video_generation_jobs",
        (
            """CREATE TABLE IF NOT EXISTS video_generation_jobs (
                generation_id TEXT PRIMARY KEY,
                owner_user_id TEXT NOT NULL REFERENCES auth_users(user_id) ON DELETE CASCADE,
                source_analysis_id TEXT NOT NULL REFERENCES video_analysis_runs(analysis_id) ON DELETE RESTRICT,
                provider TEXT NOT NULL CHECK (length(provider) BETWEEN 1 AND 80),
                model TEXT NOT NULL CHECK (length(model) BETWEEN 1 AND 120),
                status TEXT NOT NULL CHECK (status IN (
                    'prepared', 'queued', 'submitting', 'running', 'succeeded',
                    'failed', 'cancelled', 'unknown_outcome'
                )),
                provider_job_id TEXT CHECK (provider_job_id IS NULL OR length(provider_job_id) <= 255),
                progress_percent INTEGER CHECK (
                    progress_percent IS NULL OR progress_percent BETWEEN 0 AND 100
                ),
                output_asset_id TEXT REFERENCES content_assets(asset_id) ON DELETE SET NULL,
                output_bytes INTEGER CHECK (output_bytes IS NULL OR output_bytes BETWEEN 1 AND 100000000),
                output_duration_seconds REAL CHECK (
                    output_duration_seconds IS NULL OR output_duration_seconds BETWEEN 0 AND 60
                ),
                output_width INTEGER CHECK (output_width IS NULL OR output_width BETWEEN 1 AND 3840),
                output_height INTEGER CHECK (output_height IS NULL OR output_height BETWEEN 1 AND 3840),
                error_code TEXT CHECK (error_code IS NULL OR length(error_code) <= 80),
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                UNIQUE(generation_id, owner_user_id)
            )""",
            """CREATE TABLE IF NOT EXISTS video_generation_payloads (
                generation_id TEXT PRIMARY KEY REFERENCES video_generation_jobs(generation_id) ON DELETE CASCADE,
                owner_user_id TEXT NOT NULL REFERENCES auth_users(user_id) ON DELETE CASCADE,
                envelope_version INTEGER NOT NULL CHECK (envelope_version > 0),
                nonce_b64 TEXT NOT NULL,
                ciphertext_b64 TEXT NOT NULL,
                created_at TEXT NOT NULL
            )""",
            """CREATE TABLE IF NOT EXISTS video_generation_idempotency (
                owner_user_id TEXT NOT NULL REFERENCES auth_users(user_id) ON DELETE CASCADE,
                idempotency_key TEXT NOT NULL CHECK (length(idempotency_key) BETWEEN 1 AND 255),
                request_digest TEXT NOT NULL CHECK (length(request_digest) = 64),
                generation_id TEXT NOT NULL REFERENCES video_generation_jobs(generation_id) ON DELETE CASCADE,
                created_at TEXT NOT NULL,
                PRIMARY KEY(owner_user_id, idempotency_key)
            )""",
            "CREATE INDEX IF NOT EXISTS idx_video_generation_owner_created ON video_generation_jobs(owner_user_id, created_at)",
            "CREATE INDEX IF NOT EXISTS idx_video_generation_status_updated ON video_generation_jobs(status, updated_at)",
            "CREATE UNIQUE INDEX IF NOT EXISTS uq_video_generation_provider_job ON video_generation_jobs(provider, model, provider_job_id) WHERE provider_job_id IS NOT NULL",
        ),
    ),
    Migration.build(
        23,
        "fenced_media_asset_analysis_use_leases",
        (
            """CREATE TABLE IF NOT EXISTS media_asset_analysis_leases (
                lease_id TEXT PRIMARY KEY,
                asset_id TEXT NOT NULL REFERENCES content_assets(asset_id) ON DELETE RESTRICT,
                owner_user_id TEXT NOT NULL REFERENCES auth_users(user_id) ON DELETE RESTRICT,
                task_id TEXT NOT NULL REFERENCES tasks(task_id) ON DELETE RESTRICT,
                lease_owner TEXT NOT NULL,
                execution_token INTEGER NOT NULL CHECK (execution_token > 0),
                created_at TEXT NOT NULL,
                UNIQUE(asset_id, task_id, execution_token)
            )""",
            "CREATE INDEX IF NOT EXISTS idx_media_asset_analysis_leases_asset ON media_asset_analysis_leases(asset_id, owner_user_id)",
            "CREATE UNIQUE INDEX IF NOT EXISTS uq_media_asset_analysis_lease_asset ON media_asset_analysis_leases(asset_id)",
            "CREATE INDEX IF NOT EXISTS idx_media_asset_analysis_leases_task ON media_asset_analysis_leases(task_id, execution_token)",
        ),
    ),
    Migration.build(
        24,
        "global_media_file_cleanup_retry_index",
        (
            (
                "CREATE INDEX IF NOT EXISTS idx_media_file_cleanup_global_retry "
                "ON media_file_cleanup(attempt_count, updated_at, created_at, cleanup_id)"
            ),
        ),
    ),
    Migration.build(
        25,
        "owner_scoped_editable_video_timeline_drafts",
        (
            """CREATE TABLE IF NOT EXISTS video_timeline_drafts (
                draft_id TEXT PRIMARY KEY,
                owner_user_id TEXT NOT NULL REFERENCES auth_users(user_id) ON DELETE CASCADE,
                analysis_id TEXT NOT NULL REFERENCES video_analysis_runs(analysis_id) ON DELETE CASCADE,
                asset_id TEXT NOT NULL,
                duration_seconds INTEGER NOT NULL CHECK (duration_seconds BETWEEN 3 AND 60),
                aspect_ratio TEXT NOT NULL CHECK (aspect_ratio IN ('9:16', '16:9', '1:1', '4:5')),
                timeline_json TEXT NOT NULL CHECK (length(timeline_json) <= 60000),
                version INTEGER NOT NULL DEFAULT 1 CHECK (version > 0),
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                UNIQUE(owner_user_id, analysis_id, asset_id)
            )""",
            "CREATE INDEX IF NOT EXISTS idx_video_timeline_drafts_owner_updated ON video_timeline_drafts(owner_user_id, updated_at)",
            "CREATE INDEX IF NOT EXISTS idx_video_timeline_drafts_analysis ON video_timeline_drafts(analysis_id, asset_id)",
        ),
    ),
    Migration.build(
        26,
        "durable_video_generation_task_handoff",
        (
            """CREATE TABLE IF NOT EXISTS video_generation_task_links (
                generation_id TEXT PRIMARY KEY REFERENCES video_generation_jobs(generation_id) ON DELETE CASCADE,
                owner_user_id TEXT NOT NULL REFERENCES auth_users(user_id) ON DELETE CASCADE,
                task_id TEXT NOT NULL UNIQUE REFERENCES tasks(task_id) ON DELETE CASCADE,
                created_at TEXT NOT NULL,
                UNIQUE(generation_id, owner_user_id)
            )""",
            "CREATE INDEX IF NOT EXISTS idx_video_generation_task_links_task ON video_generation_task_links(task_id, owner_user_id)",
        ),
    ),
    Migration.build(
        27,
        "durable_owner_scoped_video_render_jobs",
        (
            """CREATE TABLE IF NOT EXISTS video_render_runs (
                render_id TEXT PRIMARY KEY,
                task_id TEXT NOT NULL UNIQUE REFERENCES tasks(task_id) ON DELETE CASCADE,
                owner_user_id TEXT NOT NULL REFERENCES auth_users(user_id) ON DELETE CASCADE,
                analysis_id TEXT NOT NULL REFERENCES video_analysis_runs(analysis_id) ON DELETE RESTRICT,
                status TEXT NOT NULL CHECK (status IN ('accepted', 'running', 'completed', 'failed', 'cancelled')),
                output_asset_id TEXT REFERENCES content_assets(asset_id) ON DELETE SET NULL,
                output_storage_key TEXT NOT NULL UNIQUE CHECK (length(output_storage_key) = 40),
                error_code TEXT CHECK (error_code IS NULL OR length(error_code) <= 80),
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )""",
            "CREATE INDEX IF NOT EXISTS idx_video_render_owner_created ON video_render_runs(owner_user_id, created_at)",
            "CREATE INDEX IF NOT EXISTS idx_video_render_analysis ON video_render_runs(analysis_id, owner_user_id)",
        ),
    ),
    Migration.build(
        28,
        "immutable_owner_scoped_video_render_timeline_snapshots",
        (
            "ALTER TABLE video_timeline_drafts ADD COLUMN renderer_timeline_json TEXT CHECK (renderer_timeline_json IS NULL OR length(renderer_timeline_json) <= 100000)",
            "ALTER TABLE video_timeline_drafts ADD COLUMN renderer_timeline_sha256 TEXT CHECK (renderer_timeline_sha256 IS NULL OR (length(renderer_timeline_sha256) = 64 AND renderer_timeline_sha256 NOT GLOB '*[^a-f0-9]*'))",
            """CREATE TRIGGER IF NOT EXISTS trg_video_timeline_draft_renderer_pair
               BEFORE UPDATE OF renderer_timeline_json, renderer_timeline_sha256
               ON video_timeline_drafts
               WHEN (NEW.renderer_timeline_json IS NULL) != (NEW.renderer_timeline_sha256 IS NULL)
               BEGIN
                   SELECT RAISE(ABORT, 'renderer timeline and hash must be stored together');
               END""",
             """CREATE TRIGGER IF NOT EXISTS trg_video_timeline_draft_renderer_pair_insert
                BEFORE INSERT ON video_timeline_drafts
                WHEN (NEW.renderer_timeline_json IS NULL) != (NEW.renderer_timeline_sha256 IS NULL)
                BEGIN
                    SELECT RAISE(ABORT, 'renderer timeline and hash must be stored together');
                END""",
             """CREATE TABLE IF NOT EXISTS video_render_timeline_snapshots (
                snapshot_id TEXT PRIMARY KEY,
                owner_user_id TEXT NOT NULL REFERENCES auth_users(user_id) ON DELETE CASCADE,
                analysis_id TEXT NOT NULL REFERENCES video_analysis_runs(analysis_id) ON DELETE RESTRICT,
                draft_id TEXT NOT NULL REFERENCES video_timeline_drafts(draft_id) ON DELETE RESTRICT,
                draft_version INTEGER NOT NULL CHECK (draft_version > 0),
                snapshot_version TEXT NOT NULL CHECK (snapshot_version = '1'),
                timeline_json TEXT NOT NULL CHECK (length(timeline_json) <= 100000),
                timeline_sha256 TEXT NOT NULL CHECK (
                    length(timeline_sha256) = 64
                    AND timeline_sha256 NOT GLOB '*[^a-f0-9]*'
                ),
                created_at TEXT NOT NULL,
                UNIQUE(draft_id, draft_version)
            )""",
            "CREATE INDEX IF NOT EXISTS idx_video_render_snapshots_owner_analysis ON video_render_timeline_snapshots(owner_user_id, analysis_id, created_at)",
            """CREATE TRIGGER IF NOT EXISTS trg_video_render_snapshots_immutable
               BEFORE UPDATE ON video_render_timeline_snapshots
               BEGIN
                   SELECT RAISE(ABORT, 'video render timeline snapshots are immutable');
               END""",
        ),
    ),
    Migration.build(
        29,
        "bind_video_render_jobs_to_immutable_timeline_snapshots",
        (
            "ALTER TABLE video_render_runs ADD COLUMN snapshot_id TEXT REFERENCES video_render_timeline_snapshots(snapshot_id) ON DELETE RESTRICT",
            "CREATE INDEX IF NOT EXISTS idx_video_render_runs_snapshot ON video_render_runs(snapshot_id, owner_user_id)",
        ),
    ),
    Migration.build(
        30,
        "durable_video_generation_reconciliation_cooldowns",
        (
            """CREATE TABLE IF NOT EXISTS video_generation_reconciliation_limits (
                generation_id TEXT NOT NULL,
                owner_user_id TEXT NOT NULL,
                attempt_count INTEGER NOT NULL DEFAULT 0 CHECK (attempt_count BETWEEN 0 AND 1000000),
                last_attempt_at TEXT,
                next_allowed_at TEXT,
                PRIMARY KEY(generation_id, owner_user_id),
                FOREIGN KEY(generation_id, owner_user_id)
                    REFERENCES video_generation_jobs(generation_id, owner_user_id)
                    ON DELETE CASCADE
            )""",
            "CREATE INDEX IF NOT EXISTS idx_video_generation_reconciliation_next_allowed ON video_generation_reconciliation_limits(next_allowed_at)",
        ),
    ),

    Migration.build(
        31,
        "owner_scoped_expiring_tool_permission_grants",
        (
            """CREATE TABLE IF NOT EXISTS tool_permission_grants (
                grant_id TEXT PRIMARY KEY CHECK (length(grant_id) = 36),
                owner_user_id TEXT NOT NULL REFERENCES auth_users(user_id) ON DELETE CASCADE,
                permission TEXT NOT NULL CHECK (permission = 'cloudflare.read'),
                granted_at TEXT NOT NULL,
                expires_at TEXT NOT NULL,
                CHECK (expires_at > granted_at),
                UNIQUE(owner_user_id, permission)
            )""",
            "CREATE INDEX IF NOT EXISTS idx_tool_permission_grants_owner_expiry ON tool_permission_grants(owner_user_id, expires_at)",
        ),
    ),
    Migration.build(
        32,
        "durable_kimi_owner_request_rate_limits",
        (
            """CREATE TABLE IF NOT EXISTS kimi_request_events (
                event_id INTEGER PRIMARY KEY AUTOINCREMENT,
                owner_user_id TEXT NOT NULL CHECK (length(owner_user_id) BETWEEN 1 AND 200),
                requested_at TEXT NOT NULL
            )""",
            "CREATE INDEX IF NOT EXISTS idx_kimi_request_events_owner_time ON kimi_request_events(owner_user_id, requested_at)",
            "CREATE INDEX IF NOT EXISTS idx_kimi_request_events_time ON kimi_request_events(requested_at)",
        ),
    ),
    Migration.build(
        33,
        "telegram_scoped_client_pairing",
        (
            """CREATE TABLE IF NOT EXISTS telegram_pairing_challenges (
                challenge_hash TEXT PRIMARY KEY CHECK (length(challenge_hash) = 64),
                owner_user_id TEXT NOT NULL REFERENCES auth_users(user_id) ON DELETE CASCADE,
                telegram_user_id INTEGER NOT NULL CHECK (telegram_user_id > 0),
                client_id TEXT NOT NULL CHECK (length(client_id) = 36),
                label TEXT NOT NULL CHECK (length(label) BETWEEN 1 AND 64),
                scopes_json TEXT NOT NULL,
                expires_at TEXT NOT NULL,
                created_at TEXT NOT NULL,
                consumed_at TEXT
            )""",
            "CREATE INDEX IF NOT EXISTS idx_telegram_pairing_challenges_expiry ON telegram_pairing_challenges(expires_at)",
            """CREATE TABLE IF NOT EXISTS telegram_clients (
                client_id TEXT PRIMARY KEY CHECK (length(client_id) = 36),
                owner_user_id TEXT NOT NULL REFERENCES auth_users(user_id) ON DELETE CASCADE,
                telegram_user_id INTEGER NOT NULL CHECK (telegram_user_id > 0),
                label TEXT NOT NULL CHECK (length(label) BETWEEN 1 AND 64),
                scopes_json TEXT NOT NULL,
                status TEXT NOT NULL CHECK (status IN ('active', 'revoked')),
                created_at TEXT NOT NULL,
                last_seen_at TEXT,
                revoked_at TEXT
            )""",
            "CREATE INDEX IF NOT EXISTS idx_telegram_clients_owner_status ON telegram_clients(owner_user_id, status, created_at)",
            """CREATE TABLE IF NOT EXISTS telegram_access_tokens (
                token_hash TEXT PRIMARY KEY CHECK (length(token_hash) = 64),
                client_id TEXT NOT NULL REFERENCES telegram_clients(client_id) ON DELETE CASCADE,
                token_type TEXT NOT NULL CHECK (token_type IN ('access', 'refresh')),
                expires_at TEXT NOT NULL,
                created_at TEXT NOT NULL,
                revoked_at TEXT
            )""",
            "CREATE INDEX IF NOT EXISTS idx_telegram_access_tokens_client_expiry ON telegram_access_tokens(client_id, expires_at)",
        ),
    ),
    Migration.build(
        34,
        "owner_scoped_reviewable_agent_proposals",
        (
            """CREATE TABLE IF NOT EXISTS agent_proposals (
                proposal_id TEXT PRIMARY KEY CHECK (length(proposal_id) = 36),
                owner_user_id TEXT NOT NULL REFERENCES auth_users(user_id) ON DELETE CASCADE,
                name TEXT NOT NULL CHECK (length(name) BETWEEN 1 AND 64),
                description TEXT NOT NULL CHECK (length(description) BETWEEN 1 AND 200),
                instructions TEXT NOT NULL CHECK (length(instructions) BETWEEN 1 AND 1200),
                allowed_tools_json TEXT NOT NULL,
                max_turns INTEGER NOT NULL CHECK (max_turns BETWEEN 1 AND 3),
                rationale TEXT NOT NULL CHECK (length(rationale) BETWEEN 1 AND 1000),
                fingerprint TEXT NOT NULL CHECK (
                    length(fingerprint) = 64 AND fingerprint NOT GLOB '*[^a-f0-9]*'
                ),
                status TEXT NOT NULL CHECK (status IN ('pending', 'approved', 'rejected')),
                created_at TEXT NOT NULL,
                reviewed_at TEXT,
                reviewed_by TEXT REFERENCES auth_users(user_id) ON DELETE SET NULL
            )""",
            "CREATE INDEX IF NOT EXISTS idx_agent_proposals_owner_created ON agent_proposals(owner_user_id, created_at DESC)",
            "CREATE UNIQUE INDEX IF NOT EXISTS idx_agent_proposals_owner_name_active ON agent_proposals(owner_user_id, name) WHERE status IN ('pending', 'approved')",
        ),
    ),
    Migration.build(
        35,
        "telegram_client_task_audit_lookup_index",
        (
            "CREATE INDEX IF NOT EXISTS idx_audit_telegram_task_owner ON audit_events(actor_type, actor_id, event_type, subject_type, subject_id)",
        ),
    ),
    Migration.build(
        36,
        "owner_scoped_people_needs_research",
        (
            """CREATE TABLE IF NOT EXISTS research_opportunities (
                opportunity_id TEXT PRIMARY KEY CHECK (length(opportunity_id) = 36),
                owner_user_id TEXT NOT NULL REFERENCES auth_users(user_id) ON DELETE CASCADE,
                domain_id TEXT NOT NULL CHECK (domain_id IN (
                    'content', 'web', 'automation', 'customer_support', 'business_ops',
                    'security', 'learning', 'documents', 'productivity', 'multilingual'
                )),
                title TEXT NOT NULL CHECK (length(title) BETWEEN 1 AND 160),
                problem_statement TEXT NOT NULL CHECK (length(problem_statement) BETWEEN 1 AND 4000),
                audience TEXT NOT NULL CHECK (length(audience) BETWEEN 1 AND 240),
                solution_hypothesis TEXT NOT NULL DEFAULT '' CHECK (length(solution_hypothesis) <= 2000),
                status TEXT NOT NULL CHECK (status IN (
                    'new', 'validating', 'validated', 'prioritized', 'in_progress', 'deferred', 'rejected'
                )),
                impact_score INTEGER CHECK (impact_score IS NULL OR impact_score BETWEEN 1 AND 5),
                frequency_score INTEGER CHECK (frequency_score IS NULL OR frequency_score BETWEEN 1 AND 5),
                feasibility_score INTEGER CHECK (feasibility_score IS NULL OR feasibility_score BETWEEN 1 AND 5),
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                UNIQUE(opportunity_id, owner_user_id)
            )""",
            "CREATE INDEX IF NOT EXISTS idx_research_opportunities_owner_updated ON research_opportunities(owner_user_id, updated_at DESC)",
            "CREATE INDEX IF NOT EXISTS idx_research_opportunities_owner_domain_status ON research_opportunities(owner_user_id, domain_id, status)",
            """CREATE TABLE IF NOT EXISTS research_evidence (
                evidence_id TEXT PRIMARY KEY CHECK (length(evidence_id) = 36),
                opportunity_id TEXT NOT NULL,
                owner_user_id TEXT NOT NULL,
                source_type TEXT NOT NULL CHECK (source_type IN (
                    'public_discussion', 'community_forum', 'app_review',
                    'research_report', 'support_request', 'other'
                )),
                canonical_url TEXT NOT NULL CHECK (length(canonical_url) BETWEEN 1 AND 2048),
                source_label TEXT NOT NULL CHECK (length(source_label) BETWEEN 1 AND 120),
                observation_summary TEXT NOT NULL CHECK (length(observation_summary) BETWEEN 1 AND 2000),
                signal_strength TEXT NOT NULL CHECK (signal_strength IN ('low', 'medium', 'high')),
                captured_at TEXT NOT NULL,
                published_at TEXT,
                UNIQUE(opportunity_id, canonical_url),
                FOREIGN KEY(opportunity_id, owner_user_id)
                    REFERENCES research_opportunities(opportunity_id, owner_user_id)
                    ON DELETE CASCADE
            )""",
            "CREATE INDEX IF NOT EXISTS idx_research_evidence_owner_opportunity_captured ON research_evidence(owner_user_id, opportunity_id, captured_at DESC)",
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
