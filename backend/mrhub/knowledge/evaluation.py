"""Repeatable, local-only evaluation metrics for SQLite FTS5 retrieval."""

from __future__ import annotations

import json
import tempfile
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from mrhub.infrastructure.database import TaskRepository
from mrhub.knowledge.repository import KnowledgeRepository
from mrhub.security.auth import AuthService

MAX_EVALUATION_CASES = 100
MAX_QUERY_CHARS = 200
MAX_RELEVANT_DOCUMENTS_PER_CASE = 100
MAX_TOTAL_RELEVANT_DOCUMENT_IDS = 1_000
MAX_DOCUMENT_ID_CHARS = 64
MAX_K = 25


@dataclass(frozen=True)
class RetrievalCase:
    """One query and its reviewed set of relevant document identifiers."""

    query: str
    relevant_document_ids: tuple[str, ...]


def _validated_relevant_ids(case: RetrievalCase) -> set[str]:
    identifiers = case.relevant_document_ids
    if not isinstance(identifiers, (tuple, list)):
        raise TypeError("relevant_document_ids must be a tuple or list")
    if not identifiers or len(identifiers) > MAX_RELEVANT_DOCUMENTS_PER_CASE:
        raise ValueError(
            "Each case must contain between 1 and "
            f"{MAX_RELEVANT_DOCUMENTS_PER_CASE} relevant document IDs"
        )

    normalized: list[str] = []
    for identifier in identifiers:
        if not isinstance(identifier, str):
            raise TypeError("Each relevant document ID must be a string")
        if not identifier or len(identifier) > MAX_DOCUMENT_ID_CHARS:
            raise ValueError("Each relevant document ID must be a non-empty bounded string")
        normalized.append(identifier)

    if len(set(normalized)) != len(normalized):
        raise ValueError("Relevant document IDs must not contain duplicates")
    return set(normalized)


def evaluate_retrieval(
    repository: KnowledgeRepository,
    owner_user_id: str,
    cases: Sequence[RetrievalCase],
    *,
    k: int = 5,
) -> dict[str, Any]:
    """Compute bounded document-level top-k metrics without returning source text."""
    if not isinstance(k, int) or isinstance(k, bool):
        raise TypeError("k must be an integer")
    if not 1 <= k <= MAX_K:
        raise ValueError(f"k must be between 1 and {MAX_K}")
    if not isinstance(owner_user_id, str):
        raise TypeError("owner_user_id must be a string")
    if not owner_user_id or len(owner_user_id) > 80:
        raise ValueError("owner_user_id must contain 1 to 80 characters")
    if not isinstance(cases, Sequence) or isinstance(cases, (str, bytes)):
        raise TypeError("cases must be a sequence")
    if not cases or len(cases) > MAX_EVALUATION_CASES:
        raise ValueError(
            f"cases must contain between 1 and {MAX_EVALUATION_CASES} items"
        )

    results: list[dict[str, object]] = []
    precision_values: list[float] = []
    recall_values: list[float] = []
    reciprocal_ranks: list[float] = []
    hits = 0
    total_relevant_ids = 0

    for case in cases:
        if not isinstance(case, RetrievalCase):
            raise TypeError("Every evaluation case must be a RetrievalCase")
        if (
            not isinstance(case.query, str)
        ):
            raise TypeError("Each evaluation query must be a string")
        if not case.query.strip() or len(case.query) > MAX_QUERY_CHARS:
            raise ValueError(
                f"Each query must contain 1 to {MAX_QUERY_CHARS} characters"
            )

        relevant = _validated_relevant_ids(case)
        total_relevant_ids += len(relevant)
        if total_relevant_ids > MAX_TOTAL_RELEVANT_DOCUMENT_IDS:
            raise ValueError(
                "Total relevant document IDs exceed "
                f"{MAX_TOTAL_RELEVANT_DOCUMENT_IDS}"
            )

        # KnowledgeRepository.search returns chunk hits. Collapse those hits to
        # unique documents in rank order before computing document-level metrics.
        chunk_hits = repository.search(owner_user_id, case.query.strip(), limit=MAX_K)
        retrieved_ids: list[str] = []
        seen_ids: set[str] = set()
        for item in chunk_hits:
            document_id = str(item["document_id"])
            if document_id not in seen_ids:
                seen_ids.add(document_id)
                retrieved_ids.append(document_id)
                if len(retrieved_ids) == k:
                    break

        relevant_ranks = [
            rank
            for rank, document_id in enumerate(retrieved_ids, start=1)
            if document_id in relevant
        ]
        relevant_found = len(set(retrieved_ids) & relevant)
        precision = relevant_found / k
        recall = relevant_found / len(relevant)
        reciprocal_rank = 1 / relevant_ranks[0] if relevant_ranks else 0.0
        if relevant_ranks:
            hits += 1

        precision_values.append(precision)
        recall_values.append(recall)
        reciprocal_ranks.append(reciprocal_rank)
        results.append(
            {
                "query": case.query.strip(),
                "retrieved_document_ids": retrieved_ids,
                "relevant_found": relevant_found,
                "relevant_total": len(relevant),
                "precision_at_k": precision,
                "recall_at_k": recall,
                "reciprocal_rank": reciprocal_rank,
            }
        )

    count = len(results)
    return {
        "evaluation_version": 1,
        "cases_evaluated": count,
        "k": k,
        "precision_at_k": sum(precision_values) / count,
        "recall_at_k": sum(recall_values) / count,
        "mean_reciprocal_rank": sum(reciprocal_ranks) / count,
        "hit_rate": hits / count,
        "case_results": results,
        "retrieved_source_text_included": False,
        "network_accessed": False,
    }


