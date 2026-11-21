# MR_SIAVASH_ENGINEERING_HQ — Decision Log

This log records cross-repository decisions. Repository-local architecture decisions remain in their owning repository and should be linked here when they affect another project.

## Accepted decisions

### HQ-DEC-001 — HUB is the active development project

- **Status:** Accepted
- **Date:** 2026-11-21
- **Decision:** MR_SIAVASH_HUB_AI is the single primary development repository.
- **Rationale:** It owns the shared intelligence core, private memory, agent orchestration, policy, jobs, tools and core integration contracts.
- **Consequences:** Website and EL_AI remain independently maintained companions. Do not start competing feature programs in all three repositories.

### HQ-DEC-002 — Gshop is outside this workspace scope

- **Status:** Accepted
- **Date:** 2026-11-21
- **Decision:** Do not inspect for implementation, modify, deploy, or otherwise operate Gshop as part of MR_SIAVASH_ENGINEERING_HQ.
- **Rationale:** Explicit owner scope boundary.
- **Consequences:** Existing documents may contain historical Gshop references. They do not authorize action. Keep Gshop out of task assignment, integration execution and release planning.

### HQ-DEC-003 — Hybrid source-of-truth model

- **Status:** Accepted
- **Date:** 2026-11-21
- **Decision:** GitHub is authoritative for technical state and evidence; the existing SPC Control Center in Notion is the human-facing portfolio dashboard.
- **Rationale:** Code, commits, PRs, issues and CI need versioned, auditable evidence. Notion is useful for navigation and management views.
- **Consequences:** Do not create a second Notion control center. Mirror summaries and links only when Notion write access is available. The current Notion connection exposes search/fetch, not page creation/update.

### HQ-DEC-004 — Independent repository ownership and versioning

- **Status:** Accepted
- **Date:** 2026-11-21
- **Decision:** The three repositories keep independent source histories, CI pipelines, release gates and runtime ownership.
- **Rationale:** Avoid unnecessary coupling and accidental shared failure domains.
- **Consequences:** Integration occurs through explicit, versioned API contracts, not shared source directories or direct database access.

### HQ-DEC-005 — Private control plane belongs to HUB

- **Status:** Accepted
- **Date:** 2026-11-21
- **Decision:** HUB owns owner identity, private memory, tool grants, policy, approvals, audit records and durable job state.
- **Rationale:** These capabilities form the trusted control plane.
- **Consequences:** EL_AI is a scoped client; Website/Gateway receives public-only projections and must never receive private Hub context.

### HQ-DEC-006 — Reviewable, exact-head delivery

- **Status:** Accepted
- **Date:** 2026-11-21
- **Decision:** Use dedicated branches and focused PRs. A check is PASS only when it completed successfully on the exact SHA under review.
- **Rationale:** Prevent stale checks and undocumented changes from satisfying release gates.
- **Consequences:** No direct-to-main implementation. Do not merge when required checks are pending, failed, skipped or from another SHA.

### HQ-DEC-007 — Explicit approval for consequential operations

- **Status:** Accepted
- **Date:** 2026-11-21
- **Decision:** Routine reversible engineering work may proceed under the owner's standing authorization. Production deployment, credentials, access policy, DNS, billing, public publishing, destructive data/branch operations and other consequential changes require separate explicit approval.
- **Rationale:** Preserve initiative without weakening owner control.
- **Consequences:** Staging plans must be isolated and reviewed; no secret values are placed in source, Issues or chat.

## Existing repository decisions to preserve

- HUB [ADR-0006 — Central Project Control Center](../../architecture/decisions/ADR-0006-central-project-control-center.md) is accepted and specifies extension of the existing authenticated operator UI rather than creating a duplicate dashboard. Its project registry historically mentions Gshop; HQ-DEC-002 excludes Gshop from this workspace's execution scope.
- HUB [ADR-0042 — Knowledge and Memory](../../architecture/adr-0042-knowledge-memory.md) defines the local-first memory boundary.
- HUB [ADR-0043 — Fenced Workflow Cancellation](../../architecture/adr-0043-fenced-workflow-cancellation.md) defines cancellation fencing.
- EL_AI [ADR-0002 — Hub Pairing Contract](https://github.com/MRSIAVASSHIRBOT/MR_SIAVASH_EL_AI/blob/main/docs/architecture/adr/0002-hub-pairing-contract.md) defines the scoped pairing boundary.
- Website [Decision 0004 — Hub Integration Boundary](https://github.com/MRSIAVASSHIRBOT/MR_SIAVASH_AI/blob/main/docs/decisions/0004-hub-integration-boundary.md) preserves independent deployment and public/private separation.

## Proposed decisions — not accepted

No new cross-repository architectural proposal is accepted by this document. Any proposal must be reviewed and assigned a new HQ-DEC identifier before it is treated as binding.

## Change record

| Date | Change |
| --- | --- |
| 2026-11-21 | Initial HQ decision log created from explicit owner scope and the current repository/Notion audit. |
