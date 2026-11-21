from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from mrhub.api.routes import health


class _Result:
    def __init__(self, row):
        self._row = row

    def fetchone(self):
        return self._row


class _Connection:
    def __init__(self, schema_version, heartbeat):
        self.schema_version = schema_version
        self.heartbeat = heartbeat

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return None

    def execute(self, query):
        if "MAX(version)" in query:
            return _Result((self.schema_version,))
        if "heartbeat_at" in query:
            return _Result(self.heartbeat)
        if "FROM tasks" in query:
            return _Result(None)
        raise AssertionError(f"Unexpected readiness query: {query}")


def _configure_readiness(monkeypatch, tmp_path, heartbeat, *, require_worker=False):
    expected_version = max(migration.version for migration in health.MIGRATIONS)
    settings = SimpleNamespace(
        database_path=tmp_path / "hub.sqlite3",
        worker_heartbeat_timeout_seconds=30,
        require_worker_for_readiness=require_worker,
    )
    monkeypatch.setattr(health, "get_settings", lambda: settings)
    monkeypatch.setattr(
        health.sqlite3,
        "connect",
        lambda *_args, **_kwargs: _Connection(expected_version, heartbeat),
    )


def test_readiness_distinguishes_stale_worker_from_missing_worker(monkeypatch, tmp_path):
    heartbeat = (datetime.now(UTC) - timedelta(minutes=2)).isoformat()
    _configure_readiness(monkeypatch, tmp_path, (heartbeat,))

    result = health.readiness()

    assert result["status"] == "ready"
    assert result["database"] == "ready"
    assert result["worker"] == "stale"
    assert result["worker_heartbeat_age_seconds"] >= 120


def test_required_worker_rejects_stale_heartbeat(monkeypatch, tmp_path):
    heartbeat = (datetime.now(UTC) - timedelta(minutes=2)).isoformat()
    _configure_readiness(monkeypatch, tmp_path, (heartbeat,), require_worker=True)

    with pytest.raises(HTTPException) as exc_info:
        health.readiness()

    assert exc_info.value.status_code == 503
    assert exc_info.value.detail == "Worker process is not ready"


def test_readiness_keeps_missing_worker_distinct(monkeypatch, tmp_path):
    _configure_readiness(monkeypatch, tmp_path, None)

    result = health.readiness()

    assert result["worker"] == "not_detected"
    assert result["worker_heartbeat_age_seconds"] is None


def test_future_worker_heartbeat_is_not_accepted_as_live(monkeypatch, tmp_path):
    heartbeat = (datetime.now(UTC) + timedelta(minutes=5)).isoformat()
    _configure_readiness(monkeypatch, tmp_path, (heartbeat,))

    result = health.readiness()

    assert result["worker"] == "not_detected"
    assert result["worker_heartbeat_age_seconds"] is None


def test_required_worker_rejects_future_heartbeat(monkeypatch, tmp_path):
    heartbeat = (datetime.now(UTC) + timedelta(minutes=5)).isoformat()
    _configure_readiness(
        monkeypatch, tmp_path, (heartbeat,), require_worker=True
    )

    with pytest.raises(HTTPException) as exc_info:
        health.readiness()

    assert exc_info.value.status_code == 503
    assert exc_info.value.detail == "Worker process is not ready"