def _create_fixture_owner(database_path: Path) -> str:
    tasks = TaskRepository(database_path)
    tasks.initialize()
    AuthService(tasks).initialize_owner("retrieval-evaluation-fixture-password")
    owner = tasks.get_auth_user("owner")
    if owner is None:
        raise RuntimeError("Could not initialize the synthetic evaluation owner")
    return str(owner["user_id"])


def run_reference_evaluation() -> dict[str, Any]:
    """Run a synthetic benchmark in a temporary database; no user data is read."""
    fixtures = [
        (
            "DNS Troubleshooting",
            (
                "DNS troubleshooting starts by checking resolver configuration, name resolution, "
                "the configured DNS server, and whether the hostname resolves to the expected address."
            ),
        ),
        (
            "Signed Media Delivery",
            (
                "Signed media URL delivery uses HTTPS, an HMAC signature, an asset identifier, "
                "and a short expiry to let an external image service fetch an approved image."
            ),
        ),
        (
            "Worker Lease Safety",
            (
                "A worker lease and fencing token prevent stale workers from committing workflow state "
                "after ownership changes; ambiguous external operations require reconciliation."
            ),
        ),
        (
            "Python AST Review",
            (
                "Python AST analysis parses source structure without importing or executing code, "
                "and reports line-specific static findings for human review."
            ),
        ),
        (
            "SQLite Backup Restore",
            (
                "SQLite backup and restore verifies a checksum manifest, file size, and database "
                "integrity before creating a new destination without overwriting existing files."
            ),
        ),
    ]

    with tempfile.TemporaryDirectory(prefix="mrhub-retrieval-eval-") as directory:
        database_path = Path(directory) / "evaluation.sqlite3"
        owner_id = _create_fixture_owner(database_path)
        repository = KnowledgeRepository(database_path)
        document_ids: dict[str, str] = {}
        for title, content in fixtures:
            document = repository.create_document(
                owner_id,
                title=title,
                content=content,
                source_ref=f"evaluation-fixture://{title.lower().replace(' ', '-')}",
            )
            document_ids[title] = str(document["document_id"])

        cases = (
            RetrievalCase(
                "DNS troubleshooting resolver",
                (document_ids["DNS Troubleshooting"],),
            ),
            RetrievalCase(
                "signed media URL HMAC",
                (document_ids["Signed Media Delivery"],),
            ),
            RetrievalCase(
                "worker lease fencing token",
                (document_ids["Worker Lease Safety"],),
            ),
            RetrievalCase(
                "Python AST analysis",
                (document_ids["Python AST Review"],),
            ),
            RetrievalCase(
                "SQLite backup restore checksum",
                (document_ids["SQLite Backup Restore"],),
            ),
        )
        report = evaluate_retrieval(repository, owner_id, cases, k=3)
        return {
            **report,
            "benchmark": "synthetic_fixture_corpus",
            "fixture_documents": len(fixtures),
            "production_quality_claim": False,
        }


def main() -> None:
    print(json.dumps(run_reference_evaluation(), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
