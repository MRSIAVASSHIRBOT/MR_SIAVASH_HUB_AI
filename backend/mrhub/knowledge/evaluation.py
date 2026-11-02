"""Repeatable, local-only evaluation metrics for SQLite FTS5 retrieval."""
from __future__ import annotations

import json
import tempfile
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

from mrhub.knowledge.repository import KnowledgeRepository

MAX_EVALUATION_CASES = 100


@dataclass(frozen=True)
class RetrievalCase:
    query: str
    relevant_document_ids: tuple[str, ...]


def evaluate_retrieval(
    repository: KnowledgeRepository,
    owner_user_id: str,
    cases: Sequence[RetrievalCase],
    *,
    k: int = 5,
) -> dict[str, object]:
    """Compute deterministic top-k metrics without returning retrieved document text."""
    if not 1 <= k <= 25:
        raise ValueError("k must be between 1 and 25")
    if not cases or len(cases) > MAX_EVALUATION_CASES:
        raise ValueError(f"cases must contain between 1 and {MAX_EVALUATION_CASES} items")

    results: list[dict[str, object]] = []
    precision_values: list[float] = []
    recall_values: list[float] = []
    reciprocal_ranks: list[float] = []
    hits = 0

    for case in cases:
        if not case.query.strip() or not case.relevant_document_ids:
            raise ValueError("Each evaluation case needs a query and relevant document IDs")
        relevant = set(case.relevant_document_ids)
        retrieved = repository.search(owner_user_id, case.query, limit=k)
        retrieved_ids = [str(item["document_id"]) for item in retrieved]
        relevant_ranks = [
            rank for rank, document_id in enumerate(retrieved_ids, start=1)
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
        results.append({
            "query": case.query,
            "retrieved_document_ids": retrieved_ids,
            "relevant_found": relevant_found,
            "relevant_total": len(relevant),
            "precision_at_k": precision,
            "recall_at_k": recall,
            "reciprocal_rank": reciprocal_rank,
        })

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


def run_reference_evaluation() -> dict[str, object]:
    """Run a small synthetic benchmark in a temporary database; no user data is read."""
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
                "A worker lease and fencing token prevent stale workers from committing results "
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
        repository = KnowledgeRepository(Path(directory) / "evaluation.sqlite3")
        owner_id = "retrieval-evaluation-fixture-owner"
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
            RetrievalCase("DNS troubleshooting resolver", (document_ids["DNS Troubleshooting"],)),
            RetrievalCase("signed media URL HMAC", (document_ids["Signed Media Delivery"],)),
            RetrievalCase("worker lease fencing token", (document_ids["Worker Lease Safety"],)),
            RetrievalCase("Python AST analysis", (document_ids["Python AST Review"],)),
            RetrievalCase("SQLite backup restore checksum", (document_ids["SQLite Backup Restore"],)),
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
