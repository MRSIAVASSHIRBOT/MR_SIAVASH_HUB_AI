# MR_SIAVASH_ENGINEERING_HQ — Master Status

**Snapshot date:** 2026-11-21 UTC  
**Status owner:** Engineering Coordinator  
**Authority:** GitHub repository heads, pull requests, issues, and exact-head Actions observations  
**Scope:** MR_SIAVASH_HUB_AI, MR_SIAVASH_AI, MR_SIAVASH_EL_AI, and MR_SIAVASH_EL_AGENT. Gshop is explicitly out of scope.

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
| [MR_SIAVASH_HUB_AI](https://github.com/MRSIAVASSHIRBOT/MR_SIAVASH_HUB_AI) | main / `fd3d8b319592fec207912f446234c359e0352fd9` | 472 | 2 | 5 | 7 workflows passed on exact HEAD |
| [MR_SIAVASH_AI](https://github.com/MRSIAVASSHIRBOT/MR_SIAVASH_AI) | main / `a2428f5208a78e3d8f1181f55af1427448b55483` | 244 | 0 | 2 | 6 workflows passed on exact HEAD |
| [MR_SIAVASH_EL_AI](https://github.com/MRSIAVASSHIRBOT/MR_SIAVASH_EL_AI) | main / `90aa638fff2f515e193e754fa73bad4b79e14e36` | 79 | 1 | 1 | CI, security audit, Scorecard passed on exact HEAD |

Branch counts were obtained by exhausting paginated branch listings (100 per page). They describe remote branch refs, not necessarily active work. No branch was deleted. The three repositories in this historical baseline use `main` as the default branch and GitHub reported `protected=false`; EL_AGENT branch protection was not established by that observation.

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
| HUB ↔ EL_AGENT | Versioned device-task API and paired-device contract | Four-project integration baseline; physical-device and isolated staging acceptance pending | Keep device execution in EL_AGENT; Hub authorizes and records task state |

No direct cross-repository database access is permitted. Use versioned API contracts, scoped credentials, correlation IDs, idempotency keys, bounded retries, and sanitized errors.

## Tool and permission findings

- GitHub connector: authenticated repository reads and writes are available. Repository metadata reports admin/maintain/push permissions on the three repositories in the initial audit; EL_AGENT access is recorded separately in the four-project addendum. Available actions include branch creation, file creation/update, PR creation, PR review/comment, issue updates, and merge operations.
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


## Exact-head CI refresh — 2026-11-21 19:05 UTC

This addendum supersedes the open-PR CI state above; repository main SHAs are unchanged.

- HUB PR #472 head `b6e6974edc000091f37eac0a2988dd076f1114ce`: Workflow Security Audit, Defensive Python Scan and Video Render Integration passed. CI was cancelled; Backend CI remained in progress at the latest read. Cancelled is not PASS.
- HUB PR #473 head `1eb1b95f79c7f200dfd9a9ac5acbb6d3cd6fba3c`: Workflow Security Audit, Defensive Python Scan and Video Render Integration passed; Windows Launcher Validation failed; CI was cancelled; Backend CI remained in progress at the latest read.
- The failed Windows job executed 70 targeted database/device/backup tests: 69 passed and 1 failed. Failure: `tests/test_device_tasks.py::test_model_device_task_creation_uses_time_after_write_lock_for_grants` — expected `DeviceTaskPermissionError`, but none was raised. See [exact Windows run](https://github.com/MRSIAVASSHIRBOT/MR_SIAVASH_HUB_AI/actions/runs/44938460022).
- Root cause is not yet established. PR #473 is not accepted for merge until the failing regression is understood, fixed if needed, and the exact updated head passes all required checks.
- New HQ documentation PR #474 is open at head `6d58c02da0f74c7f2c5d2c8e2be485cba5ae981d`. Workflow Security Audit, Defensive Python Scan and Video Render Integration passed; CI and Backend CI were still running at this refresh. See [PR #474](https://github.com/MRSIAVASSHIRBOT/MR_SIAVASH_HUB_AI/pull/474).


## Branch inventory count correction — 2026-11-21 UTC

The complete paginated Hub branch inventory contains 472 remote branches (pages 1–4: 100 each; page 5: 72). The prior 372 figure was an arithmetic error. No branch was deleted or modified.


## HQ bootstrap PR count update — 2026-11-21 UTC

The initial repository baseline table recorded two open HUB PRs (#472 and #473) before HQ initialization. This branch subsequently opened documentation-only PR #474. The current open HUB PR count is therefore **3**: #472, #473 and #474. No existing PR was closed or modified by this count update.


# Four-project architecture correction and refreshed baseline — 2026-11-21 UTC

**This section supersedes every earlier statement in this document that described a three-project ecosystem or excluded EL_AGENT.** The authoritative ecosystem has FOUR independent repositories:

1. [MR_SIAVASH_HUB_AI](https://github.com/MRSIAVASSHIRBOT/MR_SIAVASH_HUB_AI) — central control plane and orchestration.
2. [MR_SIAVASH_EL_AGENT](https://github.com/MRSIAVASSHIRBOT/MR_SIAVASH_EL_AGENT) — standalone Windows/Android device-side execution agent.
3. [MR_SIAVASH_EL_AI](https://github.com/MRSIAVASSHIRBOT/MR_SIAVASH_EL_AI) — Telegram-facing conversational and communication interface.
4. [MR_SIAVASH_AI](https://github.com/MRSIAVASSHIRBOT/MR_SIAVASH_AI) — public website, learning surface and public Gateway.

Gshop remains excluded. The separate four-project architecture does not change the active development priority: HUB remains the primary development project.

## Current four-repository baseline

| Repository | Default branch / latest main SHA | Remote branches | Open PRs | Open issues | Latest exact-main CI evidence |
| --- | --- | ---: | ---: | ---: | --- |
| HUB_AI | main / `9ae07b04733ac5555be8bf237437b4570e1985ed` | 473 | 2 | 5 | Security Audit, Scorecard, Defensive Scan, Video Render Integration and Windows Launcher passed; CI and Backend CI still running at snapshot |
| EL_AGENT | main / `d2511f57abe00451ada4b84e5fe1196742393505` | 28 | 2 | 0 | CI passed on exact main SHA; four Ubuntu/Windows × Python 3.11/3.12 jobs succeeded |
| EL_AI | main / `39ea9557b12ebc827e19b0e4d2f274073752b0a2` | 79 | 0 | 1 | CI, Workflow Security Audit and OpenSSF Scorecard passed on exact main SHA |
| MR_SIAVASH_AI | main / `a2428f5208a78e3d8f1181f55af1427448b55483` | 244 | 0 | 2 | Gateway CI, Security Audit, Scorecard, Preview/Production Gateway smoke and Pages quality/deploy all passed |

Branch counts reflect complete paginated inventories observed in this audit: HUB 100+100+100+100+73=473; EL_AGENT 28; EL_AI 79; Website 100+100+44=244. No branch was deleted or modified. All four default `main` branch metadata records report `protected=false`; the branch-protection endpoint is not accessible to the current GitHub integration (403), so no ruleset mutation or protection readback was possible.

### Current open work and status corrections

**HUB_AI**
- Open PR [#472](https://github.com/MRSIAVASSHIRBOT/MR_SIAVASH_HUB_AI/pull/472), head `1a7e3c0fd35c51134497056894c02ccf29efc34d`: all five observed checks (Workflow Security Audit, Defensive Python Scan, Video Render Integration, CI, Backend CI) passed on exact head.
- Open PR [#474](https://github.com/MRSIAVASSHIRBOT/MR_SIAVASH_HUB_AI/pull/474), HQ documentation. Latest observed head `e885e514c20148f60dbefb0f86eee49270a32ad4`: Workflow Security Audit, Defensive Python Scan, Video Render Integration and Backend CI passed; CI remained in progress at the last exact-head read. This PR is being expanded to include the fourth project baseline.
- PR #473 is now **merged** into main at `9ae07b04733ac5555be8bf237437b4570e1985ed`. Its previously failing Windows regression rerun completed successfully; Windows Launcher Validation on the merged main SHA also passed. The earlier statement that #473 was blocked is superseded.
- Five open issues remain: #200, #182, #298, #304 and #305. #298 references payment/production credential/CORS resources outside this workspace execution scope; do not act on it here.
- Latest main CI had CI and Backend CI still running, while security audit, Scorecard, Defensive Scan, Video Render Integration and Windows Launcher Validation passed.

**EL_AGENT**
- Exact repository located through authenticated owner-repository listing and exact-name repository search: [MRSIAVASSHIRBOT/MR_SIAVASH_EL_AGENT](https://github.com/MRSIAVASSHIRBOT/MR_SIAVASH_EL_AGENT), repository ID `1465333314`, public, default branch `main`, created 2026-11-20, last pushed 2026-11-21.
- Open [PR #23](https://github.com/MRSIAVASSHIRBOT/MR_SIAVASH_EL_AGENT/pull/23), Draft: Windows scoped Hub task consumer; 14 files, +1313/-48. Exact head `dfd482971340fcfe69d36855e005e9fa397062aa`. Python CI matrix, Android workflow and push CI observed successful. Physical Windows 11 and isolated Hub Staging acceptance remain pending.
- Open [PR #25](https://github.com/MRSIAVASSHIRBOT/MR_SIAVASH_EL_AGENT/pull/25), Draft: Android reviewed planner, offline runtimes and foreground Hub consumer; 42 files, +4859/-83. Exact head `1f57a3810e6c0ed1bf7eb9959f13db1e8e8195a4`. Exact-head Python CI and Android debug build/unit tests both passed. Physical Android and isolated Hub Staging/revocation acceptance remain pending.
- No open Issues. The repository has 28 remote branches, all observed unprotected.
- Main CI run [44933709135](https://github.com/MRSIAVASSHIRBOT/MR_SIAVASH_EL_AGENT/actions/runs/44933709135) passed all four Ubuntu/Windows and Python 3.11/3.12 matrix jobs. Android workflow is path-filtered and was not observed on the latest main commit; PR #25's exact-head Android workflow passed.
- Main README documents a Windows 0.2.0 local-first MVP: loopback-only authenticated API, explicit screenshot, fixed app allowlist, local scheduler, task list/cancel, desktop control center, deterministic Persian/English command parser, optional per-user startup, local Ollama-first text provider and opt-in local push-to-talk. Hub pairing on main is heartbeat-only; remote task dispatch is not yet on main.
- Android companion preview includes owner pairing, Android Keystore credential storage, heartbeat, foreground push-to-talk prototype and explicit local app launch. Physical-device acceptance is pending.
- Main roadmap explicitly leaves clean Windows 11 install/live acceptance, Hub-issued task dispatch, shared memory, Android physical acceptance, wake word, hybrid voice and adaptive memory/planning unfinished.

**EL_AI**
- PR #78 is now **merged** into main at `39ea9557b12ebc827e19b0e4d2f274073752b0a2`; it adds authenticated Hub client redirect protection. Exact-main CI, Workflow Security Audit and Scorecard all passed.
- One open issue remains: #5 (main branch protection).

**MR_SIAVASH_AI**
- No open PRs; two open issues remain: #70 (main branch protection) and #120 (Gateway deployment/source reconciliation).
- Six exact-main workflows passed. GitHub Pages publication passed; Cloudflare production source/version parity is not established by CI alone.

## Four-project acceptance boundary

- CI PASS is not physical-device acceptance, live integration acceptance, deployment confirmation or production health.
- EL_AGENT remains independently useful in local/standalone mode. Hub pairing and remote task relay are optional adapters, not startup dependencies.
- Hub is authoritative for ecosystem owner identity, shared grants, cross-project policy, shared task relay/audit and shared memory services. EL_AGENT owns its local runtime, platform capabilities, local settings, local scheduler and future local-memory implementation; do not claim local memory is shipped until its implementation and tests exist.
- EL_AI remains the Telegram interface, not the device executor. It submits only scoped requests to Hub; it does not directly invoke local Windows/Android tools.
- Website/Gateway receives public-only projections and public request context. It never receives private Hub memory, owner tasks, device credentials or private EL_AGENT telemetry.
- No repository may access another repository's database or private filesystem directly.
