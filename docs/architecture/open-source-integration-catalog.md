# Open-source integration catalog

MR_SIAVASH_HUB_AI is independent from the owner's previous repositories. Third-party projects are evaluated behind Hub-owned interfaces.

## Candidates

- Headroom: https://github.com/headroomlabs-ai/headroom — Apache-2.0; Python >=3.11; optional prototype only after dependency review.
- PixelRAG: https://github.com/StarTrail-org/PixelRAG — Apache-2.0; Python >=3.12; visual retrieval with substantial optional ML dependencies; keep separate from the Python >=3.11 core.
- Cloudflare Security Audit Skill: https://github.com/cloudflare/security-audit-skill — MIT; agent skill rather than a Python library; methodology only, no automatic command execution.
- MCP Python SDK: https://github.com/modelcontextprotocol/python-sdk — MIT; Python >=3.11; candidate optional integration with explicit server allowlists and per-tool permissions.

## Not approved yet

- GLM: verify official upstream, license, API contract, and dependencies before selecting an adapter.
- Sandbox: select only after reviewing isolation boundaries, permissions, and resource limits; a container alone is not sufficient.
- Text RAG: evaluate separately; PixelRAG is visually oriented.

## Adoption gate

For every upstream, record the canonical URL and revision, license obligations, runtime compatibility, dependencies, data/network/filesystem behavior, Hub interface, tests, feature flag, and rollback plan. Discovery is not approval. Do not install or execute discovered projects automatically. Optional integrations must not silently enable paid services or send private data to third parties.

## Order

1. Prototype MCP behind a disabled optional feature and allowlist.
2. Benchmark Headroom behind the context interface.
3. Keep PixelRAG separate until Python-version compatibility is resolved.
4. Adapt Cloudflare's audit methodology into a reviewed workflow.
5. Select GLM and a sandbox after upstream review.

These are candidates, not completed runtime integrations.


## Local candidate catalog

The first capability-catalog slice is available through the authenticated API:

- `POST /capabilities/candidates` registers a canonical HTTPS source URL and declared capabilities.
- `GET /capabilities/candidates` lists candidates; filter with `?status=discovered`, `reviewing`, `approved`, `rejected`, or `disabled`.
- `GET /capabilities/candidates/{candidate_id}` retrieves one candidate.
- `POST /capabilities/candidates/{candidate_id}/transition` advances review status.

Registration is metadata-only: it does not fetch, install, import, or execute upstream code. Duplicate canonical URLs are rejected. Approval is blocked unless a known license identifier, public HTTPS license URL, security review, compatibility notes, and a test plan are recorded. This catalog is a first building block, not yet an automated GitHub scanner, package installer, plugin runtime, or self-modifying code system.
