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


## Authenticated model-driven Agent run

`POST /agent/run` is the bounded synchronous entry point for the model-driven orchestration primitive. It assembles owner-scoped memory/knowledge evidence, passes the evidence JSON as untrusted data, and returns source references/freshness metadata separately from the answer.

Example request:

```json
{
  "goal": "Summarize the relevant evidence and cite its source references.",
  "provider_mode": "local",
  "include_memory": true,
  "include_knowledge": true,
  "max_turns": 3,
  "max_output_tokens": 512
}
```

- `provider_mode=local` requires an explicitly enabled local provider. `provider_mode=remote` requires an explicitly enabled remote provider. The endpoint does not use the stub provider or silently fall back between local and remote.
- The current tool catalog exposes only the deterministic `text.echo` tool; the model cannot add tools or grant itself permissions.
- The synchronous request is deliberately bounded: at most three model turns, with each provider request capped at 30 seconds (roughly 90 seconds of maximum provider wait, plus local processing overhead). It is an initial integration slice, not a replacement for durable worker-owned long-running workflows.
- The endpoint audits status/provider/turn/tool-count metadata, not the goal, retrieved text, or answer. It does not publish content or perform external side effects.
- Context sources remain untrusted. `owner_reviewed_current` is a manual owner assertion, not automatic source verification.


## Operator UI

The local dashboard exposes the bounded Agent endpoint with explicit local/remote provider mode, optional memory/knowledge context, a maximum of three turns, and a maximum of 512 output tokens. It displays the answer and source metadata separately, including freshness labels. Remote mode requires deliberate selection; the UI does not fall back between provider modes. The endpoint remains synchronous and is not a durable workflow runner.
