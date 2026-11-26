# Architecture Decision Index — G8

- **Baseline:** 2026-11-27
- **Owner:** HUB architecture / ecosystem owner
- **Scope:** HUB, EL_AI, EL_AGENT, MR_SIAVASH_AI and shared contracts
- **Authority:** [ADR-0051 — four-product ecosystem scope](decisions/ADR-0051-four-product-ecosystem-scope-and-telegram-ownership.md)

## 1. Purpose and rules

This index is the navigation and identifier registry for architecture decisions used by the four-product ecosystem. The exact file path is the canonical citation key; do not identify a decision by its number alone until the historical duplicate IDs have been resolved through a separately reviewed ADR-governance change.

Rules:
1. Accepted decisions are not silently rewritten. Material changes create a new ADR that explicitly supersedes the relevant decision.
2. Proposed decisions are not implementation or production authorization.
3. Every new ADR must use a unique ID reserved in this index before the file is created.
4. Cross-product decisions must record scope, owners, data-flow/security impact, migration/rollback, verification evidence and approval.
5. Duplicate historical IDs remain visible here; do not mass-rename historical files or change links without a dedicated compatibility plan.

## 2. HUB architecture and runtime decisions

| File / identifier | Title | Status observed | Scope / note |
|---|---|---|---|
| [adr-0041-unified-job-recovery.md](adr-0041-unified-job-recovery.md) | Unified Job Engine, Workflow Recovery, and Resume (ADR-004.1 in heading) | Accepted | Job/workflow lifecycle and recovery |
| [adr-0042-knowledge-memory.md](adr-0042-knowledge-memory.md) | Local-first Knowledge and Memory Architecture (ADR-0042) | Proposed | Knowledge/memory ownership and retrieval |
| [adr-0042-worker-owned-workflow-execution.md](adr-0042-worker-owned-workflow-execution.md) | Worker-Owned Agent Workflow Execution and Cancellation (ADR-0042) | Proposed implementation contract | **Identifier collision:** shares number 0042 with knowledge/memory ADR |
| [adr-0043-fenced-workflow-cancellation.md](adr-0043-fenced-workflow-cancellation.md) | Fenced Workflow Cancellation and Crash Recovery | Proposed in PR #7 | Durable cancellation and stale-worker fencing |
| [adr-0044-awi-plan-execution-bridge.md](adr-0044-awi-plan-execution-bridge.md) | Safe AWI Plan-to-Execution Bridge | Proposed design | Does not authorize execution by itself |
| [adr-0045-tool-lifecycle-trace-correlation.md](adr-0045-tool-lifecycle-trace-correlation.md) | Correlate tool lifecycle events with workflow attempts | Accepted | Tool lifecycle correlation |
| [adr-0046-workorder-evidence-evaluation.md](adr-0046-workorder-evidence-evaluation.md) | Digest-bound WorkOrder evidence evaluation | Accepted | H10; read-only semantic evidence contract |
| [decisions/ADR-0046-four-repository-scope-and-agent-bridge-boundary.md](decisions/ADR-0046-four-repository-scope-and-agent-bridge-boundary.md) | Four-repository scope and Agent/Bridge boundary | Accepted historically; **superseded for current portfolio scope** | **Identifier collision:** shares number 0046 with WorkOrder evidence ADR; its EL_IR_BOT scope is historical only |
| [decisions/ADR-0047-process-local-http-request-metrics.md](decisions/ADR-0047-process-local-http-request-metrics.md) | Bounded process-local HTTP request metrics | Accepted | H15; **retain ADR-0047 for this existing decision** |
| [decisions/ADR-0050-paios-product-boundaries-and-agent-runtime.md](decisions/ADR-0050-paios-product-boundaries-and-agent-runtime.md) | PAIOS product boundaries and replaceable agent runtime | Proposed (runtime architecture only) | Product-taxonomy/legacy-Bridge assumptions superseded by ADR-0051; remaining runtime proposal remains reviewable |
| [decisions/ADR-0051-four-product-ecosystem-scope-and-telegram-ownership.md](decisions/ADR-0051-four-product-ecosystem-scope-and-telegram-ownership.md) | Four-product ecosystem scope and Telegram ownership | Accepted by ecosystem owner; repository integration pending review | Current portfolio authority; supersedes conflicting product-scope assumptions in ADR-0046 and ADR-0050 |

