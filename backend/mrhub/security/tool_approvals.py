"""Owner-scoped, one-time approval receipts bound to an exact tool action."""

from __future__ import annotations

import hashlib
import json
import marshal
import re
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from uuid import UUID

from mrhub.infrastructure.database import TaskRepository
from mrhub.tools.registry import ToolDefinition

MIN_TOOL_APPROVAL_TTL_SECONDS = 60
MAX_TOOL_APPROVAL_TTL_SECONDS = 900
_SHA256_PATTERN = re.compile(r"^[0-9a-f]{64}$")


class ToolApprovalError(RuntimeError):
    """Raised when a tool approval cannot be safely created or consumed."""


def _canonical_json(value: object) -> bytes:
    try:
        return json.dumps(
            value,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        ).encode("utf-8")
    except (TypeError, ValueError, OverflowError) as exc:
        raise ToolApprovalError("Tool action is not finite canonical JSON data") from exc


def canonical_tool_payload(tool: ToolDefinition, payload: dict[str, object]) -> tuple[dict[str, object], str]:
    """Validate and fingerprint exactly the normalized input the handler receives."""
    validated = tool.input_model.model_validate(payload)
    normalized = validated.model_dump(mode="json")
    digest = hashlib.sha256(_canonical_json(normalized)).hexdigest()
    return normalized, digest


def tool_definition_fingerprint(tool: ToolDefinition) -> str:
    """Bind approvals to schemas, policy metadata and the registered handler code."""
    handler = tool.handler
    code = getattr(handler, "__code__", None)
    if code is not None:
        handler_code_digest = hashlib.sha256(marshal.dumps(code)).hexdigest()
    else:
        handler_code_digest = hashlib.sha256(
            f"{type(handler).__module__}:{type(handler).__qualname__}".encode("utf-8")
        ).hexdigest()
    contract = {
        "name": tool.name,
        "risk_class": tool.risk_class.value,
        "required_permissions": sorted(tool.required_permissions),
        "external_side_effect": tool.external_side_effect,
        "input_schema": tool.input_model.model_json_schema(),
        "output_schema": tool.output_model.model_json_schema(),
        "handler_module": getattr(handler, "__module__", type(handler).__module__),
        "handler_qualname": getattr(handler, "__qualname__", type(handler).__qualname__),
        "handler_code_digest": handler_code_digest,
    }
    return hashlib.sha256(_canonical_json(contract)).hexdigest()


