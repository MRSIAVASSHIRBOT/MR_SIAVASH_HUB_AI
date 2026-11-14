import sqlite3

import pytest

from mrhub.infrastructure.migrations import MIGRATIONS, MigrationError, SchemaMigrator


def connect(path):
    connection = sqlite3.connect(path)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    return connection


def test_fresh_database_applies_all_migrations_and_is_idempotent(tmp_path):
    connection = connect(tmp_path / "fresh.sqlite3")
    migrator = SchemaMigrator(connection)

    assert migrator.migrate() == [migration.version for migration in MIGRATIONS]
    assert migrator.migrate() == []
    versions = connection.execute(
        "SELECT version FROM schema_migrations ORDER BY version"
    ).fetchall()
    assert [row["version"] for row in versions] == [migration.version for migration in MIGRATIONS]
    worker_columns = {
        row["name"] for row in connection.execute("PRAGMA table_info(worker_executions)")
    }
    assert {
        "attempt_count", "recovered_at", "next_attempt_at",
        "lease_owner", "lease_expires_at", "heartbeat_at", "execution_token",
    } <= worker_columns
    assert {
        "workflow_runs", "workflow_steps", "workflow_step_attempts",
        "workflow_checkpoints", "idempotency_records", "agent_runs", "workflow_payloads", "capability_candidates",
        "memory_entries", "knowledge_sources", "knowledge_documents", "knowledge_chunks",
        "memory_entries_fts", "knowledge_chunks_fts", "content_drafts", "content_draft_versions", "content_assets",
        "content_publish_schedules", "media_file_cleanup", "media_asset_analysis_leases",
        "video_render_runs", "video_render_timeline_snapshots", "video_generation_reconciliation_limits",
        "tool_permission_grants",
        "kimi_request_events", "telegram_pairing_challenges", "telegram_clients",
        "telegram_access_tokens",
        "resource_reply_configs",
    } <= {
        row["name"]
        for row in connection.execute(
            "SELECT name FROM sqlite_master WHERE type = 'table'"
        )
    }
    kimi_request_columns = {
        row["name"]
        for row in connection.execute("PRAGMA table_info(kimi_request_events)")
    }
    assert {"event_id", "owner_user_id", "requested_at"} <= kimi_request_columns
    assert connection.execute(
        "SELECT 1 FROM sqlite_master WHERE type = 'index' "
        "AND name = 'idx_kimi_request_events_owner_time'"
    ).fetchone() is not None
    source_columns = {
        row["name"] for row in connection.execute("PRAGMA table_info(knowledge_sources)")
    }
    assert {"freshness_status", "freshness_checked_at", "freshness_checked_by"} <= source_columns
    draft_columns = {
        row["name"] for row in connection.execute("PRAGMA table_info(content_drafts)")
    }
    version_columns = {
        row["name"] for row in connection.execute("PRAGMA table_info(content_draft_versions)")
    }
    assert "media_asset_id" in draft_columns
    assert "media_asset_id" in version_columns

    workflow_columns = {
        row["name"] for row in connection.execute("PRAGMA table_info(workflow_runs)")
    }
    assert "owner_user_id" in workflow_columns
    cleanup_columns = {
        row["name"]
        for row in connection.execute("PRAGMA table_info(media_file_cleanup)")
    }
    assert {
        "cleanup_id", "owner_user_id", "storage_key", "attempt_count",
        "created_at", "updated_at"
    } <= cleanup_columns
    # Cleanup intents must survive account deletion, so this table intentionally
    # has no cascading foreign key to auth_users.
    assert connection.execute(
        "PRAGMA foreign_key_list(media_file_cleanup)"
    ).fetchall() == []
    cleanup_index = connection.execute(
        "SELECT sql FROM sqlite_master WHERE type = 'index' "
        "AND name = 'idx_media_file_cleanup_owner_retry'"
    ).fetchone()
    assert cleanup_index is not None
    assert "owner_user_id, attempt_count, updated_at, created_at" in cleanup_index["sql"]
    connection.close()