## 3. Other HUB decisions

The following files exist under docs/architecture/decisions/; statuses should be read from each record because this index records path and topic rather than inferring acceptance from file presence.

| File | Topic |
|---|---|
| [0002-control-plane-services.md](decisions/0002-control-plane-services.md) | Control-plane services |
| [0004-versioned-schema-migrations.md](decisions/0004-versioned-schema-migrations.md) | Versioned schema migrations |
| [0005-local-inference-adapter.md](decisions/0005-local-inference-adapter.md) | Local inference adapter |
| [0007-telegram-client-pairing.md](decisions/0007-telegram-client-pairing.md) | Telegram client pairing |
| [0008-review-only-agent-proposals.md](decisions/0008-review-only-agent-proposals.md) | Review-only agent proposals |
| [0009-owner-scoped-agent-proposals.md](decisions/0009-owner-scoped-agent-proposals.md) | Owner-scoped agent proposals |
| [0010-read-only-agent-proposal-evaluation.md](decisions/0010-read-only-agent-proposal-evaluation.md) | Read-only proposal evaluation |
| [0011-personal-device-agent-control-plane.md](decisions/0011-personal-device-agent-control-plane.md) | Personal device-agent control plane |
| [ADR-0001-cloudflare-integration.md](decisions/ADR-0001-cloudflare-integration.md) | Cloudflare integration |
| [ADR-0002-cloudflare-workers-gateway.md](decisions/ADR-0002-cloudflare-workers-gateway.md) | Cloudflare Workers Gateway |
| [ADR-0006-central-project-control-center.md](decisions/ADR-0006-central-project-control-center.md) | Central project control center |

## 4. Website decisions

The public Website maintains its own product-local decision records in MR_SIAVASH_AI/docs/decisions/:

| File | Topic |
|---|---|
| 0001-cloudflare-backend-boundary.md | Cloudflare backend boundary |
| 0003-internal-principal-identity-mapping.md | Internal principal identity mapping |
| 0004-hub-integration-boundary.md | HUB integration boundary |

These records retain their repository-local IDs and are not renumbered into the HUB sequence. Any shared decision must point to both producer and consumer records.

## 5. Known identifier collisions and cleanup plan

The current repository history contains these collisions:
- **0042:** knowledge/memory architecture and worker-owned workflow execution.
- **0046:** WorkOrder evidence evaluation (architecture root) and four-repository scope/Agent-Bridge boundary (decisions subfolder).
- **0047:** bounded process-local request metrics is the pre-existing accepted decision. The new four-product portfolio decision is **ADR-0051**, not ADR-0047.
- adr-0041-unified-job-recovery.md uses ADR-004.1 in its heading rather than the filename's 0041 form.

This is a traceability defect, not evidence that either decision should be deleted. A future dedicated ADR-ID governance Work Order should:
1. Inventory inbound relative links, GitHub PR/issue references and external citations.
2. Decide a stable ID namespace and canonical index owner.
3. Add immutable aliases or redirect notes for duplicate historical identifiers.
4. Change links only in a separate reviewed PR with a complete reference audit.
5. Keep original files and historical decision meaning intact.

Until that Work Order is accepted, use the full relative path (or GitHub file URL) as the unique identifier.

## 6. New ADR reservation

- Highest newly assigned portfolio ADR: **ADR-0051**.
- Next available candidate for a new HUB-wide ADR: **ADR-0052**, subject to confirming no concurrent reservation before creation.
- Product-local ADR sequences remain local to their repositories.
