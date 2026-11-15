import sqlite3

from mrhub.infrastructure.migrations import SchemaMigrator


def _connect(path, *, timeout=0.05):
    connection = sqlite3.connect(path, timeout=timeout)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    return connection


def test_current_schema_fast_path_does_not_wait_for_reserved_write_lock(tmp_path):
    database_path = tmp_path / "current-schema-lock.sqlite3"
    initializer = _connect(database_path)
    try:
        SchemaMigrator(initializer).migrate()
    finally:
        initializer.close()

    blocker = _connect(database_path)
    reader = _connect(database_path)
    try:
        blocker.execute("BEGIN IMMEDIATE")
        blocker.execute(
            """INSERT INTO tasks (
                task_id, task_type, status, risk_class, created_at, updated_at, description
            ) VALUES ('lock-holder', 'test', 'queued', 'low', 'now', 'now', '')"""
        )

        # A current database must validate its migration history without trying
        # to acquire a reserved write lock held by another process.
        assert SchemaMigrator(reader).migrate() == []
        assert reader.in_transaction is False
    finally:
        reader.close()
        blocker.rollback()
        blocker.close()
