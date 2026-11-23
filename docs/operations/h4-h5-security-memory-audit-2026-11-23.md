# H4/H5 Security and Memory Audit — 2026-11-23

Baseline: `main` at `d15c45e4f72a2928e97476944ee7a5a83a3a2d54`.
Source inspection only; no local test suite execution.

## H4 — Permission and Security Engine

### Verified components
- `security/auth.py`: local owner bootstrap, password hashing with scrypt, opaque session tokens, token hashing at rest, expiration and revocation.
- `security/policy.py`: explicit `ALLOW / REQUIRE_APPROVAL / DENY`; missing permission grants deny; prohibited risk deny; high-risk and external side effects require approval; unknown task types are server-classified as high risk.
- `security/tool_permissions.py`: narrow permission allow-list, owner-scoped grants, expiry bounds (60 seconds to 24 hours), audit records and revocation.
- `tools/registry.py`: explicit registered tools, validated names and schemas, policy checks, typed output validation, and exception sanitization.
- `security/audit.py`: metadata allow-list to avoid arbitrary prompts/credentials in audit events.
- API route protections: auth dependencies are present on policy and memory routers.

### Security tests observed in source
- Auth setup/login/logout, invalid credentials, protected endpoints.
- High-risk and unknown task approval gates; client-supplied approval ignored by policy API.
- Permission grants are owner-scoped, expire, revoke and audit.
- Audit metadata rejects/drop sensitive keys and prompt content.
- GPI prompt injection and untrusted input regression coverage exists in `tests/test_gpi_security_regressions.py` (file retrieval unavailable in this pass).

### Remaining H4 gates (not phase-complete)
- End-to-end role model and separation of roles from capability grants need a formal contract; currently the grant model is a single-owner, explicit permission allow-list.
- Input/output validation is implemented at several layers; systematic tool output trust-boundary tests and cross-tool injection cases need full test execution and audit.
- Rate limiting and execution resource budgets require end-to-end coverage; not proven by these inspected modules.
- Secrets management beyond the narrow credential detector and deployment configuration review remains.
- Security test suite and CI results must be verified on exact current commit.

## H5 — Memory System

### Verified components
- `memory/repository.py`: owner-scoped persistence, FTS5 lexical retrieval, credential pattern checks, expiry handling and memory provenance/metadata.
- `memory/validation.py`: bounded read-only review for expiry, verification and possible contradictions.
- `memory/dreaming.py`: deterministic duplicate review proposals; no automatic merge/delete/rewrite.
- `api/routes/memory.py`: authenticated memory CRUD/search/export routes and bounded input validation.

### Tests observed in source
- Memory CRUD/search/update/delete and FTS index consistency.
- Owner-scoped memory and audit behavior.
- Secret-pattern rejection.
- Expiry and validation handling.
- Contradiction review (including Persian negation) without mutation.
- Dreaming duplicate suggestions require owner review and do not mutate state.

### Remaining H5 gates (not phase-complete)
- Working/episodic/semantic/procedural memory types are not established as a complete typed architecture in the inspected repository.
- Cross-project shared memory with granular project/agent ACL and selective sharing is not verified; repository is owner-scoped private memory.
- Retrieval ranking is lexical FTS5; recency, confidence, provenance-aware relevance and stale-source weighting need further work/acceptance tests.
- Consolidation remains conservative duplicate/contradiction preview, not automated learning or knowledge revision.
- Full memory privacy, deletion/retention, migration and isolation tests must run.

## Disposition
**H4: partial. H5: partial.** These audits identify existing security and memory foundations, but do not certify either phase as complete. Next priority is test-backed gap closure and contracts, not broad rewrites.
