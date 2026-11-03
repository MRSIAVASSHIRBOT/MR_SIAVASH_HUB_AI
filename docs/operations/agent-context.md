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
- Up to 4 memory entries and 4 knowledge chunks before budget enforcement.
- Memory passage content is capped at 600 characters; knowledge chunks at 1,400 characters.
- The **complete serialized model-facing evidence block**, including its trust-boundary prefix, JSON syntax, metadata, and escaped content, is capped at 6,000 characters. Oversized final passages are deterministically truncated; a passage that cannot fit with its metadata is omitted.
- The response exposes `context_char_count` so callers and tests can verify the actual serialized size.
- Knowledge passages retain stable `knowledge://documents/...` citation references, source references, trust classifications, and content hashes.
- Memory passages retain their memory reference, provenance, and verification status.
- Audit events record inclusion flags, retrieval method, and passage count only. Query text and retrieved content are not logged.
- Owner/scope filters remain enforced inside the source repositories before ranking.

## Trust boundary

All retrieved content is explicitly marked as untrusted evidence. Documents can contain prompt injection, misleading claims, or instructions; this endpoint does not treat them as authority. Retrieval cannot grant tool permissions, change policy, or authorize external side effects. Tool calls still require independent schema validation and policy evaluation.

## Current limitation — important

The standalone `POST /agent/context/assemble` endpoint is a retrieval preview and does not invoke a model. The separate `AgentCore` remains a deterministic planner/tool runner. The bounded model-driven path is `POST /agent/run`, documented below; it explicitly passes the assembled evidence as untrusted model input and retains independent server-side tool validation and policy checks. This synchronous path is not a durable worker-owned execution workflow.

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


## Model-driven Agent run history

The authenticated model-run history is available without persisting prompts, retrieved passage bodies, answers, tool inputs, or tool outputs.

- `GET /agent/model-runs?limit=20` lists the most recent runs for the current owner. The limit is bounded to 1–100.
- `GET /agent/model-runs/{run_id}` retrieves one run belonging to the current owner; another owner's run is indistinguishable from a missing run (404).
- Records contain the run identifier, outcome, timestamp, provider mode, terminal status, selected provider, turn count, tool-call count, and retrieved-passage count.
- The history is backed by the existing audit-event store; no schema migration or duplicate history table is introduced.
- The audit metadata allow-list explicitly permits only these operational fields. Arbitrary request fields, prompts, evidence, answers, credentials, and tool payloads remain excluded.


## Knowledge freshness filtering

Both `POST /agent/context/assemble` and `POST /agent/run` accept
`knowledge_freshness_policy`:

- `include_all` (default) preserves the existing behavior and labels each passage.
- `owner_reviewed_current_only` includes only knowledge sources whose freshness status
  is `owner_reviewed_current` and whose review timestamp is present. The filtered mode
  inspects up to 25 ranked chunk candidates before selecting at most 4 eligible passages,
  so stale top-ranked chunks do not automatically hide a later reviewed candidate. Stale,
  unknown, and incomplete review records are excluded before context budgeting.

The response reports `excluded_stale_knowledge_count` and
`excluded_unreviewed_knowledge_count`. This policy relies on the owner's manual review
assertion; it does **not** perform automatic URL checks or prove that a source is current.
Memory evidence is unaffected by this knowledge-only filter. Retrieved content remains
untrusted and cannot grant tool permissions.

The operator UI exposes the same policy selector in its bounded Agent run panel and
shows the number of stale and unreviewed knowledge passages excluded from each run.
