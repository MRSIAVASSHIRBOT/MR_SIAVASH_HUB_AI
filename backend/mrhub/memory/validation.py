"""Conservative, read-only memory validation and contradiction hints."""
from __future__ import annotations

import re
import unicodedata
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from mrhub.memory.repository import MemoryRepository

_MAX_ENTRIES = 100
_MIN_SHARED_TOKENS = 3
_DEFAULT_THRESHOLD = 0.72
_NEGATION = re.compile(
    r"(?<![\w])(?:not|never|no|without|isn't|aren't|don't|doesn't|didn't|"
    r"cannot|can't|won't)(?![\w])|(?<![\w])(?:نیست|نبود|ندار[\w]*|نمی)(?![\w])",
    re.IGNORECASE,
)
_NEGATION_EXCLUSIONS = ("not only",)


def _normalize(value: str) -> str:
    return (
        unicodedata.normalize("NFKC", value)
        .casefold()
        .replace("ي", "ی")
        .replace("ك", "ک")
        .replace("\u200c", " ")
    )


def _tokens(value: str) -> set[str]:
    normalized = _normalize(value)
    stopwords = {
        "a", "an", "the", "i", "you", "he", "she", "it", "we", "they",
        "am", "is", "are", "was", "were", "be", "been", "being", "do",
        "does", "did", "to", "of", "for", "in", "on", "at", "and", "or",
        "but", "my", "your", "his", "her", "our", "their", "this", "that",
        "من", "تو", "او", "ما", "شما", "آنها", "این", "آن", "را", "به",
        "از", "در", "با", "برای", "و", "یا", "که",
    }
    return {
        token for token in re.findall(r"[^\W_]+", normalized, flags=re.UNICODE)
        if len(token) > 1 and token not in stopwords
    }


def _has_negation(value: str) -> bool:
    normalized = _normalize(value)
    if any(phrase in normalized for phrase in _NEGATION_EXCLUSIONS):
        normalized = normalized.replace("not only", "")
    return _NEGATION.search(normalized) is not None


def _expired(value: object) -> bool:
    if not isinstance(value, str) or not value:
        return False
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError:
        return False
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        return False
    return parsed.astimezone(UTC) <= datetime.now(UTC)


class MemoryValidationEngine:
    """Flag explicit polarity conflicts and weakly verified notes for owner review.

    This is a heuristic triage tool, not a fact checker. It never mutates memory.
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
        limit: int = _MAX_ENTRIES,
        threshold: float = _DEFAULT_THRESHOLD,
    ) -> dict[str, Any]:
        if not 1 <= limit <= _MAX_ENTRIES:
            raise ValueError("Validation limit must be between 1 and 100")
        if not 0.65 <= threshold <= 1.0:
            raise ValueError("Contradiction threshold must be between 0.65 and 1.0")

        entries = self.repository.list_entries(
            owner_user_id, limit=limit, include_expired=True
        )
        active: list[dict[str, object]] = []
        expired: list[dict[str, object]] = []
        review_queue: list[dict[str, object]] = []

        for entry in entries:
            content = entry.get("content")
            if not isinstance(content, str):
                continue
            if _expired(entry.get("expires_at")):
                expired.append({
                    "memory_id": entry["memory_id"],
                    "category": entry["category"],
                    "excerpt": content[:300],
                    "reason": "expired",
                    "requires_owner_review": True,
                })
                continue
            active.append(entry)
            confidence = entry.get("confidence")
            verification_status = entry.get("verification_status")
            reasons: list[str] = []
            if verification_status != "user_approved":
                reasons.append("not_user_approved")
            if isinstance(confidence, (int, float)) and confidence < 0.8:
                reasons.append("low_confidence")
            if reasons:
                review_queue.append({
                    "memory_id": entry["memory_id"],
                    "category": entry["category"],
                    "excerpt": content[:300],
                    "confidence": confidence,
                    "verification_status": verification_status,
                    "reasons": reasons,
                    "requires_owner_review": True,
                })

        prepared: list[tuple[dict[str, object], set[str], bool]] = []
        for entry in active:
            content = str(entry["content"])
            tokens = _tokens(content)
            if len(tokens) >= _MIN_SHARED_TOKENS:
                prepared.append((entry, tokens, _has_negation(content)))

        contradictions: list[dict[str, object]] = []
        for index, (left, left_tokens, left_negated) in enumerate(prepared):
            for right, right_tokens, right_negated in prepared[index + 1:]:
                if left.get("category") != right.get("category"):
                    continue
                if left_negated == right_negated:
                    continue
                similarity = self._similarity(left_tokens, right_tokens)
                if similarity < threshold:
                    continue
                contradictions.append({
                    "proposal_type": "possible_contradiction",
                    "memory_ids": [left["memory_id"], right["memory_id"]],
                    "category": left["category"],
                    "similarity": round(similarity, 4),
                    "confidence": "heuristic",
                    "evidence": "similar wording with different negation polarity",
                    "excerpts": [
                        str(left["content"])[:300],
                        str(right["content"])[:300],
                    ],
                    "requires_owner_review": True,
                    "automatic_change": False,
                })

        contradictions.sort(
            key=lambda item: (
                -float(item["similarity"]),
                str(item["memory_ids"][0]),
                str(item["memory_ids"][1]),
            )
        )
        return {
            "engine": "deterministic_memory_validation_v1",
            "entries_scanned": len(entries),
            "active_entries": len(active),
            "expired_count": len(expired),
            "unverified_count": len(review_queue),
            "contradiction_count": len(contradictions),
            "expired_entries": expired[:50],
            "review_queue": review_queue[:50],
            "contradictions": contradictions[:50],
            "state_changed": False,
            "limitations": [
                "Contradictions are heuristic polarity conflicts, not verified factual contradictions.",
                "Negation and token matching can miss paraphrases and produce false positives.",
                "The engine cannot verify truth against external sources or session transcripts.",
                "No memory is approved, rewritten, merged, or deleted automatically.",
            ],
        }
