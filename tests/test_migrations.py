import sqlite3

import pytest

from mrhub.infrastructure.migrations import MigrationError, SchemaMigrator


def connect(path):
    connection = sqlite3.connect(path)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    return connection


def test_fresh_database_applies_all_migrations_and_is_idempotent(tmp_path):
    connection = connect(tmp_path / "fresh.sqlite3")
    migrator = SchemaMigrator(connection)

    assert migrator.migrate() == [1, 2, 3]
    assert migrator.migrate() == []
    versions = connection.execute(
        "SELECT version FROM schema_migrations ORDER BY version"
    ).fetchall()
    assert [row["version"] for row in versions] == [1, 2, 3]
    assert {
        row["name"] for row in connection.execute("PRAGMA table_info(worker_executions)")
    } >= {"attempt_count", "recovered_at", "next_attempt_at"}
    assert connection.execute(
        "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = 'capability_candidates'"
    ).fetchone() is not None
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

    assert SchemaMigrator(connection).migrate() == [1, 2, 3]
    row = connection.execute(
        "SELECT event_id, actor_id FROM audit_events WHERE event_id = 'event-1'"
    ).fetchone()
    assert row["event_id"] == "event-1"
    assert row["actor_id"] is None
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
