"""Privacy-minimizing SQLite history for completed agent tool runs."""

from __future__ import annotations

import hashlib
import json
import sqlite3
from datetime import UTC, datetime
from pathlib import Path
from uuid import UUID, uuid4


class AgentRunRepository:
    """Persist run metadata without storing prompts, tool inputs, or tool outputs."""

    def __init__(self, database_path: Path) -> None:
        self.database_path = database_path

    def _connect(self) -> sqlite3.Connection:
        self.database_path.parent.mkdir(parents=True, exist_ok=True)
        connection = sqlite3.connect(self.database_path, timeout=5.0)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA busy_timeout = 5000")
        return connection

    def initialize(self) -> None:
        """Apply the canonical versioned schema; repositories never issue runtime DDL."""
        from mrhub.infrastructure.database import TaskRepository

        TaskRepository(self.database_path).initialize()

    def record(
        self,
        request_payload: dict[str, object],
        execution: dict[str, object],
        *,
        owner_user_id: str | None = None,
    ) -> dict[str, object]:
        self.initialize()
        requested_tools = request_payload.get("tools", [])
        safe_request_metadata = {
            "goal_length": len(str(request_payload.get("goal", ""))),
            "tool_names": [
                str(item.get("name"))
                for item in requested_tools
                if isinstance(item, dict) and "name" in item
            ]
            if isinstance(requested_tools, list)
            else [],
            "requires_text": bool(request_payload.get("requires_text", True)),
            "requires_vision": bool(request_payload.get("requires_vision", False)),
            "requires_audio": bool(request_payload.get("requires_audio", False)),
            "requires_tool_calling": bool(request_payload.get("requires_tool_calling", False)),
            "prefer_local": bool(request_payload.get("prefer_local", False)),
        }
        request_bytes = json.dumps(
            safe_request_metadata, ensure_ascii=False, sort_keys=True, separators=(",", ":")
        ).encode("utf-8")
        digest = hashlib.sha256(request_bytes).hexdigest()
        plan = execution["plan"]
        if not isinstance(plan, dict):
            raise TypeError("Execution response does not contain a valid plan")
        steps = plan.get("steps", [])
        tool_names = [
            str(step["name"])
            for step in steps
            if isinstance(step, dict) and step.get("kind") == "tool" and "name" in step
        ]
        results = execution.get("results", [])
        status = (
            "blocked"
            if execution.get("blocked")
            else "succeeded"
            if execution.get("execution_completed")
            else "failed"
        )
        selection = plan.get("selected_provider", {})
        provider_name = selection.get("provider") if isinstance(selection, dict) else None
        model_name = selection.get("model") if isinstance(selection, dict) else None
        error_code = execution.get("error_code")
        created_at = datetime.now(UTC).isoformat()
        run_id = uuid4()

        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO agent_runs (
                    run_id, request_digest, status, provider_name, model_name,
                    plan_json, tool_names_json, executed_tool_count, error_code, created_at,
                    owner_user_id
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    str(run_id),
                    digest,
                    status,
                    provider_name,
                    model_name,
                    json.dumps(plan, ensure_ascii=False, sort_keys=True),
                    json.dumps(tool_names, ensure_ascii=False),
                    len(results) if isinstance(results, list) else 0,
                    error_code,
                    created_at,
                    owner_user_id,
                ),
            )
        return self.get(run_id, owner_user_id=owner_user_id)  # type: ignore[return-value]

    def get(self, run_id: UUID, *, owner_user_id: str | None = None) -> dict[str, object] | None:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT * FROM agent_runs WHERE run_id = ? AND owner_user_id = ?",
                (str(run_id), owner_user_id),
            ).fetchone()
        if row is None:
            return None
        return {
            "run_id": row["run_id"],
            "status": row["status"],
            "request_digest": row["request_digest"],
            "provider": row["provider_name"],
            "model": row["model_name"],
            "plan": json.loads(row["plan_json"]),
            "tool_names": json.loads(row["tool_names_json"]),
            "executed_tool_count": row["executed_tool_count"],
            "error_code": row["error_code"],
            "created_at": row["created_at"],
            "stored_payloads": False,
            "stored_tool_outputs": False,
        }
