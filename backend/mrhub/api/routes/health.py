"""Health and readiness endpoints."""
from __future__ import annotations

import sqlite3

from fastapi import APIRouter, HTTPException, status

from mrhub.config import get_settings
from mrhub.infrastructure.migrations import MIGRATIONS

router = APIRouter(tags=["system"])


@router.get("/health", summary="Application liveness")
def health() -> dict[str, str]:
    """Report process liveness without claiming dependencies are ready."""
    return {"status": "ok"}


@router.get("/ready", summary="Application database readiness")
def readiness() -> dict[str, str | int]:
    """Check that the existing database is readable and at the expected schema version.

    This endpoint is read-only: it never creates a database or runs migrations.
    It intentionally does not claim that a separate pull-driven worker is alive.
    """
    database_path = get_settings().database_path
    expected_version = max(migration.version for migration in MIGRATIONS)
    try:
        database_uri = f"{database_path.resolve().as_uri()}?mode=ro"
        with sqlite3.connect(database_uri, uri=True, timeout=1.0) as connection:
            row = connection.execute(
                "SELECT MAX(version) FROM schema_migrations"
            ).fetchone()
            applied_version = row[0] if row else None
            if applied_version != expected_version:
                raise HTTPException(
                    status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                    detail="Database schema is not ready",
                )
            connection.execute("SELECT 1 FROM tasks LIMIT 1").fetchone()
    except HTTPException:
        raise
    except (OSError, sqlite3.Error, ValueError):
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Database is not ready",
        ) from None
    return {"status": "ready", "database": "ready", "schema_version": expected_version}