class ToolInvocationApprovalStore:
    """Persist only action digests and lifecycle metadata; never persist payloads."""

    def __init__(
        self,
        repository: TaskRepository,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self.repository = repository
        self._clock = clock or (lambda: datetime.now(UTC))

    def _now(self) -> datetime:
        value = self._clock()
        if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() is None:
            raise ToolApprovalError("Tool approval clock must be timezone-aware")
        return value.astimezone(UTC)

    @staticmethod
    def _validate_digest(value: str) -> None:
        if not isinstance(value, str) or _SHA256_PATTERN.fullmatch(value) is None:
            raise ToolApprovalError("Tool approval digest is invalid")

    @staticmethod
    def _validate_identifiers(approval_id: str, owner_user_id: str, tool_name: str) -> str:
        try:
            normalized = str(UUID(approval_id))
        except (TypeError, ValueError, AttributeError) as exc:
            raise ToolApprovalError("Tool approval identifier is invalid") from exc
        if normalized != approval_id:
            raise ToolApprovalError("Tool approval identifier must be canonical")
        if not isinstance(owner_user_id, str) or not owner_user_id.strip() or len(owner_user_id) > 200:
            raise ToolApprovalError("Tool approval owner is invalid")
        if not isinstance(tool_name, str) or not 1 <= len(tool_name) <= 80:
            raise ToolApprovalError("Tool name is invalid")
        return normalized

    def create(
        self,
        *,
        approval_id: str,
        owner_user_id: str,
        tool_name: str,
        payload_digest: str,
        tool_fingerprint: str,
        ttl_seconds: int = 300,
    ) -> dict[str, object]:
        """Create a pending receipt for one owner, tool definition and exact payload."""
        normalized_id = self._validate_identifiers(approval_id, owner_user_id, tool_name)
        self._validate_digest(payload_digest)
        self._validate_digest(tool_fingerprint)
        if (
            isinstance(ttl_seconds, bool)
            or not isinstance(ttl_seconds, int)
            or not MIN_TOOL_APPROVAL_TTL_SECONDS <= ttl_seconds <= MAX_TOOL_APPROVAL_TTL_SECONDS
        ):
            raise ToolApprovalError("Tool approval expiry is outside the allowed range")

        now = self._now()
        created_at = now.isoformat()
        expires_at = (now + timedelta(seconds=ttl_seconds)).isoformat()
        with self.repository._connection() as connection:
            connection.execute("BEGIN IMMEDIATE")
            connection.execute(
                """
                INSERT INTO tool_invocation_approvals (
                    approval_id, owner_user_id, tool_name, payload_digest,
                    tool_fingerprint, status, created_at, expires_at,
                    decided_at, consumed_at
                ) VALUES (?, ?, ?, ?, ?, 'pending', ?, ?, NULL, NULL)
                """,
                (
                    normalized_id,
                    owner_user_id,
                    tool_name,
                    payload_digest,
                    tool_fingerprint,
                    created_at,
                    expires_at,
                ),
            )
        return {
            "approval_id": normalized_id,
            "owner_user_id": owner_user_id,
            "tool_name": tool_name,
            "payload_digest": payload_digest,
            "tool_fingerprint": tool_fingerprint,
            "status": "pending",
            "created_at": created_at,
            "expires_at": expires_at,
            "decided_at": None,
            "consumed_at": None,
        }

    def get(self, approval_id: str, *, owner_user_id: str) -> dict[str, object] | None:
        try:
            normalized_id = str(UUID(approval_id))
        except (TypeError, ValueError, AttributeError):
            return None
        if normalized_id != approval_id or not isinstance(owner_user_id, str):
            return None
        with self.repository._connection() as connection:
            row = connection.execute(
                """
                SELECT approval_id, owner_user_id, tool_name, payload_digest,
                       tool_fingerprint, status, created_at, expires_at,
                       decided_at, consumed_at
                FROM tool_invocation_approvals
                WHERE approval_id = ? AND owner_user_id = ?
                """,
                (normalized_id, owner_user_id),
            ).fetchone()
        return dict(row) if row is not None else None

    def decide(
        self,
        approval_id: str,
        *,
        owner_user_id: str,
        tool_name: str,
        tool_fingerprint: str,
        decision: str,
    ) -> dict[str, object] | None:
        """Approve or reject a still-pending receipt only while its definition is current."""
        normalized_id = self._validate_identifiers(approval_id, owner_user_id, tool_name)
        self._validate_digest(tool_fingerprint)
        if decision not in {"approved", "rejected"}:
            raise ToolApprovalError("Tool approval decision is invalid")
        now = self._now()
        now_text = now.isoformat()
        with self.repository._connection() as connection:
            connection.execute("BEGIN IMMEDIATE")
            row = connection.execute(
                """
                SELECT approval_id, owner_user_id, tool_name, payload_digest,
                       tool_fingerprint, status, created_at, expires_at,
                       decided_at, consumed_at
                FROM tool_invocation_approvals
                WHERE approval_id = ? AND owner_user_id = ?
                """,
                (normalized_id, owner_user_id),
            ).fetchone()
            if row is None:
                return None
            if row["tool_name"] != tool_name:
                raise ToolApprovalError("Tool approval does not match the requested tool")
            if row["status"] != "pending":
                raise ToolApprovalError("Tool approval is no longer pending")
            if row["expires_at"] <= now_text or row["tool_fingerprint"] != tool_fingerprint:
                connection.execute(
                    "UPDATE tool_invocation_approvals SET status = 'expired' "
                    "WHERE approval_id = ? AND status = 'pending'",
                    (normalized_id,),
                )
                expired = connection.execute(
                    """
                    SELECT approval_id, owner_user_id, tool_name, payload_digest,
                           tool_fingerprint, status, created_at, expires_at,
                           decided_at, consumed_at
                    FROM tool_invocation_approvals
                    WHERE approval_id = ? AND owner_user_id = ?
                    """,
                    (normalized_id, owner_user_id),
                ).fetchone()
                return dict(expired) if expired is not None else None
            cursor = connection.execute(
                """
                UPDATE tool_invocation_approvals
                SET status = ?, decided_at = ?
                WHERE approval_id = ? AND owner_user_id = ?
                  AND status = 'pending' AND expires_at > ?
                """,
                (decision, now_text, normalized_id, owner_user_id, now_text),
            )
            if cursor.rowcount != 1:
                raise ToolApprovalError("Tool approval state changed concurrently")
            updated = connection.execute(
                """
                SELECT approval_id, owner_user_id, tool_name, payload_digest,
                       tool_fingerprint, status, created_at, expires_at,
                       decided_at, consumed_at
                FROM tool_invocation_approvals
                WHERE approval_id = ? AND owner_user_id = ?
                """,
                (normalized_id, owner_user_id),
            ).fetchone()
            return dict(updated) if updated is not None else None

    def validate(
        self,
        approval_id: str,
        *,
        owner_user_id: str,
        tool_name: str,
        payload_digest: str,
        tool_fingerprint: str,
    ) -> bool:
        """Check a receipt without consuming it; the executor must consume again atomically."""
        normalized_id = self._validate_identifiers(approval_id, owner_user_id, tool_name)
        self._validate_digest(payload_digest)
        self._validate_digest(tool_fingerprint)
        now_text = self._now().isoformat()
        with self.repository._connection() as connection:
            connection.execute("BEGIN IMMEDIATE")
            row = connection.execute(
                """
                SELECT tool_name, payload_digest, tool_fingerprint, status, expires_at
                FROM tool_invocation_approvals
                WHERE approval_id = ? AND owner_user_id = ?
                """,
                (normalized_id, owner_user_id),
            ).fetchone()
            if row is None:
                return False
            if row["status"] == "approved" and row["expires_at"] <= now_text:
                connection.execute(
                    "UPDATE tool_invocation_approvals SET status = 'expired' "
                    "WHERE approval_id = ? AND status = 'approved'",
                    (normalized_id,),
                )
                return False
            return (
                row["status"] == "approved"
                and row["expires_at"] > now_text
                and row["tool_name"] == tool_name
                and row["payload_digest"] == payload_digest
                and row["tool_fingerprint"] == tool_fingerprint
            )

    def consume(
        self,
        approval_id: str,
        *,
        owner_user_id: str,
        tool_name: str,
        payload_digest: str,
        tool_fingerprint: str,
    ) -> bool:
        """Atomically consume one approved receipt immediately before handler invocation."""
        normalized_id = self._validate_identifiers(approval_id, owner_user_id, tool_name)
        self._validate_digest(payload_digest)
        self._validate_digest(tool_fingerprint)
        now_text = self._now().isoformat()
        with self.repository._connection() as connection:
            connection.execute("BEGIN IMMEDIATE")
            row = connection.execute(
                """
                SELECT tool_name, payload_digest, tool_fingerprint, status, expires_at
                FROM tool_invocation_approvals
                WHERE approval_id = ? AND owner_user_id = ?
                """,
                (normalized_id, owner_user_id),
            ).fetchone()
            if row is None:
                return False
            if row["status"] == "approved" and row["expires_at"] <= now_text:
                connection.execute(
                    "UPDATE tool_invocation_approvals SET status = 'expired' "
                    "WHERE approval_id = ? AND status = 'approved'",
                    (normalized_id,),
                )
                return False
            if (
                row["status"] != "approved"
                or row["tool_name"] != tool_name
                or row["payload_digest"] != payload_digest
                or row["tool_fingerprint"] != tool_fingerprint
                or row["expires_at"] <= now_text
            ):
                return False
            cursor = connection.execute(
                """
                UPDATE tool_invocation_approvals
                SET status = 'consumed', consumed_at = ?
                WHERE approval_id = ? AND owner_user_id = ?
                  AND status = 'approved' AND expires_at > ?
                  AND tool_name = ? AND payload_digest = ? AND tool_fingerprint = ?
                """,
                (
                    now_text,
                    normalized_id,
                    owner_user_id,
                    now_text,
                    tool_name,
                    payload_digest,
                    tool_fingerprint,
                ),
            )
            return cursor.rowcount == 1
