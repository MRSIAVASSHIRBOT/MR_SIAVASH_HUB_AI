# Repeatable Knowledge Retrieval Evaluation

Run the synthetic benchmark from the installed project environment:

```powershell
python -m mrhub.knowledge.evaluation
```

The command creates a temporary SQLite database, indexes five synthetic documents, evaluates five known queries, prints Precision@k, Recall@k, mean reciprocal rank (MRR), and hit rate, then removes the temporary database. It does not read the user's knowledge base, contact the network, or return source text.

## Interpretation

- `precision_at_k`: fraction of the top-k returned documents that are labeled relevant, averaged across cases.
- `recall_at_k`: fraction of labeled relevant documents found in the top-k, averaged across cases.
- `mean_reciprocal_rank`: average reciprocal rank of the first relevant result.
- `hit_rate`: fraction of queries with at least one relevant result in the top-k.

This fixture benchmark verifies that the evaluation harness is repeatable and wired to SQLite FTS5. It is **not** evidence that retrieval quality on real user documents is good. A production-quality evaluation requires a reviewed, representative query/relevance dataset with privacy controls, plus measured results before considering embeddings or vector retrieval. Owner-declared source freshness remains distinct from automatic source verification.
