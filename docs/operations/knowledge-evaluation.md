# Repeatable Knowledge Retrieval Evaluation

Run the synthetic benchmark from the installed project environment:

```powershell
python -m mrhub.knowledge.evaluation
```

The command creates a temporary SQLite database, indexes five synthetic documents,
evaluates five known queries, prints Precision@k, Recall@k, mean reciprocal rank (MRR),
and hit rate, then removes the temporary database. It does not read the user's
knowledge base, contact the network, or return source text.

## Interpretation

- `precision_at_k`: relevant unique documents in the top-k divided by k.
- `recall_at_k`: relevant unique documents found in the top-k divided by the number
  of labeled relevant documents.
- `mean_reciprocal_rank`: average reciprocal rank of the first relevant document.
- `hit_rate`: fraction of queries with at least one relevant document in the top-k.

The knowledge search API ranks chunks. The evaluator collapses chunk hits into unique
documents while preserving first-seen rank. It examines at most 25 chunk hits per query,
matching the repository search bound; a document with many matching chunks can therefore
reduce the number of distinct documents available to the evaluator.

## Input and privacy bounds

- At most 100 evaluation cases.
- Each query is limited to 200 characters.
- At most 100 relevant document IDs per case and 1,000 across the complete evaluation.
- Document identifiers are limited to 64 characters and duplicates are rejected.
- The report contains query strings and document IDs, but never retrieved source text.
- The benchmark uses a temporary database and synthetic fixtures only; it never reads
  a user's production database or performs network access.

## Interpretation limits

This fixture benchmark verifies that the evaluation harness is repeatable and wired to
SQLite FTS5. It is **not** evidence that retrieval quality on real user documents is good.
A production-quality evaluation requires a reviewed, representative query/relevance
dataset with privacy controls and measured results. Owner-declared source freshness
remains distinct from automatic source verification.
