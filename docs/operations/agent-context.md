# Agent Context Assembly — First Integration Slice

The authenticated `POST /agent/context/assemble` endpoint combines the existing owner-scoped Memory API and source-backed Knowledge API for an explicit query. It uses local SQLite FTS5 only and does not invoke a model or execute tools.

## Request

```json
{
  "query": "SQLite FTS5 retrieval",
  "include_memory": true,
  "include_knowledge": true
}
```

Both source classes are enabled by default, but each can be disabled per request. The endpoint requires the owner's bearer session.

## Bounds and provenance

- Query: 1–200 characters.
- Up to 4 memory entries and 4 knowledge chunks.
- Memory passage content is capped at 600 characters; knowledge chunks at 1,400 characters.
- Combined passage content is capped at 6,000 characters.
- Knowledge passages retain stable `knowledge://documents/...` citation references, source references, trust classifications, and content hashes.
- Memory passages retain their memory reference, provenance, and verification status.
- Audit events record inclusion flags, retrieval method, and passage count only. Query text and retrieved content are not logged.
- Owner/scope filters remain enforced inside the source repositories before ranking.

## Trust boundary

All retrieved content is explicitly marked as untrusted evidence. Documents can contain prompt injection, misleading claims, or instructions; this endpoint does not treat them as authority. Retrieval cannot grant tool permissions, change policy, or authorize external side effects. Tool calls still require independent schema validation and policy evaluation.

## Current limitation — important

This is the context assembly contract and authenticated preview endpoint. The current `AgentCore` remains a deterministic planner/tool runner and does not yet send model-facing prompts, so this change does **not** claim that memory/knowledge is automatically injected into local or remote model inference. A subsequent integration must pass the structured evidence as a separate untrusted-data field to a real inference call and pass prompt-injection, citation-attribution, size-bound, and tool-boundary regression tests before enabling automatic injection.


## Source freshness signal

Knowledge passages now carry `freshness_status` and `freshness_checked_at`. The default is `unknown`; an owner can manually mark a source `owner_reviewed_current` or `stale` through the Knowledge API. The context marks this metadata as not automatically verified and keeps every passage untrusted regardless of freshness status. No URL fetch or external freshness probe occurs.
