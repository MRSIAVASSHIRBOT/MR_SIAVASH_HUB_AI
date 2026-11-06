import sqlite3
from datetime import UTC, datetime

import pytest

from mrhub.infrastructure.database import TaskRepository
from mrhub.security.audit import AuditLogger
from mrhub.security.tool_permissions import ToolPermissionService


def _repository(tmp_path):
    repository = TaskRepository(tmp_path / "tool-permissions.sqlite3")
    repository.initialize()
    repository.create_auth_user("owner-a", "owner-a", "00" * 16, "00" * 32)
    repository.create_auth_user("owner-b", "owner-b", "11" * 16, "11" * 32)
    return repository


def test_grants_are_owner_scoped_expiring_and_audited(tmp_path):
    repository = _repository(tmp_path)
    service = ToolPermissionService(repository, AuditLogger(repository))

    grant_a = service.grant("owner-a", "cloudflare.read", 3600)
    service.grant("owner-b", "cloudflare.read", 7200)

    assert service.active_permissions("owner-a") == frozenset({"cloudflare.read"})
    assert service.active_permissions("owner-b") == frozenset({"cloudflare.read"})
    assert repository.get_active_tool_permissions("owner-a", grant_a["expires_at"]) == frozenset()

    assert service.revoke("owner-a", "cloudflare.read") is True
    assert service.revoke("owner-a", "cloudflare.read") is False
    assert service.active_permissions("owner-a") == frozenset()
    assert service.active_permissions("owner-b") == frozenset({"cloudflare.read"})

    events = repository.list_audit()
    assert [event["event_type"] for event in events].count("tool.permission_granted") == 2
    assert [event["event_type"] for event in events].count("tool.permission_revoked") == 1
    assert all("permission" in event["metadata"] for event in events)


def test_grant_renewal_replaces_expiry_without_duplicate_rows(tmp_path):
    repository = _repository(tmp_path)
    service = ToolPermissionService(repository, AuditLogger(repository))

    first = service.grant("owner-a", "cloudflare.read", 3600)
    second = service.grant("owner-a", "cloudflare.read", 7200)

    active = service.list_active("owner-a")
    assert len(active) == 1
    assert active[0]["grant_id"] == second["grant_id"]
    assert active[0]["grant_id"] != first["grant_id"]
    assert active[0]["expires_at"] == second["expires_at"]


@pytest.mark.parametrize(
    ("permission", "expiry"),
    [
        ("cloudflare.write", 3600),
        ("cloudflare.read", 59),
        ("cloudflare.read", 86_401),
        ("cloudflare.read", True),
    ],
)
def test_invalid_permission_and_expiry_are_rejected(tmp_path, permission, expiry):
    repository = _repository(tmp_path)
    service = ToolPermissionService(repository, AuditLogger(repository))
    with pytest.raises(ValueError):
        service.grant("owner-a", permission, expiry)


def test_permission_change_and_audit_event_roll_back_together(tmp_path):
    repository = _repository(tmp_path)
    now = datetime.now(UTC).isoformat()
    grant = {
        "grant_id": "12345678-1234-5678-1234-567812345678",
        "owner_user_id": "owner-a",
        "permission": "cloudflare.read",
        "granted_at": now,
        "expires_at": "2999-01-01T00:00:00+00:00",
    }

    with pytest.raises(KeyError):
        repository.upsert_tool_permission_grant(grant, {})

    assert repository.get_active_tool_permissions("owner-a", now) == frozenset()
    assert repository.list_audit() == []


def test_failed_revoke_audit_rolls_back_permission_deletion(tmp_path):
    repository = _repository(tmp_path)
    service = ToolPermissionService(repository, AuditLogger(repository))
    service.grant("owner-a", "cloudflare.read", 3600)

    with pytest.raises(KeyError):
        repository.revoke_tool_permission_grant("owner-a", "cloudflare.read", {})

    assert service.active_permissions("owner-a") == frozenset({"cloudflare.read"})


def test_database_constraint_rejects_permissions_outside_the_explicit_allowlist(tmp_path):
    repository = _repository(tmp_path)
    now = datetime.now(UTC).isoformat()
    with pytest.raises(sqlite3.IntegrityError), repository._connection() as connection:
        connection.execute(
            """
            INSERT INTO tool_permission_grants (
                grant_id, owner_user_id, permission, granted_at, expires_at
            ) VALUES (?, ?, ?, ?, ?)
            """,
            (
                "12345678-1234-5678-1234-567812345678",
                "owner-a",
                "cloudflare.write",
                now,
                "2999-01-01T00:00:00+00:00",
            ),
        )
