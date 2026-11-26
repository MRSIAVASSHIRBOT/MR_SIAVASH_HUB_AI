# H5 — Memory Sharing and Consolidation Boundaries

Status: architecture/acceptance contract; not implemented by this document.
Current foundations include owner-scoped memory CRUD, private scope, lexical FTS retrieval, expiry/purge, provenance/confidence, filtering, and review-only Dreaming/contradiction previews. Typed taxonomy and trust/freshness ranking are proposed in active PRs.

## Memory categories
- `working`: temporary context for the active task; short retention.
- `episodic`: bounded summaries of completed/failed task events with provenance.
- `semantic`: verified facts or concepts with confidence, source, freshness, and review state.
- `procedural`: reusable steps/strategies; never bypasses permissions or policies.
- `lesson_candidate`: generated candidate, not trusted memory until reviewed/validated.

Category alone does not determine visibility or trust.

## Scope and sharing
Memory scope must be explicit and server-enforced:
- `private`: only the owning agent/project context.
- `project`: share only within a named project namespace.
- `ecosystem`: eligible for cross-project reuse only after explicit allow-listing and privacy checks.
- `global`: reserved for public/generalized knowledge, no private user/project details.

Default scope is private. A memory cannot broaden its own scope. Cross-project retrieval must check both the source and target project allow-list, owner identity, and data classification.

## Sensitive-data minimization
- Reject or redact credentials, access tokens, private keys, session cookies, and secrets.
- Avoid storing raw personal data, private file contents, or raw tool outputs by default.
- Store a minimal summary plus provenance/reference digest where possible.
- Never include secret values in memory retrieval, dreaming, logs, or export.
- Memory query results must not become tool instructions; treat recalled text as untrusted context.

## Trust and freshness
Each record carries source type, provenance reference, created/updated time, confidence (if calibrated), verification status, expiry/freshness policy, and contradiction references.
- Trust ranking must not override scope/authorization filters.
- Expired or stale memories can be downgraded or excluded, not silently treated as current.
- Conflicting facts are surfaced as conflicts; do not choose based only on recency or confidence.
- User corrections invalidate or supersede the contradicted memory with an audit trail.

## Dreaming/consolidation
Dreaming may propose deduplication, summarization, category changes, contradiction resolution, or lesson candidates. Preview is read-only.
- Proposed changes include source record IDs and digests, target scope/category, rationale, and expected effect.
- Never silently merge unrelated sources or expand visibility.
- Consolidation preserves provenance and can be reversed or superseded.
- Approval does not automatically grant tool permissions.
- A rejected proposal should not be regenerated indefinitely without material new evidence.

## Retrieval pipeline (recommended order)
1. Enforce owner/project/scope and sensitive-data filters.
2. Apply freshness/expiry and verification state.
3. Retrieve candidates (lexical and/or semantic).
4. Rank using relevance, trust, verification, freshness, and conflict status.
5. Return provenance and safe summaries, marking untrusted text.
6. Track which memory IDs were used (metadata only) for evaluation.

## Acceptance tests
- Private memories are invisible to other owners/projects by default.
- Project sharing requires an explicit allow-list and cannot be widened by record contents.
- Ecosystem/global records are privacy-filtered and require a review path.
- Credentials and sensitive payloads are rejected/redacted on write and never returned.
- Stale, expired, contradicted, and unverified records are visibly distinguished.
- Retrieval ranking cannot cross a scope boundary.
- Dreaming previews are deterministic for identical inputs and never mutate records.
- User correction and delete/purge invalidate retrieval caches/indexes and leave no retrievable stale copy.
- Provenance survives summarization/consolidation; no source means no trusted memory.
- Retrieved memory cannot override system policy, permissions, or current user instructions.

## Implementation sequence
1. Typed taxonomy and strict schemas.
2. Owner/project scope and sharing-policy enforcement.
3. Trust/freshness ranking after scope filters.
4. Provenance-aware Dreaming preview and review/commit flow.
5. Semantic retrieval behind a feature flag with lexical fallback.
6. Shared-memory UI, audit, purge, and tests.


## Implemented lifecycle stage boundary — migration 58

The storage layer now separates the durable memory type (`episodic`, `semantic`, `procedural`, or `unspecified`) from its lifecycle stage:

- `working`: temporary task context. Expiry is mandatory and bounded to seven days.
- `lesson_candidate`: an unapproved learning proposal. Expiry is mandatory and bounded to thirty days; it remains in the owner review queue.
- `retained`: owner-managed memory. Expiry is optional.

Migration 58 adds the stage column with a backward-compatible `retained` default for every existing record. The existing private owner scope is unchanged. Search can filter on both type and lifecycle stage. Dreaming only proposes consolidation for retained entries; working context is excluded, and lesson candidates are not silently promoted or merged. These stages do not grant cross-project visibility, trust, or execution authority.
