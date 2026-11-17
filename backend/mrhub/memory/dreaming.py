"""Conservative, deterministic memory review proposals (no automatic mutation)."""
from __future__ import annotations

import re
import unicodedata
from pathlib import Path
from typing import Any

from mrhub.memory.repository import MemoryRepository

_MIN_TOKENS = 4
_DEFAULT_SIMILARITY_THRESHOLD = 0.82
_MAX_REVIEW_ENTRIES = 100


def _tokens(value: str) -> set[str]:
    normalized = unicodedata.normalize("NFKC", value).casefold()
    normalized = normalized.replace("ي", "ی").replace("ك", "ک").replace("\u200c", " ")
    return {
        token
        for token in re.findall(r"[^\W_]+", normalized, flags=re.UNICODE)
        if len(token) > 1
    }


class MemoryDreamingEngine:
    """Find likely duplicate notes and return review proposals without changing memory.

    This first deterministic pass deliberately does not infer contradictions,
    rewrite facts, or delete entries. A human must review any proposed consolidation.
    """

    def __init__(self, database_path: Path) -> None:
        self.repository = MemoryRepository(database_path)

    @staticmethod
    def _similarity(left: set[str], right: set[str]) -> float:
        union = left | right
        return len(left & right) / len(union) if union else 0.0

    def preview(
        self,
        owner_user_id: str,
        *,
        limit: int = _MAX_REVIEW_ENTRIES,
        threshold: float = _DEFAULT_SIMILARITY_THRESHOLD,
    ) -> dict[str, Any]:
        if not 1 <= limit <= _MAX_REVIEW_ENTRIES:
            raise ValueError("Review limit must be between 1 and 100")
        if not 0.75 <= threshold <= 1.0:
            raise ValueError("Similarity threshold must be between 0.75 and 1.0")

        entries = self.repository.list_entries(owner_user_id, limit=limit)
        prepared: list[tuple[dict[str, object], set[str]]] = []
        for entry in entries:
            content = entry.get("content")
            if isinstance(content, str):
                tokens = _tokens(content)
                if len(tokens) >= _MIN_TOKENS:
                    prepared.append((entry, tokens))

        proposals: list[dict[str, Any]] = []
        for index, (left, left_tokens) in enumerate(prepared):
            for right, right_tokens in prepared[index + 1 :]:
                if left.get("category") != right.get("category"):
                    continue
                similarity = self._similarity(left_tokens, right_tokens)
                if similarity < threshold:
                    continue

                # list_entries is newest-first. Keep the newer note as the
                # suggested canonical record; never mutate or delete either note.
                canonical, redundant = left, right
                proposals.append(
                    {
                        "proposal_type": "possible_duplicate",
                        "canonical_memory_id": canonical["memory_id"],
                        "candidate_memory_id": redundant["memory_id"],
                        "category": canonical["category"],
                        "similarity": round(similarity, 4),
                        "confidence": "heuristic",
                        "canonical_excerpt": str(canonical["content"])[:500],
                        "candidate_excerpt": str(redundant["content"])[:500],
                        "recommendation": (
                            "Review both notes; manually merge only if their meaning "
                            "and provenance are genuinely equivalent."
                        ),
                        "requires_owner_review": True,
                        "automatic_change": False,
                    }
                )

        proposals.sort(
            key=lambda item: (
                -float(item["similarity"]),
                str(item["canonical_memory_id"]),
                str(item["candidate_memory_id"]),
            )
        )
        return {
            "engine": "deterministic_memory_review_v1",
            "entries_scanned": len(entries),
            "eligible_entries": len(prepared),
            "proposal_count": len(proposals),
            "proposals": proposals[:100],
            "state_changed": False,
            "limitations": [
                "Only likely duplicates in the same category are detected.",
                "Contradictions, factual correctness, and semantic equivalence are not inferred.",
                "This preview reviews saved memory entries, not raw session transcripts.",
                "No entry is merged, rewritten, or deleted automatically.",
            ],
        }
