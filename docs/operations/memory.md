# Local Memory API — Initial Slice

The first memory release is a local SQLite feature for explicit, owner-authored notes. It is deliberately separate from workflow history and is not automatically injected into agent prompts.

## API

All endpoints require the local owner's bearer session.

- `POST /memory` — create a private entry. Required: `category`, `content`. Optional: `provenance`, `confidence`, `verification_status`, `expires_at`.
- `GET /memory?limit=50` — list active entries for the authenticated owner (maximum 100).
- `GET /memory/{memory_id}` — read one active owned entry.
- `PATCH /memory/{memory_id}` — update fields; send `{"expires_at": null}` to clear expiry.
- `DELETE /memory/{memory_id}` — delete one owned entry.
- `POST /memory/search` — lexical SQLite FTS5 search, with a query up to 200 characters and at most 25 results.
- `GET /memory/export` — export all owned entries, including expired entries, as JSON.
- `DELETE /memory/expired` — permanently delete expired entries owned by the caller.

## Security and data handling

- Every record has a foreign-key owner and the only enabled scope is `private`; unknown or shared scopes are not accepted.
- Owner filtering is part of the SQL query, before ranking. Record identifiers do not grant access to another owner's entry.
- The FTS5 index is maintained transactionally by SQLite triggers on insert, update, and delete.
- Expired entries are excluded from list, read, and search. They remain available in the owner's export until explicitly purged.
- Create/update audit events include operation metadata only; memory text and search queries are not copied into audit logs.
- The API rejects several common credential/token patterns. This is a defense-in-depth heuristic, not a complete secret detector: never submit credentials, API keys, private keys, or authentication tokens as memory content.
- Retrieved text is untrusted evidence, not instructions or authorization. The initial slice does not connect memory search to model context or tool execution.
- Exporting or deleting a live record does not erase older copies in backups. Backup retention must be managed separately.

## Current limits

This is the memory-entry slice only. Markdown/plain-text document ingestion, source/chunk records, citation-aware context assembly, evaluation corpus, and retrieval integration into the agent remain separate milestones. SQLite FTS5 availability is required; no vector database, embedding API, cloud fallback, or external indexing service is used.


## Dreaming preview — first safe implementation

`POST /memory/dream/preview` runs a deterministic, owner-scoped review over at most 100 active memory entries. It proposes possible duplicates only when entries share a category and their normalized token Jaccard similarity meets the configured threshold (default 0.82; allowed range 0.75–1.0).

The endpoint is read-only with respect to memory content. It returns candidate IDs, short excerpts, heuristic similarity, and an explicit owner-review requirement. It does not merge, rewrite, downgrade, or delete entries. The audit event records counts only, never memory content.

This is intentionally a first consolidation primitive, not a complete LLM-based Dreaming system: it does not inspect raw session transcripts, infer contradictions, establish factual correctness, or autonomously promote knowledge. Those capabilities require a separately evaluated proposal/approval workflow and explicit source provenance.

### Example

```json
{
  "limit": 100,
  "similarity_threshold": 0.82
}
```

The response includes `state_changed: false` and a limitations list. Treat every proposal as a review hint, not a verified duplicate.
