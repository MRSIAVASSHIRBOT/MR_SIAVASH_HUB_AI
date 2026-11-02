# Source-Backed Local Knowledge API

The initial knowledge-document slice stores user-submitted Markdown/plain text locally, splits it into bounded chunks, and returns citation-bearing results from SQLite FTS5. It does not fetch URLs, crawl sites, install third-party code, or automatically inject retrieved text into agent prompts.

## Endpoints

All endpoints require the authenticated owner's bearer session.

- `POST /knowledge/documents` — ingest a text document with `title`, `content`, optional `source_ref`, `language`, and `trust_classification`.
- `GET /knowledge/documents?limit=50` — list owned document metadata.
- `GET /knowledge/documents/{document_id}` — read an owned document.
- `DELETE /knowledge/documents/{document_id}` — delete the source, document, chunks, and FTS rows.
- `POST /knowledge/search` — lexical search with up to 25 results and citation references.
- `GET /knowledge/export` — export all owned documents with their source references and content.

## Ingestion and provenance

- Input is limited to 100 KB of UTF-8 text per document.
- The service normalizes line endings, computes SHA-256 content hashes, and creates overlapping chunks with stable character offsets.
- Each document has a separate source record, owner, private scope, sensitivity classification, source reference, and trust classification.
- `source_ref` is a label/reference only. A URL-like value is never fetched or crawled.
- `user_reviewed` means the user marked the source reviewed; it is not an independent verification claim.
- Common credential/token patterns are rejected as a defense-in-depth heuristic. This is not a complete secret detector; do not ingest credentials, API keys, private keys, or authentication tokens.

## Retrieval and safety

- SQLite FTS5 provides local lexical search; terms are normalized before constructing the query to avoid accepting caller-supplied FTS operators.
- Owner and private-scope filters are applied in SQL before ranking. Shared scope is not enabled.
- Each result includes source/document IDs, a stable `knowledge://documents/{id}#chunk-{index}` citation reference, character offsets, chunk/document hashes, and trust metadata.
- Retrieved text is untrusted evidence. It cannot authorize tools, change policy, or approve actions.
- Search queries and document text are not copied into audit events; only operation names and minimal reason codes are recorded.
- Agent-context integration is intentionally disabled until the project adds a synthetic retrieval evaluation set, source-attribution checks, prompt-injection regressions, and context-size bounds.
- Export and deletion affect the live database, not older backup copies.

## Current limits

This slice supports text submitted through the authenticated API, not arbitrary local filesystem paths, automatic URL retrieval, PDF/OCR, vector search, cloud indexing, or automatic agent memory writes. Future ingestion formats must use explicit bounded adapters and preserve source provenance.


## Manual source freshness metadata

Every source starts with `freshness_status=unknown`. An authenticated owner can update `PATCH /knowledge/sources/{source_id}/freshness` with `owner_reviewed_current`, `stale`, or `unknown`. The service records the review time and owner identity for non-unknown states, and search results/context passages preserve that metadata.

This is an owner-declared review label, not automatic verification. Source URLs remain labels only: the application does not fetch them, crawl them, or independently verify that a document is current. Unknown or stale evidence must not be presented as freshly verified.


## Repeatable retrieval evaluation

A local synthetic benchmark is available through
`python -m mrhub.knowledge.evaluation`. It measures document-level Precision@k,
Recall@k, mean reciprocal rank, and hit rate using a temporary SQLite database.
The evaluator deduplicates chunk hits by document and bounds queries, case counts,
and relevance identifiers. It does not read production user data or claim that
synthetic fixture scores represent real retrieval quality. See
[knowledge-evaluation.md](knowledge-evaluation.md).