def test_legacy_schema_is_upgraded_without_losing_rows(tmp_path):
    connection = connect(tmp_path / "legacy.sqlite3")
    connection.execute(
        """CREATE TABLE audit_events (
            event_id TEXT PRIMARY KEY,
            event_type TEXT NOT NULL,
            outcome TEXT NOT NULL,
            subject_type TEXT NOT NULL,
            subject_id TEXT,
            actor_type TEXT NOT NULL,
            created_at TEXT NOT NULL,
            metadata_json TEXT NOT NULL
        )"""
    )
    connection.execute(
        """INSERT INTO audit_events VALUES
        ('event-1', 'legacy.event', 'ok', 'task', 'task-1', 'system',
         '2026-01-01T00:00:00+00:00', '{}')"""
    )
    connection.commit()

    assert SchemaMigrator(connection).migrate() == [migration.version for migration in MIGRATIONS]
    row = connection.execute(
        "SELECT event_id, actor_id FROM audit_events WHERE event_id = 'event-1'"
    ).fetchone()
    assert row["event_id"] == "event-1"
    assert row["actor_id"] is None
    connection.close()


def test_v3_preserves_legacy_agent_workflow_rows(tmp_path):
    connection = connect(tmp_path / "legacy-workflow.sqlite3")
    connection.execute(
        """CREATE TABLE agent_workflows (
            workflow_id TEXT PRIMARY KEY,
            status TEXT NOT NULL,
            request_digest TEXT NOT NULL,
            plan_json TEXT NOT NULL,
            steps_json TEXT NOT NULL,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        )"""
    )
    connection.execute(
        """INSERT INTO agent_workflows VALUES
        ('legacy-1', 'succeeded', 'digest', '{}', '[]',
         '2026-01-01T00:00:00+00:00', '2026-01-01T00:00:00+00:00')"""
    )
    connection.commit()

    SchemaMigrator(connection).migrate()

    row = connection.execute(
        "SELECT workflow_id, status FROM agent_workflows WHERE workflow_id = 'legacy-1'"
    ).fetchone()
    assert tuple(row) == ("legacy-1", "succeeded")
    assert connection.execute(
        "SELECT 1 FROM workflow_runs WHERE workflow_id = 'legacy-1'"
    ).fetchone() is None
    # Historical rows have no trustworthy owner identity. Migration must preserve
    # them without guessing an owner or making them visible to arbitrary users.
    columns = {
        item["name"] for item in connection.execute("PRAGMA table_info(agent_workflows)")
    }
    assert "owner_user_id" in columns
    assert connection.execute(
        "SELECT owner_user_id FROM agent_workflows WHERE workflow_id = 'legacy-1'"
    ).fetchone()["owner_user_id"] is None
    connection.close()


def test_migration_checksum_drift_fails_closed(tmp_path, monkeypatch):
    from mrhub.infrastructure import migrations

    connection = connect(tmp_path / "drift.sqlite3")
    SchemaMigrator(connection).migrate()
    original = migrations.MIGRATIONS
    changed = original[0].__class__.build(
        1, "core_schema", original[0].statements + ("CREATE TABLE drift_probe (id INTEGER)",)
    )
    monkeypatch.setattr(migrations, "MIGRATIONS", (changed, *original[1:]))

    with pytest.raises(MigrationError, match="checksum"):
        SchemaMigrator(connection).migrate()
    connection.close()


def test_failed_migration_rolls_back_schema_and_version(tmp_path, monkeypatch):
    from mrhub.infrastructure import migrations

    connection = connect(tmp_path / "rollback.sqlite3")
    original = migrations.MIGRATIONS
    broken = original[0].__class__.build(
        1,
        "broken_core",
        ("CREATE TABLE rollback_probe (id INTEGER)", "INVALID SQL"),
    )
    monkeypatch.setattr(migrations, "MIGRATIONS", (broken,))

    with pytest.raises(sqlite3.OperationalError):
        SchemaMigrator(connection).migrate()

    assert connection.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='rollback_probe'"
    ).fetchone() is None
    assert connection.execute(
        "SELECT version FROM schema_migrations"
    ).fetchall() == []
    monkeypatch.setattr(migrations, "MIGRATIONS", original)
    connection.close()


def test_unknown_future_migration_version_fails_closed(tmp_path):
    connection = connect(tmp_path / "unknown-version.sqlite3")
    SchemaMigrator(connection).migrate()
    connection.execute(
        """INSERT INTO schema_migrations (version, name, checksum, applied_at)
        VALUES (99, 'future_schema', 'future-checksum', '2026-01-01T00:00:00+00:00')"""
    )
    connection.commit()

    with pytest.raises(MigrationError, match="unsupported migration versions"):
        SchemaMigrator(connection).migrate()
    connection.close()


