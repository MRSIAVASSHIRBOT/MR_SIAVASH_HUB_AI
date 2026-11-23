# Typed Memory Classification

## Persistent memory types

Each persisted memory record has a `memory_type` separate from its free-form `category`:

- `episodic`: a dated event, interaction or task outcome.
- `semantic`: a reusable fact, concept or preference.
- `procedural`: a reusable method, workflow or instruction.
- `unspecified`: a legacy or not-yet-classified entry.

The type is owner-selected at create/update time. The system does not silently infer a persistent type from text. Existing records are migrated as `unspecified` so their original meaning is not guessed.

Working memory is deliberately not a persisted memory type in this migration. A dedicated bounded, ephemeral working-memory store and its lifecycle remain separate follow-up work.

## Retrieval and review

Owner-authenticated search can filter by one or more types. Owner and expiry predicates are always applied in SQL regardless of the requested type filter. Empty type filters return no results; invalid types are rejected by the API and repository boundary.

Context assembly carries `memory_type` into the model context while continuing to mark memory content as untrusted evidence. Dreaming/duplicate previews and contradiction review compare only records with the same category and memory type. Neither review engine changes records automatically.

## Migration

Schema migration 56 adds a constrained `memory_type` column and an owner/type/update index. The migration preserves content, provenance, verification state and existing FTS index entries. The column check permits only `unspecified`, `episodic`, `semantic` and `procedural`.

## Security and limitations

- Current memory remains private to its authenticated owner. No cross-project sharing or shared-memory ACL is introduced.
- Permission to read or modify memory is still enforced by the authenticated API and owner-scoped repository queries.
- Secret-pattern validation remains defense-in-depth; it cannot recognize every possible credential format.
- FTS5 remains lexical retrieval, not semantic-vector search. The type filter narrows candidates but does not prove factual validity.
- Dreaming and validation remain preview-only. No automatic consolidation, confidence promotion, conflict resolution or deletion is performed.
- Confidence, provenance, expiry and verification status remain separate from the memory type.
