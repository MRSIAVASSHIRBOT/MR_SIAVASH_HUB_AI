"""Owner-scoped document storage, bounded chunking, and FTS5 retrieval."""
from __future__ import annotations

import hashlib
import re
from datetime import UTC, datetime
from pathlib import Path
from uuid import UUID, uuid4

from mrhub.infrastructure.database import TaskRepository

_CHUNK_SIZE = 1200
_CHUNK_OVERLAP = 160


class KnowledgeRepository:
    """Store user-submitted text with provenance and searchable, stable chunks."""

    def __init__(self, database_path: Path) -> None:
        self.database_path = database_path
        self.tasks = TaskRepository(database_path)
        self.tasks.initialize()

    @staticmethod
    def _now() -> str:
        return datetime.now(UTC).isoformat()

    @staticmethod
    def _digest(content: str) -> str:
        return hashlib.sha256(content.encode("utf-8")).hexdigest()

    @staticmethod
    def _chunk_ranges(content: str) -> list[tuple[int, int]]:
        ranges: list[tuple[int, int]] = []
        start = 0
        while start < len(content):
            end = min(start + _CHUNK_SIZE, len(content))
            if end < len(content):
                floor = start + (_CHUNK_SIZE // 2)
                boundary = max(content.rfind("\n", floor, end), content.rfind(" ", floor, end))
                if boundary > floor:
                    end = boundary
            if content[start:end].strip():
                ranges.append((start, end))
            if end >= len(content):
                break
            start = max(start + 1, end - _CHUNK_OVERLAP)
        return ranges

    @staticmethod
    def _summary(row) -> dict[str, object]:
        return {
            "document_id": row["document_id"],
            "source_id": row["source_id"],
            "owner_user_id": row["owner_user_id"],
            "title": row["title"],
            "language": row["language"],
            "source_ref": row["canonical_origin"],
            "trust_classification": row["trust_classification"],
            "sensitivity_classification": row["sensitivity_classification"],
            "content_hash": row["content_hash"],
            "version": row["version"],
            "created_at": row["created_at"],
            "updated_at": row["updated_at"],
            "chunk_count": row["chunk_count"],
        }

    def create_document(
        self,
        owner_user_id: str,
        *,
        title: str,
        content: str,
        source_ref: str | None = None,
        language: str = "und",
        trust_classification: str = "user_supplied",
    ) -> dict[str, object]:
        normalized = content.replace("\r\n", "\n").replace("\r", "\n").strip()
        if not normalized:
            raise ValueError("Document content must not be empty")
        if len(normalized.encode("utf-8")) > 100_000:
            raise ValueError("Document exceeds the 100 KB UTF-8 limit")
        source_id = str(uuid4())
        document_id = str(uuid4())
        now = self._now()
        content_hash = self._digest(normalized)
        origin = source_ref.strip() if source_ref and source_ref.strip() else "user-submitted-text"
        with self.tasks._connection() as connection:
            connection.execute(
                """
                INSERT INTO knowledge_sources (
                    source_id, owner_user_id, scope, source_type, canonical_origin,
                    trust_classification, sensitivity_classification, content_hash,
                    created_at, updated_at
                ) VALUES (?, ?, 'private', 'user_text', ?, ?, 'private', ?, ?, ?)
                """,
                (
                    source_id,
                    owner_user_id,
                    origin,
                    trust_classification,
                    content_hash,
                    now,
                    now,
                ),
            )
            connection.execute(
                """
                INSERT INTO knowledge_documents (
                    document_id, source_id, owner_user_id, title, language, content,
                    content_hash, version, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, 1, ?, ?)
                """,
                (
                    document_id,
                    source_id,
                    owner_user_id,
                    title.strip(),
                    language,
                    normalized,
                    content_hash,
                    now,
                    now,
                ),
            )
            for index, (start, end) in enumerate(self._chunk_ranges(normalized)):
                chunk = normalized[start:end]
                connection.execute(
                    """
                    INSERT INTO knowledge_chunks (
                        chunk_id, document_id, source_id, owner_user_id, chunk_index,
                        start_offset, end_offset, content, content_hash, created_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        str(uuid4()),
                        document_id,
                        source_id,
                        owner_user_id,
                        index,
                        start,
                        end,
                        chunk,
                        self._digest(chunk),
                        now,
                    ),
                )
            row = connection.execute(
                """
                SELECT d.document_id, d.source_id, d.owner_user_id, d.title, d.language,
                       d.content_hash, d.version, d.created_at, d.updated_at,
                       s.canonical_origin, s.trust_classification, s.sensitivity_classification,
                       (SELECT COUNT(*) FROM knowledge_chunks c WHERE c.document_id = d.document_id)
                           AS chunk_count
                FROM knowledge_documents d
                JOIN knowledge_sources s ON s.source_id = d.source_id
                WHERE d.document_id = ? AND d.owner_user_id = ?
                """,
                (document_id, owner_user_id),
            ).fetchone()
        assert row is not None
        return self._summary(row)

    def list_documents(self, owner_user_id: str, limit: int = 50) -> list[dict[str, object]]:
        bounded_limit = max(1, min(limit, 100))
        with self.tasks._connection() as connection:
            rows = connection.execute(
                """
                SELECT d.document_id, d.source_id, d.owner_user_id, d.title, d.language,
                       d.content_hash, d.version, d.created_at, d.updated_at,
                       s.canonical_origin, s.trust_classification, s.sensitivity_classification,
                       (SELECT COUNT(*) FROM knowledge_chunks c WHERE c.document_id = d.document_id)
                           AS chunk_count
                FROM knowledge_documents d
                JOIN knowledge_sources s ON s.source_id = d.source_id
                WHERE d.owner_user_id = ? AND s.scope = 'private'
                  AND s.sensitivity_classification = 'private'
                ORDER BY d.updated_at DESC LIMIT ?
                """,
                (owner_user_id, bounded_limit),
            ).fetchall()
        return [self._summary(row) for row in rows]

    def get_document(self, owner_user_id: str, document_id: UUID) -> dict[str, object] | None:
        with self.tasks._connection() as connection:
            row = connection.execute(
                """
                SELECT d.document_id, d.source_id, d.owner_user_id, d.title, d.language,
                       d.content, d.content_hash, d.version, d.created_at, d.updated_at,
                       s.canonical_origin, s.trust_classification, s.sensitivity_classification,
                       (SELECT COUNT(*) FROM knowledge_chunks c WHERE c.document_id = d.document_id)
                           AS chunk_count
                FROM knowledge_documents d
                JOIN knowledge_sources s ON s.source_id = d.source_id
                WHERE d.document_id = ? AND d.owner_user_id = ?
                  AND s.scope = 'private' AND s.sensitivity_classification = 'private'
                """,
                (str(document_id), owner_user_id),
            ).fetchone()
        if row is None:
            return None
        return {**self._summary(row), "content": row["content"]}

    def delete_document(self, owner_user_id: str, document_id: UUID) -> bool:
        with self.tasks._connection() as connection:
            row = connection.execute(
                "SELECT source_id FROM knowledge_documents "
                "WHERE document_id = ? AND owner_user_id = ?",
                (str(document_id), owner_user_id),
            ).fetchone()
            if row is None:
                return False
            cursor = connection.execute(
                "DELETE FROM knowledge_sources WHERE source_id = ? AND owner_user_id = ?",
                (row["source_id"], owner_user_id),
            )
        return cursor.rowcount == 1

    def search(
        self, owner_user_id: str, query: str, limit: int = 10
    ) -> list[dict[str, object]]:
        terms = re.findall(r"[^\W_]+", query, flags=re.UNICODE)
        if not terms:
            return []
        expression = " AND ".join(f'"{term}"' for term in terms[:12])
        bounded_limit = max(1, min(limit, 25))
        with self.tasks._connection() as connection:
            rows = connection.execute(
                """
                SELECT c.chunk_id, c.document_id, c.source_id, c.chunk_index,
                       c.start_offset, c.end_offset, c.content, c.content_hash AS chunk_hash,
                       d.title, d.language, d.content_hash AS document_hash,
                       s.canonical_origin, s.trust_classification,
                       s.sensitivity_classification
                FROM knowledge_chunks_fts
                JOIN knowledge_chunks c
                  ON c.chunk_id = knowledge_chunks_fts.chunk_id
                JOIN knowledge_documents d ON d.document_id = c.document_id
                JOIN knowledge_sources s ON s.source_id = c.source_id
                WHERE knowledge_chunks_fts MATCH ?
                  AND c.owner_user_id = ?
                  AND s.scope = 'private'
                  AND s.sensitivity_classification = 'private'
                ORDER BY bm25(knowledge_chunks_fts) ASC, c.chunk_index ASC
                LIMIT ?
                """,
                (expression, owner_user_id, bounded_limit),
            ).fetchall()
        return [
            {
                "chunk_id": row["chunk_id"],
                "document_id": row["document_id"],
                "source_id": row["source_id"],
                "title": row["title"],
                "language": row["language"],
                "source_ref": row["canonical_origin"],
                "trust_classification": row["trust_classification"],
                "sensitivity_classification": row["sensitivity_classification"],
                "content": row["content"],
                "start_offset": row["start_offset"],
                "end_offset": row["end_offset"],
                "chunk_hash": row["chunk_hash"],
                "document_hash": row["document_hash"],
                "chunk_index": row["chunk_index"],
                "citation_ref": (
                    f"knowledge://documents/{row['document_id']}#chunk-{row['chunk_index']}"
                ),
            }
            for row in rows
        ]

    def export(self, owner_user_id: str) -> dict[str, object]:
        with self.tasks._connection() as connection:
            rows = connection.execute(
                """
                SELECT d.document_id, d.source_id, d.owner_user_id, d.title, d.language,
                       d.content, d.content_hash, d.version, d.created_at, d.updated_at,
                       s.canonical_origin, s.trust_classification, s.sensitivity_classification,
                       (SELECT COUNT(*) FROM knowledge_chunks c WHERE c.document_id = d.document_id)
                           AS chunk_count
                FROM knowledge_documents d
                JOIN knowledge_sources s ON s.source_id = d.source_id
                WHERE d.owner_user_id = ? AND s.scope = 'private'
                ORDER BY d.created_at ASC
                """,
                (owner_user_id,),
            ).fetchall()
        return {
            "export_version": 1,
            "exported_at": self._now(),
            "documents": [
                {**self._summary(row), "content": row["content"]} for row in rows
            ],
        }
