# MR_SIAVASH_ENGINEERING_HQ — Master Status

**Snapshot date:** 2026-11-21 UTC  
**Status owner:** Engineering Coordinator  
**Authority:** GitHub repository heads, pull requests, issues, and exact-head Actions observations  
**Scope:** MR_SIAVASH_HUB_AI, MR_SIAVASH_AI, MR_SIAVASH_EL_AI only. Gshop is explicitly out of scope.

This is a dated evidence snapshot, not a live status endpoint. Refresh it before making merge, release, deployment, or architecture decisions.

## Executive status

- **Active development:** MR_SIAVASH_HUB_AI.
- **Companion website:** MR_SIAVASH_AI; maintain independently and integrate only through versioned public contracts.
- **Telegram companion:** MR_SIAVASH_EL_AI; source and CI are healthy, but live Telegram acceptance is not verified.
- **No production deployment or external runtime is considered healthy solely because repository CI passed.**
- **No repository main branch is protected** according to the branch metadata observed in this audit.
- No code, infrastructure, secret, DNS, billing, production data, or access-control setting was changed during the audit.

## Repository baseline

| Repository | Default branch / HEAD | Branches | Open PRs | Open issues | Latest main CI evidence |
| --- | --- | ---: | ---: | ---: | --- |
| [MR_SIAVASH_HUB_AI](https://github.com/MRSIAVASSHIRBOT/MR_SIAVASH_HUB_AI) | main / `fd3d8b319592fec207912f446234c359e0352fd9` | 372 | 2 | 5 | 7 workflows passed on exact HEAD |
| [MR_SIAVASH_AI](https://github.com/MRSIAVASSHIRBOT/MR_SIAVASH_AI) | main / `a2428f5208a78e3d8f1181f55af1427448b55483` | 244 | 0 | 2 | 6 workflows passed on exact HEAD |
| [MR_SIAVASH_EL_AI](https://github.com/MRSIAVASSHIRBOT/MR_SIAVASH_EL_AI) | main / `90aa638fff2f515e193e754fa73bad4b79e14e36` | 79 | 1 | 1 | CI, security audit, Scorecard passed on exact HEAD |

Branch counts were obtained by exhausting paginated branch listings (100 per page). They describe remote branch refs, not necessarily active work. No branch was deleted. All three repositories use `main` as the default branch and GitHub reported `protected=false`.

### MR_SIAVASH_HUB_AI

Recent mainline changes include:
- owner-authorized personal device tools and device pairing/task controls;
- bounded Telegram AI task-plan preview;
- remote model-provider registry correction;
- device refresh-token reuse detection and bounded pairing challenges;
- private-media download integrity verification and stable descriptor snapshots;
- current ecosystem status documentation.

Open pull requests:
- [#472 — current device consumer and Pages checkpoints](https://github.com/MRSIAVASSHIRBOT/MR_SIAVASH_HUB_AI/pull/472), documentation-only. Latest observed head: `b6e6974edc000091f37eac0a2988dd076f1114ce`. Security audit and defensive scan passed; CI, Backend CI, and Video Render Integration were still running at the last exact-head read.
- [#473 — device credential and task-lease timing hardening](https://github.com/MRSIAVASSHIRBOT/MR_SIAVASH_HUB_AI/pull/473). Latest observed head: `1eb1b95f79c7f200dfd9a9ac5acbb6d3cd6fba3c`. Workflow Security Audit and Defensive Python Scan passed; CI, Backend CI, Video Render Integration, and Windows Launcher Validation were still running at the last exact-head read.

Open issues:
- [#200](https://github.com/MRSIAVASSHIRBOT/MR_SIAVASH_HUB_AI/issues/200) — recovery, integration, dependency, and release audit. Its historical snapshot references superseded PRs and old main SHAs; reconcile it against this baseline.
- [#182](https://github.com/MRSIAVASSHIRBOT/MR_SIAVASH_HUB_AI/issues/182) — durable video-generation lifecycle. A provider-neutral contract and durable job flow have already been merged; remaining acceptance must be checked against current source and configured provider state.
- [#304](https://github.com/MRSIAVASSHIRBOT/MR_SIAVASH_HUB_AI/issues/304) — protect main and require exact-head CI.
- [#305](https://github.com/MRSIAVASSHIRBOT/MR_SIAVASH_HUB_AI/issues/305) — isolated Hub Cloudflare staging and read-only acceptance.
- [#298](https://github.com/MRSIAVASSHIRBOT/MR_SIAVASH_HUB_AI/issues/298) — payment credential/CORS hardening references resources outside this workspace scope; do not act on it here.

Latest main-head Actions on `fd3d8b3`: Workflow Security Audit, OpenSSF Scorecard, Defensive Python Scan, Video Render Integration, Backend CI, Windows Launcher Validation, and CI all completed successfully.

### MR_SIAVASH_AI

Recent mainline changes include the Dark Emerald identity/privacy experience, Persian public learning website rebuild, CSS cleanup, and dated release-evidence clarification.

- No open PRs at the audit snapshot.
- PR #247 is merged; its documentation update is represented by current main commit `a2428f5`.
- Open [#70](https://github.com/MRSIAVASSHIRBOT/MR_SIAVASH_AI/issues/70): main branch protection.
- Open [#120](https://github.com/MRSIAVASSHIRBOT/MR_SIAVASH_AI/issues/120): reconcile current source with active Production Gateway version and release evidence.
- Six exact-main workflows passed on `a2428f5`: Gateway CI, Workflow Security Audit, Quality/Pages, OpenSSF Scorecard, Cloudflare Gateway Preview Runtime Smoke, and Cloudflare Gateway Runtime Smoke.
- GitHub Pages publication has a successful exact-main workflow. This does not prove that current Gateway source is deployed to Cloudflare Production or Preview.
- No fresh Cloudflare control-plane readback was performed as part of this repository audit.

### MR_SIAVASH_EL_AI

Recent mainline changes include dependency-aware task-plan progression, Website source/Pages evidence refresh, and safe bounded Telegram task-plan execution.

- Open [#78](https://github.com/MRSIAVASSHIRBOT/MR_SIAVASH_EL_AI/pull/78): explicitly disable redirects in the authenticated Hub HTTP client and test that bearer credentials do not follow a redirect. Exact-head Python 3.11/3.12 CI and Workflow Security Audit passed on `d093069a073f6e46274b38ea8f3f34622b20830c`.
- Open [#5](https://github.com/MRSIAVASSHIRBOT/MR_SIAVASH_EL_AI/issues/5): main branch protection.
- Exact-main CI, Workflow Security Audit, and OpenSSF Scorecard passed on `90aa638`.
- No Telegram token, live bot connection, webhook registration, real owner pairing, or production bot deployment is verified.
- Hub integration remains opt-in and public/private context separation remains mandatory.

## Cross-repository integration status

| Flow | Owner | Current contract/state | Acceptance still required |
| --- | --- | --- | --- |
| EL_AI → HUB | HUB owns identity, pairing, scopes, policy, tasks and private memory; EL_AI is a scoped client | Pairing/client API and bounded task plans exist in source | PR #78 exact-head review; live local pairing with owner-managed secrets; scope/revocation tests |
| EL_AI → Website Gateway | EL_AI public client; Website owns public Gateway | Public-only request contract exists; private Hub context must never be forwarded | Live configured Gateway response and public/owner isolation evaluation |
| Website → HUB public status | HUB publishes a bounded public projection; Website consumes its schema | Public status schema and generator exist in Website source | Schema compatibility and publication freshness checks |
| HUB → external tools/providers | HUB owns model/tool policy and execution | Explicit provider selection, grants, bounded jobs and approval gates | Provider-specific integration and operational acceptance |
| HUB ↔ device companion | Separate companion repository appears in Hub records | Not part of this three-repository audit | Inspect separately before scheduling work |

No direct cross-repository database access is permitted. Use versioned API contracts, scoped credentials, correlation IDs, idempotency keys, bounded retries, and sanitized errors.

## Tool and permission findings

- GitHub connector: authenticated repository reads and writes are available. Repository metadata reports admin/maintain/push permissions on all three audited repositories. Available actions include branch creation, file creation/update, PR creation, PR review/comment, issue updates, and merge operations.
- GitHub branch-protection administration: not available through the current connector surface. The branch-protection read endpoint returned 403 for this connection; branch metadata independently reported `protected=false`. No policy mutation was attempted.
- GitHub Actions: workflow/run/check metadata and job logs are available through read actions.
- Notion: search and fetch are available. The existing SPC Control Center and SPC Documents records were found. Page creation/update tools are not exposed as available in the current Notion access map; no Notion writes were attempted.
- Cloudflare connector: tools for identity, search, documentation and execution are exposed, but no fresh account/runtime read was performed in this audit. Production mutations remain approval-gated.
- Local repository checkout, working tree inspection, local test execution, and physical-device access were not available through this GitHub connection.

## Governance

1. GitHub source and CI evidence are authoritative for code state.
2. Notion SPC Control Center is the management dashboard; do not create a duplicate control center.
3. One active development repository at a time: HUB.
4. Companion repositories remain independently versioned and deployed.
5. No direct commits to `main`; use dedicated branches and reviewable PRs.
6. Do not delete branches or close PRs merely to reduce inventory.
7. Do not merge without exact-head checks and appropriate review.
8. Production, credentials, access control, DNS, billing, public publishing and persistent data changes require separate explicit approval.
9. Gshop is excluded from all engineering execution in this workspace.

## Refresh procedure

Before any implementation, merge, or release decision:
- re-read default branch heads and changed files;
- re-read all open PRs, issue bodies, review threads, and exact-head check runs;
- verify branch pagination and branch protection metadata;
- compare relevant source contracts and migration state;
- update this snapshot with timestamp, SHA, evidence links, and unresolved limitations.