def test_agent_repositories_delegate_schema_to_versioned_migrations(tmp_path):
    from mrhub.agents.repository import AgentRunRepository
    from mrhub.agents.workflow_repository import AgentWorkflowRepository

    database_path = tmp_path / "agent-repositories.sqlite3"
    AgentRunRepository(database_path).initialize()
    AgentWorkflowRepository(database_path).initialize()

    connection = connect(database_path)
    versions = connection.execute(
        "SELECT version FROM schema_migrations ORDER BY version"
    ).fetchall()
    assert [row["version"] for row in versions] == [migration.version for migration in MIGRATIONS]
    tables = {
        row["name"]
        for row in connection.execute(
            "SELECT name FROM sqlite_master WHERE type = 'table'"
        )
    }
    assert {"agent_runs", "agent_workflows"} <= tables
    agent_run_columns = {
        row["name"] for row in connection.execute("PRAGMA table_info(agent_runs)")
    }
    assert "owner_user_id" in agent_run_columns
    connection.close()


def test_v6_preserves_historical_agent_runs_as_unowned(tmp_path, monkeypatch):
    from mrhub.infrastructure import migrations

    connection = connect(tmp_path / "historical-agent-runs.sqlite3")
    original = migrations.MIGRATIONS
    monkeypatch.setattr(migrations, "MIGRATIONS", original[:5])
    SchemaMigrator(connection).migrate()
    connection.execute(
        """INSERT INTO agent_runs (
            run_id, request_digest, status, provider_name, model_name,
            plan_json, tool_names_json, executed_tool_count, error_code, created_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (
            "historical-run", "a" * 64, "succeeded", None, None,
            "{}", "[]", 0, None, "2026-01-01T00:00:00+00:00",
        ),
    )
    connection.commit()

    monkeypatch.setattr(migrations, "MIGRATIONS", original)
    SchemaMigrator(connection).migrate()

    row = connection.execute(
        "SELECT owner_user_id FROM agent_runs WHERE run_id = 'historical-run'"
    ).fetchone()
    assert row["owner_user_id"] is None
    connection.close()



def test_migrations_19_to_29_upgrade_an_existing_v18_database(tmp_path, monkeypatch):
    from mrhub.infrastructure import migrations

    connection = connect(tmp_path / "version-18.sqlite3")
    original = migrations.MIGRATIONS
    baseline = tuple(migration for migration in original if migration.version <= 18)
    pending = tuple(migration for migration in original if migration.version > 18)
    assert baseline and baseline[-1].version == 18
    assert pending and pending[0].version == 19

    monkeypatch.setattr(migrations, "MIGRATIONS", baseline)
    applied = SchemaMigrator(connection).migrate()

    assert applied == [migration.version for migration in baseline]
    assert connection.execute(
        "SELECT MAX(version) FROM schema_migrations"
    ).fetchone()[0] == 18
    assert connection.execute(
        "SELECT name FROM sqlite_master WHERE type = 'table' "
        "AND name = 'media_file_cleanup'"
    ).fetchone() is None
    assert connection.execute(
        "SELECT name FROM sqlite_master WHERE type = 'table' "
        "AND name = 'video_brand_profiles'"
    ).fetchone() is None

    monkeypatch.setattr(migrations, "MIGRATIONS", original)
    assert SchemaMigrator(connection).migrate() == [
        migration.version for migration in pending
    ]
    assert connection.execute(
        "SELECT MAX(version) FROM schema_migrations"
    ).fetchone()[0] == pending[-1].version
    assert connection.execute(
        "SELECT name FROM sqlite_master WHERE type = 'table' "
        "AND name = 'media_file_cleanup'"
    ).fetchone() is not None
    assert connection.execute(
        "SELECT name FROM sqlite_master WHERE type = 'index' "
        "AND name = 'idx_media_file_cleanup_owner_retry'"
    ).fetchone() is not None
    assert connection.execute(
        "SELECT name FROM sqlite_master WHERE type = 'table' "
        "AND name = 'video_brand_profiles'"
    ).fetchone() is not None
    assert connection.execute(
        "SELECT name FROM sqlite_master WHERE type = 'table' "
        "AND name = 'video_analysis_runs'"
    ).fetchone() is not None
    assert connection.execute(
        "SELECT name FROM sqlite_master WHERE type = 'table' "
        "AND name = 'video_analysis_payloads'"
    ).fetchone() is not None
    assert connection.execute(
        "SELECT name FROM sqlite_master WHERE type = 'table' "
        "AND name = 'video_generation_jobs'"
    ).fetchone() is not None
    assert connection.execute(
        "SELECT name FROM sqlite_master WHERE type = 'table' "
        "AND name = 'video_generation_payloads'"
    ).fetchone() is not None
    assert connection.execute(
        "SELECT name FROM sqlite_master WHERE type = 'table' "
        "AND name = 'video_generation_idempotency'"
    ).fetchone() is not None
    assert connection.execute(
        "SELECT name FROM sqlite_master WHERE type = 'table' "
        "AND name = 'media_asset_analysis_leases'"
    ).fetchone() is not None
    assert connection.execute(
        "SELECT name FROM sqlite_master WHERE type = 'index' "
        "AND name = 'idx_media_asset_analysis_leases_asset'"
    ).fetchone() is not None
    lease_foreign_keys = {
        row["table"]: row["on_delete"]
        for row in connection.execute(
            "PRAGMA foreign_key_list(media_asset_analysis_leases)"
        )
    }
    assert lease_foreign_keys == {
        "content_assets": "RESTRICT",
        "auth_users": "RESTRICT",
        "tasks": "RESTRICT",
    }
    assert connection.execute(
        "SELECT name FROM sqlite_master WHERE type = 'table' "
        "AND name = 'video_timeline_drafts'"
    ).fetchone() is not None
    assert connection.execute(
        "SELECT name FROM sqlite_master WHERE type = 'index' "
        "AND name = 'idx_video_timeline_drafts_owner_updated'"
    ).fetchone() is not None
    assert connection.execute(
        "SELECT name FROM sqlite_master WHERE type = 'table' "
        "AND name = 'video_generation_task_links'"
    ).fetchone() is not None
    assert connection.execute(
        "SELECT name FROM sqlite_master WHERE type = 'index' "
        "AND name = 'idx_video_generation_task_links_task'"
    ).fetchone() is not None
    assert connection.execute(
        "SELECT name FROM sqlite_master WHERE type = 'table' "
        "AND name = 'video_render_runs'"
    ).fetchone() is not None
    render_columns = {
        row["name"] for row in connection.execute("PRAGMA table_info(video_render_runs)")
    }
    assert {
        "render_id", "task_id", "owner_user_id", "analysis_id",
        "output_asset_id", "output_storage_key", "status",
    } <= render_columns
    assert connection.execute(
        "SELECT name FROM sqlite_master WHERE type = 'index' "
        "AND name = 'idx_video_render_owner_created'"
    ).fetchone() is not None
    assert connection.execute(
        "SELECT name FROM sqlite_master WHERE type = 'index' "
        "AND name = 'idx_video_render_analysis'"
    ).fetchone() is not None
    render_snapshot_columns = {
        row["name"]
        for row in connection.execute("PRAGMA table_info(video_render_runs)")
    }
    assert "snapshot_id" in render_snapshot_columns
    assert connection.execute(
        "SELECT name FROM sqlite_master WHERE type = 'index' "
        "AND name = 'idx_video_render_runs_snapshot'"
    ).fetchone() is not None
    render_snapshot_foreign_keys = {
        row["table"]: row["on_delete"]
        for row in connection.execute("PRAGMA foreign_key_list(video_render_runs)")
    }
    assert render_snapshot_foreign_keys["video_render_timeline_snapshots"] == "RESTRICT"
    draft_renderer_columns = {
        row["name"]
        for row in connection.execute("PRAGMA table_info(video_timeline_drafts)")
    }
    assert {"renderer_timeline_json", "renderer_timeline_sha256"} <= draft_renderer_columns
    snapshot_columns = {
        row["name"]
        for row in connection.execute("PRAGMA table_info(video_render_timeline_snapshots)")
    }
    assert {
        "snapshot_id", "owner_user_id", "analysis_id", "draft_id",
        "draft_version", "snapshot_version", "timeline_json",
        "timeline_sha256", "created_at",
    } <= snapshot_columns
    assert connection.execute(
        "SELECT name FROM sqlite_master WHERE type = 'trigger' "
        "AND name = 'trg_video_render_snapshots_immutable'"
    ).fetchone() is not None
    assert SchemaMigrator(connection).migrate() == []
    connection.close()




def test_v28_renderer_snapshot_schema_enforces_pair_and_retention_policy(tmp_path):
    connection = connect(tmp_path / "renderer-snapshot-schema.sqlite3")
    try:
        SchemaMigrator(connection).migrate()

        triggers = {
            row["name"]
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type = 'trigger'"
            )
        }
        assert "trg_video_timeline_draft_renderer_pair" in triggers
        assert "trg_video_timeline_draft_renderer_pair_insert" in triggers
        assert "trg_video_render_snapshots_immutable" in triggers

        foreign_keys = {
            row["table"]: row["on_delete"]
            for row in connection.execute(
                "PRAGMA foreign_key_list(video_render_timeline_snapshots)"
            )
        }
        assert foreign_keys == {
            "video_timeline_drafts": "RESTRICT",
            "video_analysis_runs": "RESTRICT",
            "auth_users": "CASCADE",
        }
        draft_foreign_keys = {
            row["table"]: row["on_delete"]
            for row in connection.execute(
                "PRAGMA foreign_key_list(video_timeline_drafts)"
            )
        }
        assert draft_foreign_keys["video_analysis_runs"] == "CASCADE"
    finally:
        connection.close()


def test_telegram_client_task_ownership_query_uses_composite_audit_index(tmp_path):
    connection = connect(tmp_path / "telegram-audit-index.sqlite3")
    try:
        SchemaMigrator(connection).migrate()
        for index in range(1_000):
            task_id = f"task-{index}"
            actor_id = "client-target" if index == 500 else f"client-{index}"
            connection.execute(
                """INSERT INTO tasks (
                    task_id, task_type, status, risk_class, created_at, updated_at, description
                ) VALUES (?, 'test', 'queued', 'low', ?, ?, '')""",
                (task_id, "2026-11-09T00:00:00+00:00", "2026-11-09T00:00:00+00:00"),
            )
            connection.execute(
                """INSERT INTO audit_events (
                    event_id, event_type, outcome, subject_type, subject_id,
                    actor_type, actor_id, created_at, metadata_json
                ) VALUES (?, 'task.submitted', 'queued', 'task', ?, 'telegram_client', ?, ?, '{}')""",
                (f"event-{index}", task_id, actor_id, "2026-11-09T00:00:00+00:00"),
            )
        connection.execute("ANALYZE")
        plan = connection.execute(
            """EXPLAIN QUERY PLAN
               SELECT t.*
               FROM tasks AS t
               INNER JOIN audit_events AS a
                   ON a.subject_id = t.task_id
                  AND a.event_type = 'task.submitted'
                  AND a.subject_type = 'task'
                  AND a.actor_type = 'telegram_client'
                  AND a.actor_id = ?
               ORDER BY t.created_at DESC, t.task_id DESC
               LIMIT ?""",
            ("client-target", 20),
        ).fetchall()
        details = [row["detail"] for row in plan]
        assert any("idx_audit_telegram_task_owner" in detail for detail in details), details
    finally:
        connection.close()


def test_v36_rebuild_preserves_content_versions_and_schedules_and_allows_reels(tmp_path, monkeypatch):
    from mrhub.infrastructure import migrations as migrations_module

    connection = connect(tmp_path / "reel-migration.sqlite3")
    all_migrations = migrations_module.MIGRATIONS
    monkeypatch.setattr(migrations_module, "MIGRATIONS", all_migrations[:35])
    assert SchemaMigrator(connection).migrate() == [item.version for item in all_migrations[:35]]

    now = "2026-11-14T00:00:00+00:00"
    connection.execute(
        "INSERT INTO auth_users (user_id, username, salt, password_hash, created_at) "
        "VALUES ('owner-1', 'owner-1', '00', '00', ?)",
        (now,),
    )
    connection.execute(
        """INSERT INTO content_drafts (
            draft_id, owner_user_id, platform, content_type, title, body, hashtags_json,
            status, content_hash, version, approved_by, approved_at, created_at, updated_at,
            media_asset_id
        ) VALUES ('draft-1', 'owner-1', 'instagram', 'caption', 'Legacy', 'Legacy body',
                  '[]', 'draft', ?, 1, NULL, NULL, ?, ?, NULL)""",
        ("a" * 64, now, now),
    )
    connection.execute(
        """INSERT INTO content_draft_versions (
            version_id, draft_id, owner_user_id, version_number, platform, content_type,
            title, body, hashtags_json, content_hash, changed_by, created_at, media_asset_id
        ) VALUES ('version-1', 'draft-1', 'owner-1', 1, 'instagram', 'caption',
                  'Legacy', 'Legacy body', '[]', ?, 'owner-1', ?, NULL)""",
        ("a" * 64, now),
    )
    connection.execute(
        """INSERT INTO content_publish_schedules (
            schedule_id, owner_user_id, draft_id, platform, scheduled_at, status,
            draft_version, content_hash, idempotency_key, attempt_count, last_error_code,
            provider_post_id, created_at, updated_at, published_at, next_attempt_at
        ) VALUES ('schedule-1', 'owner-1', 'draft-1', 'instagram', ?, 'scheduled',
                  1, ?, 'idem-1', 0, NULL, NULL, ?, ?, NULL, NULL)""",
        (now, "a" * 64, now, now),
    )
    connection.commit()

    monkeypatch.setattr(migrations_module, "MIGRATIONS", all_migrations)
    assert SchemaMigrator(connection).migrate() == [36, 37]
    preserved_draft = connection.execute(
        "SELECT title, content_type FROM content_drafts WHERE draft_id = 'draft-1'"
    ).fetchone()
    assert (preserved_draft["title"], preserved_draft["content_type"]) == ("Legacy", "caption")
    assert connection.execute(
        "SELECT version_id FROM content_draft_versions WHERE version_id = 'version-1'"
    ).fetchone()["version_id"] == "version-1"
    assert connection.execute(
        "SELECT schedule_id FROM content_publish_schedules WHERE schedule_id = 'schedule-1'"
    ).fetchone()["schedule_id"] == "schedule-1"

    connection.execute(
        """INSERT INTO content_drafts (
            draft_id, owner_user_id, platform, content_type, title, body, hashtags_json,
            status, content_hash, version, approved_by, approved_at, created_at, updated_at,
            media_asset_id
        ) VALUES ('reel-draft', 'owner-1', 'instagram', 'reel', 'Reel', 'Reel body',
                  '[]', 'draft', ?, 1, NULL, NULL, ?, ?, NULL)""",
        ("b" * 64, now, now),
    )
    connection.execute(
        """INSERT INTO content_draft_versions (
            version_id, draft_id, owner_user_id, version_number, platform, content_type,
            title, body, hashtags_json, content_hash, changed_by, created_at, media_asset_id
        ) VALUES ('reel-version', 'reel-draft', 'owner-1', 1, 'instagram', 'reel',
                  'Reel', 'Reel body', '[]', ?, 'owner-1', ?, NULL)""",
        ("b" * 64, now),
    )
    connection.execute(
        """INSERT INTO content_drafts (
            draft_id, owner_user_id, platform, content_type, title, body, hashtags_json,
            status, content_hash, version, approved_by, approved_at, created_at, updated_at,
            media_asset_id
        ) VALUES ('telegram-draft', 'owner-1', 'telegram', 'post_text', 'Lesson',
                  'Companion lesson', '[]', 'draft', ?, 1, NULL, NULL, ?, ?, NULL)""",
        ("c" * 64, now, now),
    )
    connection.execute(
        """INSERT INTO content_campaigns (
            campaign_id, owner_user_id, title, instagram_draft_id, telegram_draft_id,
            status, created_at, updated_at
        ) VALUES ('campaign-1', 'owner-1', 'Campaign', 'reel-draft',
                  'telegram-draft', 'draft', ?, ?)""",
        (now, now),
    )
    assert connection.execute(
        "SELECT campaign_id FROM content_campaigns WHERE campaign_id = 'campaign-1'"
    ).fetchone()["campaign_id"] == "campaign-1"
    connection.commit()
    assert connection.execute("PRAGMA foreign_key_check").fetchall() == []
    connection.close()
