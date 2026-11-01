"""Durable, privacy-minimizing workflow state and step ledger."""

from __future__ import annotations

import json
import sqlite3
from datetime import UTC, datetime
from pathlib import Path
from typing import ClassVar
from uuid import UUID, uuid4


class AgentWorkflowRepository:
    """Persist workflow and per-step state, never prompts, payloads, or outputs."""

    _STEP_TRANSITIONS: ClassVar[dict[str, set[str]]] = {
        "pending": {"running", "blocked"},
        "running": {"succeeded", "failed", "blocked"},
        "succeeded": set(),
        "failed": set(),
        "blocked": set(),
    }

    def __init__(self, database_path: Path) -> None:
        self.database_path = database_path

    def _connect(self) -> sqlite3.Connection:
        self.database_path.parent.mkdir(parents=True, exist_ok=True)
        connection = sqlite3.connect(self.database_path, timeout=5.0)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA busy_timeout = 5000")
        return connection

    def initialize(self) -> None:
        with self._connect() as connection:
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS agent_workflows (
                    workflow_id TEXT PRIMARY KEY,
                    status TEXT NOT NULL,
                    request_digest TEXT NOT NULL,
                    plan_json TEXT NOT NULL,
                    steps_json TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                )
                """
            )
            columns = {row["name"] for row in connection.execute("PRAGMA table_info(agent_workflows)")}
            if "owner_user_id" not in columns:
                connection.execute("ALTER TABLE agent_workflows ADD COLUMN owner_user_id TEXT")

    def create(self, request_digest: str, plan: dict[str, object], *, owner_user_id: str | None = None) -> dict[str, object]:
        self.initialize()
        now = datetime.now(UTC).isoformat()
        workflow_id = uuid4()
        steps = [
            {
                "step": item.get("step"),
                "kind": item.get("kind"),
                "name": item.get("name"),
                "status": "pending" if item.get("status") == "ready" else item.get("status"),
                "error_code": None,
            }
            for item in plan.get("steps", [])
            if isinstance(item, dict)
        ]
        status = "queued" if plan.get("execution_ready") else "blocked"
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO agent_workflows
                (workflow_id, status, request_digest, plan_json, steps_json, created_at, updated_at, owner_user_id)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    str(workflow_id), status, request_digest,
                    json.dumps(plan, ensure_ascii=False, sort_keys=True),
                    json.dumps(steps, ensure_ascii=False, sort_keys=True), now, now, owner_user_id,
                ),
            )
        return self.get(workflow_id)  # type: ignore[return-value]

    def start(self, workflow_id: UUID) -> None:
        self._transition(workflow_id, {"queued"}, "running")

    def record_step(
        self, workflow_id: UUID, step_number: int, status: str, error_code: str | None = None
    ) -> None:
        """Apply one legal step transition under a SQLite write lock."""
        with self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            row = connection.execute(
                "SELECT steps_json, status FROM agent_workflows WHERE workflow_id = ?",
                (str(workflow_id),),
            ).fetchone()
            if row is None:
                raise LookupError("Workflow not found")
            if row["status"] != "running":
                raise RuntimeError("Workflow is not running")
            steps = json.loads(row["steps_json"])
            target = next((item for item in steps if item["step"] == step_number), None)
            if target is None:
                raise LookupError("Workflow step not found")
            current = target["status"]
            if status not in self._STEP_TRANSITIONS.get(current, set()):
                raise RuntimeError("Workflow step transition is not allowed")
            target["status"] = status
            target["error_code"] = error_code
            connection.execute(
                "UPDATE agent_workflows SET steps_json = ?, updated_at = ? WHERE workflow_id = ?",
                (
                    json.dumps(steps, ensure_ascii=False, sort_keys=True),
                    datetime.now(UTC).isoformat(),
                    str(workflow_id),
                ),
            )

    def finish(self, workflow_id: UUID, status: str) -> None:
        if status not in {"succeeded", "failed", "blocked"}:
            raise ValueError("Unsupported terminal workflow status")
        self._transition(workflow_id, {"running"}, status)

    def _transition(self, workflow_id: UUID, expected: set[str], target: str) -> None:
        with self._connect() as connection:
            placeholders = ",".join("?" for _ in expected)
            cursor = connection.execute(
                f"UPDATE agent_workflows SET status = ?, updated_at = ? "
                f"WHERE workflow_id = ? AND status IN ({placeholders})",
                (target, datetime.now(UTC).isoformat(), str(workflow_id), *sorted(expected)),
            )
            if cursor.rowcount != 1:
                raise RuntimeError("Workflow state changed or transition is not allowed")

    def get(self, workflow_id: UUID, *, owner_user_id: str | None = None) -> dict[str, object] | None:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT * FROM agent_workflows WHERE workflow_id = ? AND (? IS NULL OR owner_user_id = ?)", (str(workflow_id), owner_user_id, owner_user_id)
            ).fetchone()
        if row is None:
            return None
        return {
            "workflow_id": row["workflow_id"],
            "status": row["status"],
            "request_digest": row["request_digest"],
            "plan": json.loads(row["plan_json"]),
            "steps": json.loads(row["steps_json"]),
            "created_at": row["created_at"],
            "updated_at": row["updated_at"],
            "stored_request": False,
            "stored_tool_payloads": False,
            "stored_tool_outputs": False,
        }
