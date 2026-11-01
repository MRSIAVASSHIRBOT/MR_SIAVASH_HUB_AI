# ADR-0042: Local-first Knowledge and Memory Architecture

- Status: Proposed
- Phase: 2 — AI Core and Memory
- Date: 2026-11-01
- Scope: single-user local runtime, SQLite-first storage

## Context

The product roadmap names Memory and Retrieval as a core domain, but the current implementation baseline is still centered on the control plane, jobs, authentication, policy, model routing, and diagnostics. Knowledge retrieval must be introduced without turning every stored record into unrestricted model context or confusing operational history with durable knowledge.

The system needs to distinguish three different data classes:

1. **Project knowledge** — source-backed technical documents, architecture decisions, approved notes, and reference material.
2. **User memory** — small, durable facts or preferences that are useful across tasks and have an explicit owner, scope, provenance, and retention policy.
3. **Operational history** — jobs, workflow states, audit events, and execution metadata. This is not a knowledge store and must not be silently promoted into memory.

## Decisions

### 1. Keep knowledge, memory, and execution history separate

Each data class has a separate repository and lifecycle. Retrieval may combine authorized results through a context service, but the underlying records retain their original owner, source, trust level, and retention rules.

Operational logs are not a substitute for memory. Raw prompts, credentials, tool arguments, and tool outputs must not be copied into durable memory by default.

### 2. Local-first SQLite and FTS5 before vector infrastructure

The first implementation uses SQLite with FTS5 for lexical retrieval. Do not add a vector database, embedding service, or external indexing dependency until an evaluation set demonstrates that lexical retrieval is insufficient and the target hardware can support the added cost.

The retrieval interface must remain provider-agnostic so a future vector index can be added behind the same contract without changing callers.

### 3. Provenance is mandatory

Every knowledge document must retain:
- stable source and document identifiers;
- source type and canonical origin (local file, user note, or connected provider);
- content hash and ingestion timestamp;
- title, language, and document version where available;
- trust classification and sensitivity classification;
- owner/scope and retention metadata;
- a source reference that can be shown to the user.

A result without usable provenance may be shown only as an explicitly unverified suggestion; it must not be presented as an authoritative fact.

### 4. Authorization and scope filtering happen before ranking

The retrieval service must apply owner, workspace, source, and sensitivity constraints before scoring or assembling context. Ranking must never be allowed to broaden access.

Initial scopes:
- **private**: visible only to its owner;
- **project**: visible only within the named project;
- **shared**: disabled until an explicit sharing and authorization model exists.

A missing or unknown scope fails closed.

### 5. Retrieved content is untrusted data

Documents, web pages, code comments, connector output, and user uploads may contain prompt injection or misleading instructions. Retrieved text is evidence, not authority. It cannot change system policy, grant tool permissions, approve an action, or override the active task.

Tool execution continues to require independent schema validation and policy evaluation. Retrieval must not create an implicit tool capability.

### 6. Memory writes are controlled

The first release supports explicit user-authored or user-approved memory writes. Automatic promotion of arbitrary conversation text into long-term memory is out of scope until provenance, sensitivity detection, correction, export, and deletion controls are tested.

Memory entries should be concise and structured with:
- category and scope;
- normalized value or statement;
- provenance;
- confidence or verification status;
- created/updated timestamps;
- optional expiry or review date.

Credentials, authentication secrets, payment data, and other secrets are never valid memory entries.

### 7. Privacy and lifecycle controls are part of the first slice

Before enabling broad ingestion, provide:
- list/read/update/delete for owned memory entries;
- export of a user's knowledge and memory records;
- retention and expiry behavior;
- deletion tests that verify removal from the primary store and FTS index;
- audit events that record the operation without copying the content itself.

Backups must be documented because deleting a live record does not automatically erase copies in older backups.

### 8. Retrieval returns evidence, not just text

The context service returns a typed result containing:
- the selected passage or summary;
- source/document reference;
- matching section or page where available;
- source trust and freshness indicators;
- retrieval method and score metadata suitable for debugging.

The model-facing context must preserve source references so user-facing answers can cite the documents used.

## Initial data model

The exact SQL schema is deferred to the implementation PR, but the logical entities are:

| Entity | Responsibility |
|---|---|
| knowledge_sources | Origin, owner, trust, version, hash, and lifecycle |
| knowledge_documents | Parsed document metadata and canonical content |
| knowledge_chunks | Bounded passages with stable source offsets |
| knowledge_chunks_fts | SQLite FTS5 lexical index |
| memory_entries | Small, owner-scoped durable facts/preferences |
| memory_provenance | Source and verification lineage |
| retrieval_events | Minimal diagnostics; no copied prompt or private content |

Every persistent schema change must use the versioned migration system. The migration must be forward-only, checksummed, and tested against both a fresh database and a representative legacy database.

## Retrieval pipeline

1. Authenticate the caller.
2. Resolve the active owner and project scope.
3. Validate query length and requested source filters.
4. Filter candidate sources by owner, scope, trust, sensitivity, and retention.
5. Retrieve lexical candidates using FTS5.
6. Rank using lexical relevance with bounded freshness/authority adjustments.
7. Deduplicate overlapping chunks and cap total context size.
8. Return passages with provenance and source references.
9. Record minimal retrieval diagnostics without storing the raw query or retrieved private content by default.

No fallback may silently query another user's data or an unapproved external provider.

## Evaluation and quality gates

Before enabling retrieval in agent execution, add a small version-controlled evaluation corpus with synthetic, non-sensitive examples. Measure:
- precision@k and recall@k for known questions;
- citation/source attribution correctness;
- freshness and stale-document behavior;
- owner/scope isolation;
- deletion from both canonical storage and FTS index;
- prompt-injection resistance at the context/tool boundary;
- bounded query time and context size on the target workstation.

A retrieval result is not considered correct merely because it returns plausible text; it must return the right source and preserve the access boundary.

## Implementation sequence

1. Add the versioned schema and repository contracts.
2. Implement owner-scoped CRUD and export/delete tests for memory entries.
3. Implement local Markdown/plain-text ingestion with file-size and parser limits.
4. Add FTS5 indexing, source offsets, and index consistency tests.
5. Add the retrieval service and citation-bearing API response.
6. Add evaluation fixtures, isolation tests, and prompt-injection regression tests.
7. Integrate retrieval into the agent context manager only after the standalone API passes its quality gates.
8. Re-evaluate vector search only after measured lexical-retrieval limitations.

## Non-goals for the first release

- A hosted vector database.
- Automatic web crawling or unrestricted connector ingestion.
- Hidden user profiling or unreviewable memory writes.
- Cross-user or public memory sharing.
- Storing credentials or raw tool execution payloads.
- Letting retrieved text approve or authorize external actions.

## Review triggers

Revisit this ADR when multi-user workspaces are introduced, a new connector can ingest private data, cloud retrieval is proposed, embeddings are benchmarked, or the retention/export model changes.
