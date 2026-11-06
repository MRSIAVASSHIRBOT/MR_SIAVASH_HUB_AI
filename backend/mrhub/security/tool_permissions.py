"""Owner-scoped, expiring permission grants for explicitly registered tools."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import uuid4

from mrhub.infrastructure.database import TaskRepository
from mrhub.security.audit import AuditLogger

DEFAULT_GRANT_SECONDS = 3_600
MIN_GRANT_SECONDS = 60
MAX_GRANT_SECONDS = 86_400
GRANTABLE_PERMISSIONS = frozenset({"cloudflare.read"})


class ToolPermissionService:
    """Manage the small allow-listed set of permissions through owner identity."""

    def __init__(self, repository: TaskRepository, audit: AuditLogger) -> None:
        self.repository = repository
        self.audit = audit

    @staticmethod
    def _validate_permission(permission: str) -> None:
        if permission not in GRANTABLE_PERMISSIONS:
            raise ValueError("Permission is not grantable")

    @staticmethod
    def _validate_expiry(expires_in_seconds: int) -> None:
        if (
            isinstance(expires_in_seconds, bool)
            or not isinstance(expires_in_seconds, int)
            or not MIN_GRANT_SECONDS <= expires_in_seconds <= MAX_GRANT_SECONDS
        ):
            raise ValueError("Permission grant expiry is outside the allowed range")

    def grant(
        self,
        owner_user_id: str,
        permission: str,
        expires_in_seconds: int = DEFAULT_GRANT_SECONDS,
    ) -> dict[str, str]:
        self._validate_permission(permission)
        self._validate_expiry(expires_in_seconds)
        if not owner_user_id or len(owner_user_id) > 80:
            raise ValueError("Invalid permission owner")

        now = datetime.now(UTC)
        expires_at = now + timedelta(seconds=expires_in_seconds)
        grant = {
            "grant_id": str(uuid4()),
            "owner_user_id": owner_user_id,
            "permission": permission,
            "granted_at": now.isoformat(),
            "expires_at": expires_at.isoformat(),
        }
        event = self.audit.build_event(
            event_type="tool.permission_granted",
            outcome="success",
            subject_id=grant["grant_id"],
            subject_type="tool_permission",
            actor_type="user",
            actor_id=owner_user_id,
            metadata={
                "permission": permission,
                "status": "active",
                "reason_code": "owner_granted",
            },
        )
        self.repository.upsert_tool_permission_grant(
            grant,
            event.model_dump(mode="json"),
        )
        return {
            "permission": permission,
            "granted_at": grant["granted_at"],
            "expires_at": grant["expires_at"],
        }

    def revoke(self, owner_user_id: str, permission: str) -> bool:
        self._validate_permission(permission)
        if not owner_user_id or len(owner_user_id) > 80:
            raise ValueError("Invalid permission owner")
        event = self.audit.build_event(
            event_type="tool.permission_revoked",
            outcome="success",
            subject_id=permission,
            subject_type="tool_permission",
            actor_type="user",
            actor_id=owner_user_id,
            metadata={
                "permission": permission,
                "status": "revoked",
                "reason_code": "owner_revoked",
            },
        )
        return self.repository.revoke_tool_permission_grant(
            owner_user_id,
            permission,
            event.model_dump(mode="json"),
        )

    def list_active(self, owner_user_id: str) -> list[dict[str, str]]:
        return self.repository.list_tool_permission_grants(
            owner_user_id,
            datetime.now(UTC).isoformat(),
        )

    def active_permissions(self, owner_user_id: str) -> frozenset[str]:
        return self.repository.get_active_tool_permissions(
            owner_user_id,
            datetime.now(UTC).isoformat(),
        )
