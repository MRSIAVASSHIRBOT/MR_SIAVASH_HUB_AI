## Current Hub and ecosystem state refresh — 2026-11-21 (latest verified GitHub state)

This addendum supersedes earlier repository and companion snapshots below where they conflict. It records exact GitHub commits and Actions evidence only. It is not a fresh Cloudflare inventory, Production release approval, live bot acceptance, Hub Staging acceptance, or physical-device acceptance.

### Verified repository heads

- **Hub `main`:** `358d5c934a0c60e585032c14bd68a296571ad174`. Security PR [#469](https://github.com/MRSIAVASSHIRBOT/MR_SIAVASH_HUB_AI/pull/469) merged private-media integrity checks and stable-descriptor download snapshots at this commit. Exact-head PR checks passed: Backend CI (1,372 tests passed, 2 skipped, 86% coverage on Python 3.11), the complete Python 3.11/3.12 and Windows wheel smoke matrix, Workflow Security Audit, Defensive Python Scan, Video Render Integration, and Windows Launcher Validation. All seven post-merge main workflows also passed on `358d5c9`: Workflow Security Audit [44934503074](https://github.com/MRSIAVASSHIRBOT/MR_SIAVASH_HUB_AI/actions/runs/44934503074), OpenSSF Scorecard [44934503148](https://github.com/MRSIAVASSHIRBOT/MR_SIAVASH_HUB_AI/actions/runs/44934503148), Defensive Python Scan [44934503088](https://github.com/MRSIAVASSHIRBOT/MR_SIAVASH_HUB_AI/actions/runs/44934503088), Backend CI [44934503154](https://github.com/MRSIAVASSHIRBOT/MR_SIAVASH_HUB_AI/actions/runs/44934503154), CI [44934503046](https://github.com/MRSIAVASSHIRBOT/MR_SIAVASH_HUB_AI/actions/runs/44934503046), Video Render Integration [44934503062](https://github.com/MRSIAVASSHIRBOT/MR_SIAVASH_HUB_AI/actions/runs/44934503062), and Windows Launcher Validation [44934503212](https://github.com/MRSIAVASSHIRBOT/MR_SIAVASH_HUB_AI/actions/runs/44934503212).
- **Website `main`:** `d1f3634b749e15fc90e29598bc64b19642dbb242`. Website PR [#244](https://github.com/MRSIAVASSHIRBOT/MR_SIAVASH_AI/pull/244) merged the Dark Emerald/privacy release as `bd065af14f756d5bac1c2ef84adf6e931d566d72`; docs-only PR [#245](https://github.com/MRSIAVASSHIRBOT/MR_SIAVASH_AI/pull/245) then refreshed Release Status, roadmap, architecture cache reference, and documentation regression tests, and is merged. On current main, Gateway CI [44934172124](https://github.com/MRSIAVASSHIRBOT/MR_SIAVASH_AI/actions/runs/44934172124), Workflow Security Audit [44934172150](https://github.com/MRSIAVASSHIRBOT/MR_SIAVASH_AI/actions/runs/44934172150), OpenSSF Scorecard [44934172186](https://github.com/MRSIAVASSHIRBOT/MR_SIAVASH_AI/actions/runs/44934172186), Production/Preview Gateway runtime smoke [44934172162](https://github.com/MRSIAVASSHIRBOT/MR_SIAVASH_AI/actions/runs/44934172162) / [44934172119](https://github.com/MRSIAVASSHIRBOT/MR_SIAVASH_AI/actions/runs/44934172119), and Quality/Pages [44934172114](https://github.com/MRSIAVASSHIRBOT/MR_SIAVASH_AI/actions/runs/44934172114) passed. The Quality workflow deployed static Pages and verified published assets against this exact `d1f3634` commit. The active shell restores Dark Emerald, includes the privacy route/assets, and Service Worker v69 caches the offline privacy page. Current source is **102 commits ahead / 0 behind** the last recorded Production Worker source annotation `1616545a2e204cb378e2c824299412ca20ef598b`; this is source drift only. Runtime smoke tests exercise configured endpoints and do not prove current-source deployment to Cloudflare.
- **EL_AI `main`:** `90aa638fff2f515e193e754fa73bad4b79e14e36`. Docs-only PR [#76](https://github.com/MRSIAVASSHIRBOT/MR_SIAVASH_EL_AI/pull/76) aligned Website source evidence; PR [#77](https://github.com/MRSIAVASSHIRBOT/MR_SIAVASH_EL_AI/pull/77) refreshed that checkpoint to Website `d1f3634` and is merged. Exact-main CI [44934891589](https://github.com/MRSIAVASSHIRBOT/MR_SIAVASH_EL_AI/actions/runs/44934891589), Workflow Security Audit [44934891528](https://github.com/MRSIAVASSHIRBOT/MR_SIAVASH_EL_AI/actions/runs/44934891528), and OpenSSF Scorecard [44934891552](https://github.com/MRSIAVASSHIRBOT/MR_SIAVASH_EL_AI/actions/runs/44934891552) passed. The dependency-aware task-plan implementation remains `ff31209cb1d6c380b8cb3df55de17339353a2fec`; no Telegram token, live bot connection, webhook, or production bot deployment is inferred.
- **Device companion `MR_SIAVASH_EL_AGENT` `main`:** `d2511f57abe00451ada4b84e5fe1196742393505`. Security PR [#26](https://github.com/MRSIAVASSHIRBOT/MR_SIAVASH_EL_AGENT/pull/26) merged the Windows Hub client's no-redirect transport guard and bearer-forwarding regression test. Its exact-head CI passed on Windows/Linux with Python 3.11/3.12; post-merge main CI [44933709135](https://github.com/MRSIAVASSHIRBOT/MR_SIAVASH_EL_AGENT/actions/runs/44933709135) passed on all four matrix jobs.

### Hub security and device integration

- The merged PR #469 changes only the private-media download path and tests: stored size/SHA-256 verification, stable-descriptor snapshot, serving only the private snapshot, sanitized 409 plus audit for invalid storage key/integrity mismatch, and unchanged 404 for missing files. Regression coverage includes valid download/cleanup, tampering, missing source, invalid key, and source-path replacement after snapshot creation. No schema migration, new dependency, or publishing behavior was introduced.
- Hub PR #465 remains the merged source for owner-scoped device registry reads and allow-listed app-launch task submission. Owner grants, paired-device scopes, and transactional authorization rechecks remain authoritative.
- Windows permits bounded `app.launch` and explicitly owner-confirmed `screen.capture`; Android supports only its declared app aliases. Arbitrary shell commands, arbitrary executable paths, arbitrary URLs, and model-authored executable payloads are outside the Hub device-task contract.
- Windows consumer PR [#23](https://github.com/MRSIAVASSHIRBOT/MR_SIAVASH_EL_AGENT/pull/23) remains Draft at head `bff91930611c24a2b90bcac4a8f3195f44e37826`; all four exact-head CI matrix jobs passed, but GitHub still reports it non-mergeable against current main after PR #26. Android consumer PR [#25](https://github.com/MRSIAVASSHIRBOT/MR_SIAVASH_EL_AGENT/pull/25) remains Draft at head `df85e6827cc532d18a1d4ffea31f7317bc5e00ee`; its earlier exact-head Python CI and Android build passed before main advanced. Both remain one commit behind current Agent main and need base refresh plus a fresh exact-head run.
- Both client PRs still require isolated Hub Staging round-trips, grant expiry/revocation checks, and physical Windows/Android verification. CI success is not evidence of live device operations. No credentials were paired, no task was submitted to a physical device, and no screenshot or application launch was executed.

### EL_AI dependency-aware plan semantics

- Owner-authored plans support sequential shorthand and explicit 1-based DAG dependencies. Preview is local and creates no Hub tasks; the owner must explicitly start via `/taskplanrun PLAN_ID`, and only root steps are initially submitted.
- Dependent steps advance only after every prerequisite reports `succeeded`. Failed/blocked dependencies persist blocked checkpoints; unavailable status never unlocks dependent work. Stable idempotency keys support recovery after ambiguous Hub outcomes.
- This is bounded orchestration, not unrestricted autonomous execution. Hub policy and approval gates remain authoritative.
- No Telegram token is configured, no live bot connection or webhook registration is verified, and no production EL_AI deployment is claimed.

### Deployment and trust boundaries

- GitHub Pages publication for Website `d1f3634b749e15fc90e29598bc64b19642dbb242` is verified; this does not establish a corresponding Cloudflare Gateway Worker deployment.
- No Cloudflare Worker deployment, Production traffic change, D1 application-data operation, secret mutation, route/DNS change, repository permission change, or physical-device action was performed in this maintenance session.
- Cloudflare was not re-read; prior Worker versions, D1 state, bindings, routes, schedules and source annotations remain historical rather than current live observations.
- GitHub reports all four ecosystem `main` branches (Hub, EL_AGENT, EL_AI and Website) as unprotected. No branch-protection or ruleset setting was changed; configuring required checks remains an owner/admin security task.
- Green CI and Pages publication do not authorize or prove a Cloudflare Worker release.


---

## Current Hub maintenance addendum — 2026-11-21 UTC

This snapshot supersedes older repository snapshots below where they conflict. It distinguishes merged Hub source, review branches, companion branches, and live infrastructure evidence.

### Verified repository state
- Current Hub `main`: `4ebbf92cff4803d34904aa463c330b54c1aba71d`.
- Recent merged commits include:
  - `f917f4293e26c418c7869da0c9c0a44a8724df99`: refresh-token reuse detection, device credential-set revocation, outstanding-task fencing, and bounded pairing challenges.
  - `28e1dd47d26f8e2e331c438c9bbef8cb1fa12f14`: maps the stable public `remote` mode to the Kimi provider registry.
  - `4ebbf92cff4803d34904aa463c330b54c1aba71d`: bounded AI task-plan preview.
- Hub device pairing and bounded task claim/complete API are merged; PR #460 is the API baseline.
- Draft Hub PR [#465](https://github.com/MRSIAVASSHIRBOT/MR_SIAVASH_HUB_AI/pull/465), head `3371f2b0216ba56f431282406e2beb8b3e6ab79b`, adds owner-scoped model tools for device registry reads and allowlisted app launch, two independent expiring owner grants, exact device-scope checks, atomic grant re-check at enqueue, migration 52, and dashboard controls. All 21 observed exact-head checks passed. It remains Draft and is not merged or deployed pending isolated Hub Staging and physical-device acceptance.

### Cross-repository device consumers
- Windows consumer: [EL_AGENT PR #23](https://github.com/MRSIAVASSHIRBOT/MR_SIAVASH_EL_AGENT/pull/23), Draft, based on EL_AGENT `main`, head `ebd67e2605e26e0763f02a294aedbc511e89f1b1`. Its nine observed exact-head checks passed. It is limited to allowlisted `app.launch` and explicitly owner-confirmed local `screen.capture`; physical Windows 11 acceptance remains pending.
- Android consumer: [EL_AGENT PR #24](https://github.com/MRSIAVASSHIRBOT/MR_SIAVASH_EL_AGENT/pull/24), Draft, head `61627e6b93f17f5c9d68b2a816f6903d3710e32d`. Its five observed checks passed, including Android debug build. It is stacked on `feat/android-visual-refresh-20261120` and is not ready to retarget to `main` until the preceding Android stack is merged. The consumer is foreground-only, supports ChatGPT/browser app launch, and requires a separate on-device approval dialog. Physical Android acceptance remains pending.
- These are source/CI results only. No live device round-trip or deployed Hub Staging endpoint was verified.

### Website and EL_AI coordination
- Website `main`: `21657e4e21cf215b1abc1e2df3a8c4bb53d4d15d`; GitHub compare against the last recorded Production Worker source annotation reports 95 ahead and 0 behind. GitHub Pages publication and published-asset verification passed in run [44899174187](https://github.com/MRSIAVASSHIRBOT/MR_SIAVASH_AI/actions/runs/44899174187). Gateway CI and Production/Preview runtime smoke also passed on this SHA; these checks do not prove a new Cloudflare Worker deployment.
- Cloudflare was not re-read on 2026-11-21. The last recorded Production Worker version/annotation and Preview inventory remain historical observations, not fresh live verification. No Worker or D1 change is inferred.
- EL_AI `main`: `df5472c0b8321f3c32e9ad05fac6a7b282316678`. PR #67 merged owner/public Telegram routing and private Hub result/task-progress isolation tests. PR #69 refreshed the Website source snapshot; PR #70 is the current README evidence refresh.

### Security, dependencies, and release controls
- Current branch-protection reads for all three requested repositories returned HTTP 403 `Resource not accessible by integration`. Protection is not independently verified; no ruleset, access-control, or repository permission was changed.
- The Hub staging Worker was reported absent by the last recorded read-only inventory on 2026-11-20; no live Cloudflare inventory was performed on 2026-11-21. Do not repurpose the Website Gateway Preview or GShop resources.
- Hub remains local-first: Ollama is opt-in, Kimi is a separate explicit remote adapter, and there is no silent local-to-cloud fallback. No provider credential or secret value was read or changed.
- No committed Python or Node dependency lockfile was found in the inspected project roots. Reproducible dependency locking and clean Linux/Windows install acceptance remain follow-ups.
- No production Worker deployment, D1 application-row query, secret mutation, route/DNS change, or physical-device operation occurred in this run.

### Next acceptance gates
1. Complete isolated Hub Staging provisioning and authenticated contract acceptance using owner-approved resources and credentials.
2. Merge/rebase the Windows and Android consumer stacks only after their branch dependencies are resolved; then run physical-device pairing, scope, launch, screenshot/approval, expiry, and revocation acceptance.
3. Keep PR #465 Draft until the Hub tool adapter is validated against Staging and companion behavior.
4. Complete Website Cloudflare source review, Preview acceptance, D1 migration/backup/rollback verification, and explicit Production owner approval.
5. Have the repository owner configure and independently verify main-branch protection and exact-head required checks.

No deployment, production configuration, application data, repository secret, Cloudflare resource, or access-control setting was changed during this documentation update.
---

## Portfolio maintenance addendum — 2026-11-16 12:14 UTC

This snapshot supersedes the 2026-11-15 repository snapshot below where the values differ. It records GitHub and repository evidence observed during the coordinated maintenance run.

### Active repository snapshot

- **Hub `main`:** `57ac03024fa05cf76fc81d10a372944176ef98d6`. PR [#411](https://github.com/MRSIAVASSHIRBOT/MR_SIAVASH_HUB_AI/pull/411) was merged as this commit. The 21-file change adds verified source-audio passthrough to bounded local FFmpeg renders, owner-scoped output metadata, exact FFprobe audio-stream verification, metadata/chapter stripping, and regression plus real Linux/Windows FFmpeg coverage. The exact PR head `03ffbfaeac1563e03338909c15b92851b2686f24` passed its observed PR/branch checks. Post-merge main checks were not yet complete at this snapshot: 11 of 14 check-runs had succeeded, while Backend CI and the Python 3.11/3.12 test matrices were still running. Do not call the post-merge suite fully green until all 14 checks finish.
- **Website `main`:** `00f653837e1796ee85d0587f2c4095b3c7f0a258`. No open PR was present. Current-main Quality/Pages, Gateway CI, Production Runtime Smoke, Preview Runtime Smoke, Workflow Security Audit, and OpenSSF Scorecard runs succeeded. The Pages deployment job is manual-only and was not run by these push checks.
- **EL_AI `main`:** `7676f7aa7ebf789717110687f68a8840d98fe53d`. No open PR was present. Python 3.11/3.12 CI, Workflow Security Audit, and OpenSSF Scorecard succeeded. The README still correctly states that no Telegram token is configured, no live bot has been connected, and no production bot deployment has occurred.
- No open PR was present in any of the three active repositories after Hub PR #411 merged.

### Cross-repository contract

Hub remains authoritative for private memory, tasks, agents, approvals, tool policy, and audit. EL_AI owns Telegram transport and uses owner-initiated pairing with explicit scoped Hub routes; its current command set includes read-only video route preview, owner-scoped video history/status, and pending-only cancellation. The public Website Gateway remains public-only and must not receive Hub credentials or private Hub context. No shared database or implicit trust is permitted.

### Dependencies, tests, and release controls

- Hub dependencies are declared in `pyproject.toml` (FastAPI, Uvicorn, Pydantic/settings, HTTPX, Cryptography; pytest, coverage, Ruff, pip-audit, Bandit and MCP in development extras). CI includes Backend CI, Python 3.11/3.12 tests, Windows wheel smoke, Linux/Windows FFmpeg integration, Windows launcher validation, Defensive Python Scan, Workflow Security Audit and Scorecard.
- EL_AI declares HTTPX and Keyring, with pytest/pytest-asyncio/Ruff for development; CI runs Python 3.11 and 3.12.
- Website Gateway's `cloudflare/gateway/package.json` defines Node's built-in test runner and has no external package dependency. Repository CI runs JavaScript tests, OpenAPI validation, isolated SQLite migration checks, Chromium Academy E2E and accessibility/responsive smoke.
- No committed Python or Node dependency lockfile was found in the inspected active project roots. Reproducible lockfile-based installs remain a follow-up.
- The last recorded read-only Website Production inventory reported Worker version 14 (`62e8a337-d804-4748-8bb2-d5e0180ee2f8`) at 100% traffic, annotated with source `1616545a2e204cb378e2c824299412ca20ef598b`; Cloudflare was not re-read in this checkpoint. Current Website `main` `42fc965f4d22755007ce706151ae85556ddfe9d0` is 55 commits ahead and 0 behind that source baseline by GitHub compare. This is source drift, not deployment evidence. Issue [#120](https://github.com/MRSIAVASSHIRBOT/MR_SIAVASH_AI/issues/120) remains open. The delta includes Gateway runtime/tests and migrations 0004/0005; isolated migration tests pass in CI, but live Production D1 migration state and current Worker version were not queried. The Production release workflow is manual-only, defaults to `deploy=false`, and retains its owner-controlled environment gate.
- The scheduled Hub Continuous Development and comment-triggered OpenCode workflows were removed and merged in [PR #436](https://github.com/MRSIAVASSHIRBOT/MR_SIAVASH_HUB_AI/pull/436) (`aca5f198fb6e372436bdbff67aaff7385841b4ee`). No provider credential renewal or isolation work is required for those retired workflows.
- Fresh GitHub branch metadata on 2026-11-20 reports `main.protected=false` for Hub, Website, and EL_AI; required-status-check enforcement is off with no required contexts/checks. No branch-protection, ruleset, or access-control setting was changed.

### Next engineering priorities

1. Keep Hub PR #460 Draft until the device-task and specialist-profile scope is reviewed. Code head `24428ebc8890c71bf384eceb9db83a525117d5cd` passed exact-head checks; a documentation-only follow-up is re-running CI. No Hub task API has been merged or deployed.
2. Complete the separate EL_AGENT task polling/claim/outcome client and live Windows acceptance; the current companion supports owner-initiated pairing and heartbeat only.
3. Keep Website Production release gated: the current GitHub source delta is 55 commits; isolated migration tests pass, but live Production D1 migration state and current Worker inventory remain unverified. Require fresh Preview, backup/rollback, migration, and owner approval evidence before release.
4. Verify whether the retired `MR_SIAVASH_HUB_AI` Actions secret remains in repository settings; if present, remove it. Do not renew or replace it.
5. Owner/admin action is still required to enable branch protection and required checks on all three repositories; current GitHub branch metadata reports `main.protected=false` for each.
4. Have the repository owner configure and verify branch protection and exact-head required checks for all three repositories.
5. Add reproducible dependency lockfiles and verify clean Linux/Windows installs.
6. Keep EL_AI on the scoped Hub contract; perform live Telegram acceptance only after the owner configures its token securely.

No secret values, production application data, Worker deployments, D1 migrations, routes, schedules, repository permissions, or access controls were changed during this run. No local test suite was executed in this automation environment; test results above are hosted GitHub Actions results tied to the stated SHAs.

---

## Portfolio maintenance addendum — 2026-11-15 UTC

This addendum supersedes older scope and point-in-time snapshots below where they differ. It records repository and operational evidence observed during the current portfolio run.

### Current maintenance scope

- **Active:** `MR_SIAVASH_HUB_AI` (primary), `MR_SIAVASH_AI` (website and public Gateway), and `MR_SIAVASH_EL_AI` (Telegram companion).
- **Discovery-only Backlog:** `MR_SIAVASH_EL_IR_BOT` and `MR_SIAVASH_IR_H_BOT`. Do not modify their code, workflows, secrets, infrastructure, schedules, deployments, routes, or permissions.
- **Explicitly excluded:** `Gshop`. Do not inspect or operate its repository or production resources during this maintenance cycle.
- PostZen publishing is a separate automation and is not part of engineering or technology-radar runs.

### Current repository snapshot

- **Hub main:** `0a9735fdf3ad2d898151861c15971672338e4fc5`. PR [#407](https://github.com/MRSIAVASSHIRBOT/MR_SIAVASH_HUB_AI/pull/407), owner-scoped video-generation history and dashboard controls, merged as this commit. Its exact PR head `ff0eeca60601f77f384221c161bb456f9dbc928b` passed 22/22 observed check-runs. Post-merge main validation passed 14/14 check-runs on `0a9735fdf3ad2d898151861c15971672338e4fc5`. No production deployment occurred.
- **Hub PR #406:** remains Draft at `03d82c7b53e090926010568798f8c7c0791802a9`. Its exact-head checks passed on the earlier base, but the branch is now 14 commits ahead and 1 behind the post-#407 main. It is not integrated, does not register a provider, and must remain Draft until synchronized and revalidated on the current base.
- **Website main:** `31e8fc6cf22a0e821621dec0dfe28186b47b2dae`. Gateway CI, Gateway Runtime Smoke, Preview Runtime Smoke, Quality syntax checks, Workflow Security Audit, and OpenSSF Scorecard passed. The static-site deployment job was skipped; no Pages release is claimed.
- **EL_AI main:** `6bedd95ed62ef1c3b20a829a6ff09840adc786cc`. Python 3.11/3.12 CI, Workflow Security Audit, and OpenSSF Scorecard passed. No open PR is present in the current snapshot.
- No local repository test suite was run in this automation environment. Test claims above are hosted GitHub CI results tied to the stated SHAs.

### Cross-project trust contract

The Hub v1 manifest is the canonical contract. Hub owns private memory, tasks, policy, approvals, and audit. EL_AI uses owner-initiated pairing and only the scoped `/integrations/telegram` API; the default grant is `status:read`, with additional task and memory scopes explicitly granted. EL_AI must not access the Hub database directly or expose arbitrary shell, code execution, broad MCP, or approval decisions through Telegram. The public website Gateway is public-only: it must not call private Hub endpoints, receive Hub credentials, or access private Hub memory. No shared database or browser-held Hub credential is permitted.

### Infrastructure and release findings

- GitHub reports `main.protected=false` and an empty rulesets list for all three active repositories. Required current-head checks, force-push/deletion restrictions, and PR-only changes are not repository-enforced. Configuration remains an owner/admin action; no governance settings were changed.
- The website Worker `mr-siavash-ai-gateway` is serving 100% of traffic on its latest observed deployment from 2026-11-11. Its latest version is `62e8a337-d804-4748-8bb2-d5e0180ee2f8`; its daily schedule is `0 3 * * *`.
- Issue [#120](https://github.com/MRSIAVASSHIRBOT/MR_SIAVASH_AI/issues/120) records deployed source commit `971a5e702876a0bc78b19c55b8b0daf358471c5`. Current website main is 46 commits ahead of that source baseline. The compare includes changes to `cloudflare/gateway/src/index.js` and the new D1 migration `0004_support_retention_runs.sql`. The current Worker deployment has not been reconciled to this newer source; do not deploy without the explicit release gate and rollback/acceptance plan.
- No Worker named for Hub or EL_AI was found in the current Cloudflare Worker inventory. This does not establish that EL_AI has no deployment on another platform; live Telegram operation is not verified.
- The two Python repositories and the website/Gateway tree contain no `uv.lock`, `poetry.lock`, `Pipfile.lock`, `requirements*.txt`, `package-lock.json`, `pnpm-lock.yaml`, `yarn.lock`, or Bun lockfile in the inspected tree. Dependency reproducibility remains a foundation gap; evaluate a generated, committed lockfile and exact CI sync before upgrading packages.
- The provider registry remains empty by default. No production provider, paid service, model download, or provider credential has been selected or enabled.
- Issue [#332](https://github.com/MRSIAVASSHIRBOT/MR_SIAVASH_HUB_AI/issues/332) is obsolete after PR #436 merged and is being closed; Issue [#316](https://github.com/MRSIAVASSHIRBOT/MR_SIAVASH_HUB_AI/issues/316) was already closed.

### Discovery-only Backlog snapshot

- **EL_IR_BOT:** main `d562d8126863cc4d9eaa5e68d123f674a964e486`; no open PR; tests, Workflow Security Audit, and OpenSSF Scorecard passed. Issue #1 remains open for sensitive-data consent and privacy boundaries. A Cloudflare Worker with the same name is live at 100% traffic, latest deployment 2026-11-11, schedule `17 3 * * *`, with D1 database `mr-siavash-el-ir-bot-state`. This is read-only observation only; its Backlog status is unchanged.
- **IR_H_BOT:** main `3bb2244b852cabf95b92efaa08f0c939863d6c35`; no open PR; latest Pages build/deployment run on 2026-10-24 succeeded. Issue #1 remains open for microphone-consent and voice-message handling. No corresponding Cloudflare Worker was found in the inspected inventory.

### Next engineering gates

1. Keep Hub as the single primary development project; synchronize and revalidate Draft PR #406 after the #407 merge.
2. Resolve Hub provider-credential ownership and process-isolation gates without reading or exposing secret values.
3. Reconcile the website Gateway's 46-commit source drift through a reviewed Preview and release acceptance; do not deploy automatically.
4. Establish lockfile-based reproducible installs for Python and Node projects using a trusted toolchain, then verify Linux/Windows CI.
5. Have the repository owner/admin configure and verify branch protection and exact-head required checks.
6. Keep EL_AI on the narrow v1 contract and preserve the public Gateway's public-only boundary.
7. Keep both Backlog repositories discovery-only; the active EL_IR_BOT Worker and its privacy finding require an owner decision, not automatic reactivation or modification.

No secret values, credentials, production data, routes, schedules, deployments, or repository permissions were changed. Only repository and infrastructure metadata was inspected read-only.

# Project Status Ledger

Last reviewed: 2026-11-15 (UTC)

## Live status addendum — 2026-11-13

This addendum supersedes older live-status and workflow snapshots below where they conflict. Historical merge records remain unchanged. The SHA below is the application-code baseline reviewed before this documentation-only refresh; the ledger commit itself is not intended to be a self-referential live SHA.

- Reviewed `main` code baseline: `1b9e0cf4826f898d8042a6da87fd29ee95988ff5`. It is 7 commits ahead of the prior recorded baseline `fcfde61efc504c4204eb6b7c3bb2ea76bf11ee9a`, with no commits behind.
- Hub PR #365 corrected the Windows display-class registry path and added a mocked `winreg` regression test. It was merged on 2026-11-13; all 12 exact-head checks and all 12 post-merge main checks passed.
- Hub PR #367 removed HTTPX exception chaining from the then-existing third-party and Kimi provider adapters, so failures no longer retain credential-bearing request context; regression tests cover timeout and transport failures. It was merged on 2026-11-13 after all 12 exact-head checks passed. Post-merge main CI was still running when this snapshot was prepared.
- Historical note: the scheduled OpenCode workflow was previously blocked by provider authentication. That workflow and its provider execution path are removed by PR #436; the old run is not an active project blocker.
- No provider credential was read, copied, rotated or changed. No credential renewal or process-isolation work is required for the retired workflow; the old security discussion is retained only as historical audit context.
- GitHub branch metadata reports `main.protected=false`. The available connector has no branch-protection/ruleset write operation, so protection remains an owner action. Issue #304 tracks it.
- Pull-request state is intentionally sourced from live GitHub metadata rather than this static ledger; re-check open PRs and exact-head CI before every merge. Issue #332 is obsolete after PR #436 merged; Issue #316 is already closed.
- This historical review predates the retirement in PR #436. No secrets, permissions, deployment settings or production resources were modified by that review.

## Previous status snapshot


This is a live hand-off snapshot. Re-check GitHub metadata and latest-head CI before every merge or implementation decision.

## Product definition

MR_SIAVASH_HUB_AI is a local-first, hybrid-capable modular AI workspace for one primary user. Discover and evaluate third-party open-source projects, then integrate them through reviewed adapters and bounded interfaces; do not blindly copy repositories. Prefer free/open-source components without promising every provider or operation is free. No silent cloud fallback.

Historical scope note: older portfolio snapshots may mention Gshop or other repositories as active. They are superseded by the current maintenance scope above; Gshop is explicitly excluded from this cycle.

## Main baseline and merged hardening

- Main contains the FastAPI/SQLite control-plane baseline, task/job state, cancellation, policy checks, structured audit events, local owner authentication, action-bound approvals, capability-aware model routing, deterministic stub, and opt-in loopback-only Ollama adapter.
- PR #11 historically pinned the OpenCode action to a specific commit SHA; the associated provider-backed workflows were later retired in PR #436.
- PR #12 is merged: the historical scheduled code-agent used an explicit third-party model identifier. That provider-specific workflow has since been retired.
- PR #15 is merged via integration commit `0caa50637800c470b1d52f4ebd2ada78f9196ab8`: it brings worker-owned workflow execution, durable recovery, lease fencing, cancellation handling, worker heartbeat readiness, and the metadata-only capability discovery catalog into `main`. Backend CI and CI passed on integrated head `87438c66f102be5faf62c35391c4dc9cab8a0f3e`, including Python 3.11 and 3.12.
- PR #16 is merged via squash commit `e91c9d51c258292cf995e2b4fbb6b24469d91718`; its initial regression was superseded by a stronger fault-injection test.
- **PR #19 — real external-side-effect crash injection**: merged via squash commit `603b5b141b711cbfbfdaf04bba00969e0078464e`. The test injects an abrupt process crash after the simulated remote action is accepted and before the step result/checkpoint is persisted, then verifies `unknown_outcome` recovery and no automatic replay. Backend CI and CI passed on exact head `6e8b76de633c9776ac7b98022435ffa5d37394ec` (Python 3.11 and 3.12).
- PR #21 is merged via `05cfe315059bbf947278c6c844b75ebbc78caf8a`: a real-process smoke test launches FastAPI and the pull worker separately, enqueues a deterministic workflow over HTTP, and verifies durable success. CI and Backend CI passed on exact head `374295a2441768e9d1b54664990145a1b25f9188`.
- PR #22 is merged via `6cfe5dae7107ebe8754764b6f917fbf848f80e05`: migration 10 adds owner-scoped private memory entries and SQLite FTS5 indexing; authenticated CRUD, lexical search, export, expiry filtering/purge, and metadata-only audit events are implemented. CI and Backend CI passed on exact head `fbccb475e33f94323f27317ba4e547c804f9d8a5`.
- PR #24 is merged via `d879be8a6cf8fc9ed87be2b092a64195dd7c402f`: migration 11 adds owner-scoped source/document/chunk records, bounded text ingestion, SHA-256 provenance, FTS5 retrieval with citation references, export/delete, and a synthetic retrieval evaluation corpus. User-supplied URLs are labels only; no fetching or crawling occurs. CI and Backend CI passed on exact head `2fbc441836afe12f0798b840598a2496cd82823c`.
- PR #25 is merged via `bb7623e1a8da5f848b8a947524e8cc69d8fe6b70`: the optional third-party text adapter was restricted to its approved HTTPS origin, used bounded requests and sanitized errors, was disabled by default, and had an explicit generation endpoint with no silent fallback; the adapter has since been retired. CI and Backend CI passed on exact head `8866bb117e448c6f6a22f6732d2e0eb955d15d41`.
- PR #26 is merged via `6efdab80677338a2fcdae8847f39c5fc6521b337`: the initial self-hosted RTL operator UI exposes status, tasks, provider catalog, memory and knowledge controls, and separate local and provider-catalog controls. It uses sessionStorage, a restrictive CSP, no third-party assets, and textContent rendering. CI and Backend CI passed on exact head `cf4c1b726389500c317e20ca48afe28ef396b73f`.
- **PR #29 — local media asset foundation**: merged via `6f90672dc0ea9ad368a68153b3e328fd5df336ea`. Adds owner-scoped local media metadata/storage, bounded upload validation, safe retrieval, fixed-argument FFmpeg video transcoding with resource/time limits, and migration 13. It does not enable social publishing or arbitrary media commands. Backend CI and CI passed on the exact PR head after fixing import order and registering the media router.
- **PR #30 — worker-owned workflow resume**: merged via `fac6d547a731d72f38d50d9bff2f9522343335b7`. Resume requests now validate and enqueue; only the pull worker resumes under its lease/fencing token. Queued and in-flight resume cancellation, final-checkpoint/no-replay behavior, and validation failure are covered. Issue #5 is closed as completed. Backend CI and CI passed on exact head `f3074da24c9adf86a24c36d4a4f2e1e650dbf004`; Backend suite: 297 passed.
- **PR #31 — Job and Workflow operator console**: merged via `bbb95e5c6c67d1741bc95d0c3fa45f8c279487ce`. Adds bounded owner-scoped workflow history, live Job Engine metrics, workflow step inspection, cancellation, resume-check/enqueue, and manual reconciliation of externally verified outcomes. Backend CI and CI passed on exact head `3879bda0d33a8f0e2a7cdc909553b0f328a681e4`; Backend suite: 298 passed.
- Local inference remained disabled by default unless explicitly configured; the optional third-party text adapter has since been removed. Memory and knowledge retrieval are not automatically injected into Agent context. Content drafts and local media foundations exist, but external publishing, scheduling, and external media generation remain roadmap work.

## Live pull-request snapshot

Checked 2026-11-02 (UTC). Re-check live GitHub metadata before making a new merge decision.

- **PR #3 — Phase 4.2 worker-owned workflow execution**: closed without merging; its reviewed implementation is included in PR #15's integrated main commit. A supersession comment explains the disposition.
- **PR #4 — ADR-0042 knowledge/memory architecture**: merged as documentation-only via `ca5bc51871a85bf4c1ad22baed60a1ce84569907`. This is an architecture proposal, not an implementation of memory.
- **PR #6 — workflow dispatch and GitHub capability discovery**: closed without merging. Its original branch diverged from its recorded base (140 ahead / 69 behind) and proposed an alternate submission/dispatch implementation duplicating the architecture now on main. The capability-catalog part is included in PR #15. A comment records why the original branch was closed and requires any genuinely unique future improvements to use a fresh main-based PR.
- **PR #7 — Phase 4.3 cancellation/recovery hardening**: closed without merging; its reviewed implementation is included in PR #15's integrated main commit.
- **PR #10 and PR #13 — project status ledger**: merged. Keep this ledger current through reviewed documentation changes; live metadata remains authoritative.
- **PR #11 and PR #12**: merged. Do not list either as open.
- **PR #14 — standalone capability discovery**: closed without merging because the same reviewed catalog is included in PR #15.
- **PR #15 — Phase 4.2/4.3 worker hardening + capability discovery integration**: merged via `0caa50637800c470b1d52f4ebd2ada78f9196ab8`. Latest-head Backend CI and CI passed on `87438c66f102be5faf62c35391c4dc9cab8a0f3e`.
- **PR #16 — worker crash after external side effect regression test**: merged via `e91c9d51c258292cf995e2b4fbb6b24469d91718`. Backend CI and CI passed on `81bf8868e3869468c00a95988db81cdeb6428e39`.
- **PR #21 — separate-process workflow runtime smoke test**: merged via `05cfe315059bbf947278c6c844b75ebbc78caf8a`. Both CI workflows passed on the exact PR head.
- **PR #22 — owner-scoped memory and FTS5 search**: merged via `6cfe5dae7107ebe8754764b6f917fbf848f80e05`. Both CI workflows passed on the exact PR head.
- **PR #24 — source-backed knowledge ingestion and citation search**: merged via `d879be8a6cf8fc9ed87be2b092a64195dd7c402f`. Both CI workflows passed on the exact PR head.
- **PR #25 — historical third-party remote text inference (subsequently retired)**: merged via `bb7623e1a8da5f848b8a947524e8cc69d8fe6b70`. Both CI workflows passed on the exact PR head.
- **PR #26 — self-hosted operator UI**: merged via `6efdab80677338a2fcdae8847f39c5fc6521b337`. Both CI workflows passed on the exact PR head.
- **PR #29 — local media asset foundation**: merged via `6f90672dc0ea9ad368a68153b3e328fd5df336ea`. Both CI workflows passed on the exact PR head after the media router/import correction.
- **PR #30 — worker-owned workflow resume**: merged via `fac6d547a731d72f38d50d9bff2f9522343335b7`. Both CI workflows passed on exact head `f3074da24c9adf86a24c36d4a4f2e1e650dbf004`.
- **PR #31 — Job and Workflow operator console**: merged via `bbb95e5c6c67d1741bc95d0c3fa45f8c279487ce`. Both CI workflows passed on exact head `3879bda0d33a8f0e2a7cdc909553b0f328a681e4`.

## Integration outcomes and remaining risks

- The overlapping worker/recovery/cancellation code from PR #3 and PR #7 is now represented in one main-based integration commit, rather than merging their long feature-branch histories.
- Lease fencing and interrupted external-step recovery are covered by existing regression tests. PR #19 provides the stronger fault-injection case: the worker crashes at the dispatch boundary after a simulated external effect is accepted, then a fresh worker marks the step `unknown_outcome` and does not replay it.
- Capability discovery is metadata-only: it queries public GitHub repository metadata, does not download or execute source code, and never auto-approves candidates. Approval requires explicit license, security, compatibility, and test-plan evidence.
- The original PR #6 worker-dispatch changes were not merged wholesale because they duplicate the current `jobs/workflow_dispatch.py`, `jobs/payload_envelope.py`, and `jobs/idempotency.py` architecture and also conflict on ADR numbering. Any unique improvement needs a fresh, focused PR based on current `main`.
- The memory and source-backed knowledge APIs now support private owner-scoped records, bounded text ingestion, source/chunk provenance, citation-bearing FTS5 retrieval, export/delete, and a synthetic retrieval evaluation corpus. Retrieved content is not automatically inserted into agent prompts; prompt-injection resistance, context assembly, and context-size policy must be evaluated before integration.
- The initial third-party text adapter was opt-in and text-only; it was not a general tool-calling or publishing adapter and has since been removed. The self-hosted operator UI is implemented, but deployment hardening is still required before any non-loopback exposure.
- The content/media vertical is partially implemented: owner-scoped content drafts and local media assets/transcoding exist; external social publishing, scheduling, and external generation remain unimplemented.

## Recommended next steps

1. Continue operational readiness work: deployment runbook, backup/restore, worker heartbeat thresholds, and a documented loopback-only default. Do not claim production readiness until a deployment smoke test is performed in the intended environment.
2. Add a synthetic prompt-injection corpus and bounded context assembler for retrieved knowledge. Preserve citations and source trust labels; keep context injection disabled until the evaluation and tool-boundary regressions pass.
3. Extend the content/media vertical with reviewed social-channel adapters and scheduled publishing jobs behind explicit approval, deduplication, and audit controls. Keep external generation optional and disabled by default.
4. Add additional remote providers only when a concrete requirement exists; each must remain opt-in, bounded, cost-aware, and free of silent fallback.
5. Continue with NEXUS read-only analysis and reviewable patches, defensive security, and packaging after these core verticals stabilize.

## Definition of done for each code change

- Isolated branch and linked PR with a narrow, explicit scope.
- Formatting/lint, unit/integration tests, relevant security regressions, and dependency audit run as applicable.
- Latest-head CI is green; an earlier successful commit is insufficient.
- Failure/cancellation paths are tested; ambiguous external effects are not blindly replayed.
- No secrets, tokens, or sensitive execution payloads are committed or logged.
- High-impact actions remain policy-gated and require configured approval.
- PR text distinguishes verified behavior, limitations, and planned work.

## Safety and trust boundaries

Only legitimate software development, content creation, and authorized defensive security are in scope. Do not implement credential theft, phishing kits, malware/payload generation, covert tracking, unauthorized access, or evasion. Review license, maintenance, dependency, security, and compatibility before integrating third-party code.

## Status reporting rule

Never report a feature complete based only on a plan, PR description, or successful test claim. Verify code/branch, latest CI, relevant tests, and actual integration state. Always distinguish main, draft PR branches, and roadmap work.


## Superseding live snapshot — 2026-11-02

This section supersedes any earlier statements in this ledger that conflict with the merged main head below. The current main commit at the time of review is `d2e4689dcdc873391ca4820dfaba60fba6298cbf`.

### Newly integrated milestones

- **PR #32 — status/roadmap synchronization**: merged.
- **PR #33 — bounded memory and knowledge context assembly**: merged. The assembler is present, but this does not by itself establish a fully model-driven agent reasoning loop or prove that every agent path consumes retrieved context.
- **PR #34 — durable approval-gated content scheduling**: merged. Schedule records and approval/version binding are implemented.
- **PR #35 — worker-driven schedule dispatch**: merged. Dispatch is pull-driven through the worker; it does not create an always-on scheduler at API startup.
- **PR #36 — configurable Telegram publishing adapter**: merged. Telegram text publishing is opt-in through environment configuration and an explicit worker cycle. Telegram does not provide a provider idempotency key for `sendMessage`; ambiguous outcomes are quarantined rather than blindly retried.
- Instagram publishing remains unavailable: it requires the professional-account Graph API path, credentials, and a publicly reachable media URL. The local media asset endpoint is not a substitute for a public media URL.

### Exact-head CI evidence

On `d2e4689dcdc873391ca4820dfaba60fba6298cbf`, both latest push workflows completed successfully:
- Backend CI: run [41374734670](https://github.com/MRSIAVASSHIRBOT/MR_SIAVASH_HUB_AI/actions/runs/41374734670)
- CI: run [41374734542](https://github.com/MRSIAVASSHIRBOT/MR_SIAVASH_HUB_AI/actions/runs/41374734542)

These results verify the configured CI jobs on this commit; they do not replace target-device runtime, backup/restore, or real provider-account acceptance tests.

### Current product boundaries

- The memory/knowledge context assembler is implemented, but retrieval evaluation, prompt-injection regression coverage, and safe integration into a true model-driven agent loop remain explicit gates.
- The content path now includes drafts, approval, durable schedules, worker dispatch, and an opt-in Telegram text adapter. Instagram, media publication, and external generation are not complete.
- The workflow engine is durable and worker-owned, but a production-grade emergency stop and multi-worker deployment approval remain open.
- The operator UI exists; production exposure, backup/restore verification, packaging, and target-device resource measurements remain open.

See [remaining-work-dependency-map.md](architecture/remaining-work-dependency-map.md) for the seven remaining workstreams, their prerequisites, and acceptance gates.


## Superseding integration snapshot — 2026-11-02 UTC

This snapshot supersedes earlier roadmap/status statements that conflict with the merged PRs listed here. Review baseline immediately before this documentation update: main contained `e0166007ea42dafa1ef780d9094c0d3b1baf79b4`. CI on that pre-documentation head was still running when checked; do not treat it as a completed check result.

### Newly merged milestones

- **PR #44 — registry-driven migration expectations**: merged as `71d5a347a49643e6ad64cd3f57d13b5dd1bf14f5`. Migration tests now derive expected versions from `MIGRATIONS`, avoiding hard-coded version lists when new migrations are added.
- **PR #45 — verified local SQLite backup/restore**: merged as `5552286b28edc5fb2fbc484a5e057e8d70febf95`. Adds SQLite online backup, SHA-256/size manifest validation, SQLite quick-check, no-overwrite destination publication, tests, and a release-readiness checklist. This backs up SQLite only; media files, provider secrets, and workflow encryption keys remain separate.
- **PR #46 — bounded model-driven Agent orchestration primitive**: merged as `1576a6204158a62dd19a085b717fc8199275d9d5`. Adds a finite model/proposal/tool/observation loop with strict proposal schema, turn/input/tool/output limits, cancellation checks, and independent server-side registry policy checks. It is not yet connected to the public API, durable worker jobs, or the context assembler; this is a primitive, not a complete autonomous agent.
- **PR #47 — NEXUS read-only Python static analysis**: merged as `0bdaee649d1a469d2e09397686392068c2599db9`. Adds bounded repository inventory and AST checks with file/line/rule evidence; analyzed code is not imported or executed and no files are modified. Findings are advisory and the rule set is intentionally narrow.
- **PR #48 — offline defensive configuration review**: merged as `e0166007ea42dafa1ef780d9094c0d3b1baf79b4`. Adds explicit scope/expiry validation and bounded checks for selected risky configuration patterns. It is a local/offline review foundation, not an active scanner or comprehensive security audit.

### Current verified boundaries

- Worker emergency-stop state is implemented and prevents new worker claims while stopped; stop semantics for already-running synchronous/external operations still need explicit operational treatment.
- Memory/knowledge context assembly and initial prompt-injection boundary regression tests exist. Source freshness and retrieval-quality evaluation remain incomplete, and the new Agent loop does not yet consume retrieved context through an end-to-end model-facing path.
- Drafts, explicit approval, durable content schedules, worker-driven dispatch, local media storage/transcoding, and opt-in Telegram text publishing exist. Media-aware Telegram publishing and Instagram Graph API publishing remain incomplete.
- Backup/restore code has CI coverage, but a restore drill on the target machine and protected backup procedures for media/key material have not been performed here.
- NEXUS static analysis and offline configuration review are foundations only. Reviewable patch proposals, dependency auditing, target-device packaging, and clean install/upgrade/rollback drills remain open.

### Recommended next delivery order

1. Finish retrieval freshness, citation-preserving context budgets, and end-to-end safety tests before connecting retrieved context to the model loop.
2. Integrate the bounded Agent loop through an authenticated, bounded execution path with auditable provider selection and explicit cancellation/timeout behavior.
3. Complete media-aware Telegram publishing with upload/size/type validation and ambiguous-outcome handling; separately design Instagram's professional Graph API and publicly reachable media delivery.
4. Verify backup/restore, encrypted workflow recovery, migrations, clean installation, and rollback on the intended Windows machine.
5. Extend NEXUS and defensive review with reviewable patch proposals, dependency/configuration coverage, and stronger scope/evidence tests.

A green CI result is not equivalent to target-machine validation or production readiness.


## Superseding integration snapshot — 2026-11-02 UTC

This snapshot supersedes the earlier snapshot above where it describes the Agent API or Telegram media publishing as incomplete. Baseline immediately before this documentation update: `efee3a5ac0f6adec5a869f4550ab2339d879cf5e`.

### Newly merged milestones

- **PR #50 — owner-declared source freshness**: merged. Knowledge sources default to `unknown`; an authenticated owner can mark them `owner_reviewed_current` or `stale`. Search results and Agent context preserve the label and review timestamp. This is not automatic URL verification.
- **PR #51 — authenticated bounded Agent run**: merged. `POST /agent/run` assembles owner-scoped memory/knowledge context, passes passages as untrusted evidence, and returns source references separately from the answer. It requires explicit local or remote provider mode, excludes the stub provider, and audits metadata without logging the goal/context/answer.
- **PR #52 — Agent provider timeout cap**: merged. The synchronous endpoint caps each provider call at 30 seconds and allows at most three turns. Worst-case provider wait is roughly 90 seconds plus local processing overhead; this is not a durable long-running workflow.
- **PR #53 — approved Telegram media publishing**: merged. Draft revisions bind owner-scoped JPEG/PNG/MP4 assets; attachment changes reset approval. The worker resolves and validates the local file immediately before dispatch. The adapter uploads via Telegram `sendPhoto`/`sendVideo`, checks caption/file bounds, and preserves ambiguous-outcome handling.
- **PR #54 — operator media library**: merged. The authenticated local dashboard can upload/list/delete media and attach assets to Telegram drafts. Deletion conflicts are surfaced rather than bypassed.
- **PR #55 — Agent run UI**: merged. The dashboard exposes the bounded Agent endpoint, explicit local/remote mode, memory/knowledge inclusion, turn/output caps, and source trust/freshness metadata.

### Current implementation boundaries

- The Agent endpoint is synchronous and exposes only the deterministic `text.echo` tool. It is not yet a durable worker-owned Agent job or multi-agent delegation system.
- Telegram media publishing requires an approved draft, configured Bot API credentials, a functioning worker cycle, and an available local asset. The code/tests use mocked HTTP; no real Telegram post was performed here.
- Instagram Graph API publishing is still incomplete. It requires professional-account/app credentials and a publicly reachable media delivery path; local file paths alone are insufficient. Do not put tokens in source code or chat.
- Freshness status is owner-declared, not independently verified. Retrieval-quality evaluation and stronger freshness checks remain open.
- Backup/restore helpers exist, but a target-machine restore drill and protected backup for media/encryption-key material remain open.
- NEXUS static analysis and offline configuration review are advisory foundations. Patch proposals, dependency auditing, and target-machine install/upgrade/rollback validation remain open.

### Next priorities

1. Add repeatable retrieval-quality and stale-source handling evaluation before broadening Agent tools.
2. Move longer Agent work to durable worker-owned jobs with persisted state, cancellation, and recovery.
3. Finish Instagram's external integration only after public media hosting and credentials are configured outside the repository.
4. Perform a real target-machine backup/restore and clean install/rollback drill.
5. Expand NEXUS findings and defensive configuration coverage with evidence-backed tests.

A green CI result is not a substitute for live provider or target-machine validation.


## Release-readiness update — 2026-11-02 UTC

This section supersedes earlier statements above where they conflict with the following merged changes. Latest relevant merged heads:
- PR #74 merged as `294329da3afb043350b22f9e4b3214456c7bf67a`; CI and Backend CI passed on PR head `78fe761f8b7c7790a99b3d1fbb07d6d0ff15d223` (Python 3.11 and 3.12 for CI). It replaces a broad exception assertion with exact HTTP 503 and stable error-detail checks for missing signed-media configuration.
- PR #75 merged as `4d83a4c59a4a688caff5fcd2fb42a34909edf14c`; CI and Backend CI passed on PR head `1b4ca24f4b4df5d1b1355add8f558c8d67dd77d8`. Public signed media delivery now verifies JPEG/PNG file signatures against stored media types before serving bytes and has mismatch regression coverage.

### Six workstreams — implementation vs. release gates

1. **Instagram/media delivery — code foundation integrated.** The dispatcher generates short-lived signed HTTPS media URLs for approved JPEG/PNG Instagram schedules. The public route binds asset UUID and expiry with HMAC, limits URLs to 15 minutes, validates media type and bytes, and fails closed when configuration is absent. Still blocked on externally verified HTTPS reachability, edge rate limiting/query-string log hygiene, authorized professional-account credentials, and a controlled end-to-end publish/reconciliation test. No live Instagram post has been performed by CI.
2. **Workflow operations/emergency stop — core behavior and regression coverage exist.** The durable stop flag blocks new worker claims and remains latched until an explicit resume. Tests cover an in-flight synchronous handler, preventing the next claim, and resuming after the stop. The stop does not magically cancel an already-running external side effect; multi-process deployment behavior and operator procedures still require target-environment validation.
3. **Retrieval and Agent context safety — bounded integration exists.** Memory and knowledge evidence are owner-scoped, carry provenance/trust/freshness labels, are bounded by per-item and total character limits, and are explicitly marked untrusted. The authenticated bounded Agent run consumes context and preserves source references. Freshness remains owner-declared rather than automatically verified; retrieval-quality evaluation and provider-backed prompt-injection acceptance remain incomplete.
4. **NEXUS developer agent — read-only foundation exists.** Python inventory/static analysis is bounded, emits file/line/rule evidence, and does not import or execute analyzed targets or modify files. Patch proposals are review-only. Coverage is intentionally narrow; broader language support, dependency analysis, and repository-scale performance validation remain open.
5. **Defensive cybersecurity lab — offline foundation exists.** Scoped, expiring authorization records and selected read-only configuration checks are implemented. This is not a comprehensive scanner or an active penetration-testing engine. Further checks must remain explicitly scoped, authorized, evidence-backed, and non-destructive.
6. **Packaging, backup/restore, release readiness — partial.** SQLite backup/restore verifies integrity and checksum, refuses destination overwrite, and has CI tests. SQLite backup does not include media assets, provider tokens, or encryption keys. A clean install/upgrade/rollback and restore drill on the intended target device, plus separately protected backup procedures for media and secret/key material, remain open.

### Release decision

**Do not label the entire project production-complete yet.** The signed-media code and relevant automated CI checks are merged, but live Instagram acceptance and target-device operational drills cannot be inferred from CI. The remaining work should proceed by closing each code-level regression with tests first, then recording external acceptance evidence without storing credentials or private media in the repository.


## Follow-up verification — 2026-11-02 UTC

The following hardening changes were merged after the release-readiness update above:

- **PR #79 — signed-media route integration test:** merged as `60e70badd453516b858e78c13624cb7897a63898`. CI passed on Python 3.11 and 3.12; the dispatcher test now requests the signed image through the actual ASGI route and checks content type, `nosniff`, `no-store`, and image signature bytes.
- **PR #80 — bounded NEXUS inventory:** merged as `0c253865807e7ab8125c4b6452ea0301b15a91fa`. CI passed after fixing the import-order lint finding. The analyzer now counts eligible Python candidates against the budget even when files are skipped for size, and reports `files_examined` separately from `files_scanned`.
- **PR #81 — offline cookie configuration checks:** merged as `d493728a7acfe223e3a9b3aa3b90b59b4232d811`. CI passed on Python 3.11 and 3.12 after correcting the test fixture's line separators. The defensive lab detects disabled Secure/HttpOnly cookie flags and does not echo configuration values.
- **PR #82 — distributable wheel asset verification:** merged as `f3fc765d54673bf551bb0cac2363f61275501b1c`. CI passed on Python 3.11 and 3.12; the pipeline builds a wheel and checks that `index.html`, `app.css`, and `app.js` are packaged.

These changes improve automated evidence for media delivery, bounded static analysis, defensive configuration review, and packaging. They do **not** close external deployment gates: public HTTPS reachability and edge controls still need deployment verification, live Instagram publishing needs a controlled authorized account test, and clean install/upgrade/restore drills still need to run on the intended target device. Do not store access tokens, signing keys, or private media in this repository.


## Packaging follow-up — 2026-11-02 UTC

- **PR #83 — status ledger synchronization:** merged. This section is now superseded by this follow-up where newer merged changes are listed.
- **PR #84 — clean wheel-install smoke test:** merged as `9c42cf9613231efe5caceb0bec41c700996bb213`. The CI pipeline creates a fresh virtual environment, installs the built wheel, imports the installed application, and requests `/health` under an isolated test database. Latest-head Backend CI and CI both passed; CI matrix coverage includes Python 3.11 and 3.12.
- This closes the *automated clean-wheel installation smoke test* gate. It does not establish a Windows target-device install/upgrade/rollback drill, restore drill, public HTTPS reachability, edge rate-limit/log-redaction configuration, or a live authorized Instagram publish/reconciliation test.

### Next acceptance gates

1. Run clean installation, upgrade, rollback, and SQLite restore on the intended Windows device; separately verify how media and secret/key material are backed up and restored.
2. Run an authorized Instagram Graph API acceptance test only after professional-account credentials are configured securely and the signed-media URL is reachable over public HTTPS.
3. Evaluate stale-source handling and prompt-injection behavior using a repeatable synthetic retrieval corpus before expanding Agent tool access.
4. Keep all production claims tied to exact-head CI plus relevant target-environment evidence.



## Follow-up verification — 2026-11-03 UTC

- **PR #90 — emergency stop regression:** merged. The worker stop switch blocks scheduled content dispatch and only resumes after an explicit operator reset; an in-flight synchronous handler is not falsely reported as cancelled.
- **PR #91 — SiaCode Stage 2 preflight:** merged after Backend CI and CI passed on Python 3.11/3.12. The optional probe is disabled by default, loopback-only, redirect-disabled, proxy-environment-independent, timeout/response-size bounded, and returns sanitized state codes. It does not launch processes, download models, create tunnels, or submit coding requests.
- **PR #93 — stop-vs-publish race gate:** merged after Backend CI and CI passed on Python 3.11/3.12. The dispatcher re-checks the durable stop switch immediately before calling a provider and returns a claimed schedule to `scheduled` if stop is latched. This narrows but cannot eliminate the race after a remote request has started; ambiguous outcomes remain quarantined.
- **PR #94 — emergency-stop API authorization tests:** merged after Backend CI and CI passed on Python 3.11/3.12. Tests cover unauthenticated access denial, persisted owner attribution through stop/resume, and blank-reason rejection.
- **PR #96 — authenticated SiaCode preflight API:** merged to `main` as `900700e7d1c63658774507946e11671685aa355d` on 2026-11-02. The authenticated route is diagnostic-only and reports that coding requests remain disabled. The PR also stabilizes a signed-media expiry regression test. The later open Draft PR #97 proposes replacing this vendor-specific preflight with shared `assistant_gateway` and `code_engine` adapters; it is not merged and must pass latest-head CI and review before integration.
- **PR #98 — Bandit static analysis:** merged as `af394c1ec0ab386cfcf584f8aeb86b91a96bd4e3`. Backend CI, CI, and the initial Bandit workflow passed on the exact PR head. The scanner is report-only (`--exit-zero`) and uses read-only workflow permissions; findings are informational until a reviewed baseline is promoted to a blocking gate.
- **PR #100 — synchronous Agent emergency-stop enforcement:** merged as `b3b176f581512b218e8c87d798d7427a3afaf166`. Backend CI and CI passed on the exact PR head. The durable stop flag is checked before model turns and after inference before tool dispatch. It cannot interrupt a provider request already in flight; provider-side effects still require reconciliation.
- **PR #97 — vendor-neutral local integration adapters:** remains open and Draft. The branch adds shared `assistant_gateway` and `code_engine` health-only adapters. Review identified ambiguous/encoded URL path handling and a non-strict response-byte limit; these were hardened with regression tests. The initial Backend CI run exposed a Ruff import-order failure; a corrected branch commit exists, but CI has not yet been confirmed on that exact head. The branch also needs synchronization with current `main` before merge.

### Current hard boundaries

- The merged SiaCode Stage 2 endpoint is a diagnostic-only health-probe foundation, not code execution integration. Its upstream response semantics still require controlled validation before any readiness claim.
- No SiaCode notebook, tunnel, remote model, or coding request has been launched by this project. Any future code-engine execution stage requires a separately reviewed request contract, authorization gate, isolated workspace, bounded output, and explicit diff review.
- Scheduled social publishing still has no general provider-side idempotency guarantee. Ambiguous provider results must remain `unknown_outcome`; do not blindly retry or claim exactly-once publication.
- Public signed-media reachability/edge controls, a live authorized Instagram publish-and-reconciliation test, and clean Windows install/upgrade/rollback/restore drills remain external acceptance gates.

## Follow-up verification — 2026-11-03 UTC (post-PR #122, #126, #127, and #97)

The following changes were merged after the previous status entry:

- **PR #97 — vendor-neutral local integration adapters:** merged as `33861df75fac77f5d04ff3da613ce231d9891a57`. Adds optional, disabled-by-default `assistant_gateway` and `code_engine` health-only adapters, shared loopback URL validation, bounded redirect-free probes, and authenticated read-only capability reporting. It does not launch OpenClaw, SiaCode, tunnels, model downloads, coding requests, or remote execution. CI, Backend CI, and Defensive Python Scan passed on the exact PR head.
- **PR #126 — Windows local launcher:** merged as `ae87bf0a98f9751995986288de6ab1a82983538f`. Adds the PowerShell start/stop scripts, local API + worker startup, persistent workflow-payload key initialization, readiness check, and Windows quick-start documentation. Windows PowerShell syntax validation, Python 3.11/3.12 CI, Backend CI, and Defensive Python Scan passed on the exact PR head.
- **PR #127 — failed-startup cleanup:** merged as `6fb131e3b2bdf65feb81e8a4db2ad3c3b497f986`. The launcher now stops the worker if API process creation fails, cleans up only the processes it started when readiness fails, and preserves the runtime record when cleanup cannot be confirmed. Windows Launcher Validation, CI, Backend CI, and Defensive Python Scan passed on the exact PR head.
- **PR #122 — continuous-agent permission isolation:** merged as `e561da2b7641fc4ba78d6e90710998b8fd78b2d1`. The model-driven development job now has read-only repository permissions and checkout does not persist Git credentials. A separate publisher job validates a bounded patch and creates a review-only PR with write permissions; the model-agent process does not receive the write token. CI, Backend CI, and Defensive Python Scan passed on the exact PR head.

### Current verification boundaries

- These merges establish repository changes and exact-head CI evidence; they do not prove a clean Windows install/start/stop/restore on the owner's laptop.
- The Windows launcher currently requires Python 3.11 and binds the application to loopback. Do not expose it directly to the public internet.
- The scheduled Continuous Development and comment-triggered OpenCode workflows were removed in PR #436. No provider-backed artifact-transfer or publisher run remains to validate. Delete the now-unused `MR_SIAVASH_HUB_AI` Actions secret; do not renew or replace it.
- third-party text inference, Telegram/Instagram publishing, OpenClaw/SiaCode execution, and remote code execution remain opt-in or unavailable until separately configured and accepted.
- Do not claim production readiness until target-device install/upgrade/rollback/backup/restore drills and required provider acceptance tests are recorded.


## Live integration baseline — 2026-11-03 UTC

This section supersedes earlier open-PR counts and integration notes above. It was checked against GitHub at main `c073f55637a36c4c4f5897d19d77d1da46bc7ce6`. Re-check live metadata and exact-head checks before every integration.

### Current open pull requests

There are 13 open PRs at this snapshot:

| PR | Area | Current disposition |
|---|---|---|
| #198 | Durable video-generation worker handoff | Candidate for focused review; Backend CI and CI were still running at snapshot time. Defensive Python Scan passed on exact head. |
| #183 | Project audit ledger | Documentation-only, but its branch is diverged from main; reconcile on a fresh main-based branch before integration. |
| #179 | NEXUS evidence-backed patch risk review | Independent capability; exact-head Backend CI, CI, and Defensive Python Scan passed. Review semantics and safety boundaries before integration. |
| #162 | Agent orchestration and knowledge integrity | Independent capability; exact-head Backend CI, CI, and Defensive Python Scan passed. Review authorization/context boundaries before integration. |
| #176 | Video analysis admission and media readiness | Candidate foundational video change; exact-head CI workflows passed. Integrate only after API/worker contract review. |
| #197 | Owner-scoped editable timeline drafts | Draft; exact-head CI failed. Do not integrate until failure is diagnosed and rerun. |
| #195 | Video edit specification and timeline | Draft; exact-head checks passed, but overlaps #177 on the same edit-spec/timeline files. Consolidate the duplicate line of work before integration. |
| #186 | Bounded cut-only MP4 render engine | Draft; CI and Video Render Integration passed on exact head. Depends on the validated timeline contract and overlaps generation/worker/migration surfaces; hold for ordered integration. |
| #157 | Bandit guidance documentation | Independent documentation change; exact-head checks passed, but branch is 17 commits behind main. Rebase/reapply the one-file change on current main before integration. |
| #177 | Validated edit specifications | Draft; exact-head checks passed, but GitHub reports non-mergeable and it overlaps #195. Treat #195/#177 as one consolidation decision, not two independent merges. |
| #178 | Semantic editing-prompt synthesis | Draft; CI passed on exact head. Depends on stable video-analysis semantics/API; hold behind foundational analysis integration. |
| #173 | Owner-scoped analysis cancellation | Draft; exact-head checks passed, but GitHub reports non-mergeable and it overlaps #176 on jobs/worker/API files. Integrate after #176 contract review. |
| #161 | Owned-asset analysis primitives | Draft; exact-head checks passed, but GitHub reports non-mergeable and its branch is behind main. Review whether its analyzer abstraction remains needed after #176 and current main. |

### Verified integration facts

- Main baseline: `c073f55637a36c4c4f5897d19d77d1da46bc7ce6`.
- PR #198 head: `7b39173eb5c525ec5f309f57576f145e8f8142ef`; compare reported 29 commits ahead and 0 behind, with 9 changed files. Backend CI and CI were in progress; Defensive Python Scan passed.
- PR #183 head: `d5cb1473d2f593e68c541821b97422933b10d2e2`; compare reported 2 ahead / 2 behind, one changed file. The branch must be reconciled before merge even though GitHub currently reports mergeable.
- PR #179 and #162 each have one unique commit ahead and are two commits behind main. Their exact-head CI workflows passed; still require code review and integration tests.
- Video PRs share API route, schema, worker, README, and migration paths. A flat merge queue is unsafe. In particular #177/#195 overlap edit-spec/timeline files; #173/#176 overlap analysis jobs/worker/API files; #186/#198 overlap API, worker, and migration paths.
- PR #197 has a failing CI result on exact head `35d68c94f8c9cc77d997f8da227e13927407f76e`; this is a hard stop until diagnosed.
- PR #157 is a single documentation file but its branch is substantially behind main; reapply its reviewed delta onto a fresh main-based branch rather than merging its stale history.

### Integration order

1. Preserve main as the only integration baseline; no direct main edits.
2. Review and integrate independent NEXUS/Agent changes (#179, #162) one at a time after checking full diffs and exact-head CI.
3. Consolidate the video-analysis contract: #176 first, then decide whether #173 and #161 contain still-needed unique behavior.
4. Resolve the single canonical edit-spec/timeline implementation from #177/#195; do not merge both blindly.
5. Integrate rendering (#186) only after its timeline contract and migration/worker interactions are stable.
6. Revisit prompt synthesis (#178) and generation worker handoff (#198) against the integrated API contract.
7. Repair #197 CI before reconsidering timeline drafts.
8. Reapply documentation-only changes (#157, #183) on current main-based branches.

### Verification limitations

This is a metadata and changed-path audit, not a code-level approval. No source-level review or combined test run is implied by the workflow results above. Checks marked passed apply only to the exact PR head and named workflow. No PR was merged, closed, force-pushed, or deleted as part of this snapshot. Windows target-device acceptance, clean install/upgrade/rollback/restore, and live external-provider acceptance remain separate gates.


## Superseding live integration snapshot — 2026-11-04 UTC

This section supersedes older repository and PR snapshots above. The detailed current readiness matrix is in [Whole-Project Readiness Audit — 2026-11-04](management/WHOLE_PROJECT_READINESS_AUDIT_2026-11-04.md).

- **Main:** `a5a1002907b3ddac2b218b84312e2fd74f2d0256`.
- **Merged integration:** PR #223, squash merge `a5a1002907b3ddac2b218b84312e2fd74f2d0256`; 25 changed files.
- **Exact PR head validated:** `fe153ac1d9a3b57e3a3e836c54e262263b36626c`.
- **Exact-head evidence:** Backend CI, CI Python 3.11/3.12, Defensive Python Scan, and real FFmpeg/FFprobe integration on Linux and Windows all passed.
- **Post-merge main checks:** all four push-triggered workflows passed on merge commit `a5a1002907b3ddac2b218b84312e2fd74f2d0256`: Backend CI run `41722222701`, CI run `41722222754`, Defensive Python Scan run `41722222735`, and Video Render Integration run `41722222736`.
- **Repository inventory:** 325 recursive tree entries (not truncated), 94 Python test files, 19 backend domain packages, seven GitHub Actions workflows, schema migrations through version 27.

### Newly integrated capabilities

- Workflow emergency-stop/resume runtime smoke coverage using separate API and worker processes.
- Centralized 32,000-character provider-request input guard; oversized agent prompts return a sanitized budget result before provider dispatch.
- Read-only media backup integrity verifier and coordinated backup/restore runbook.
- Alias-aware NEXUS Python AST checks for risky imports/calls, including `os.system` and `os.popen`; analyzer remains read-only and advisory.
- Durable owner-scoped silent cut-only video rendering, migration 27, idempotent render jobs, authenticated submit/read/cancel routes, lease-fenced worker, source media-use locks, atomic output registration and stale orphan/partial cleanup.
- Real FFmpeg/FFprobe rendering succeeded on Linux and Windows hosted CI runners.

### Current hard boundaries

- Video output is silent and hard-cut-only. Audio, transitions, captions, graphics, motion effects and AI-generated footage remain unimplemented.
- No operational AI video provider is registered.
- Hosted Windows CI is not acceptance on the owner's actual Windows device.
- The target restore drill, clean install/upgrade/rollback, live external-provider acceptance, social publishing acceptance and whole-product release gates remain open.
- Do not label the whole project complete or production-ready.

### Immediate next work

1. Verify post-merge push CI on the exact main commit.
2. Close duplicate/superseded PRs and refresh the canonical audit branch.
3. Continue scheduled-trigger/recovery semantics, Discovery source connectors, Memory/Knowledge integrity, Operator UI end-to-end coverage and controlled Content integration.
4. Keep target-device acceptance for the final integrated candidate; do not request device access before the complete product test package is ready.


### Post-merge verification update — 2026-11-04 UTC

All four push-triggered workflows on main commit `a5a1002907b3ddac2b218b84312e2fd74f2d0256` completed successfully: Backend CI, CI, Defensive Python Scan, and Video Render Integration. This is post-merge evidence on the exact main commit; target-device and whole-product acceptance gates remain open.


## Superseding live integration snapshot — 2026-11-04 (post-PR #227)

This section supersedes the earlier 2026-11-04 snapshot above. The current main SHA is
`fabafbad607aa6bcf254669a3ccb1b4b7ff9ce2d`. The current whole-project audit is
[WHOLE_PROJECT_READINESS_AUDIT_2026-11-04.md](management/WHOLE_PROJECT_READINESS_AUDIT_2026-11-04.md).

### Latest merged work

- **PR #223** — workflow stability, AI Core provider-budget guard, media integrity verification, NEXUS alias-aware analysis and durable cut-only video rendering. Merge SHA: `a5a1002907b3ddac2b218b84312e2fd74f2d0256`.
- **PR #224** — whole-project readiness audit and release baseline refresh. Documentation-only merge.
- **PR #227** — operator UI render workflow. Merge SHA: `fabafbad607aa6bcf254669a3ccb1b4b7ff9ce2d`; exact tested PR head: `643ddfaf141004f19a90067f0992d60cebce564a`.

### Exact-head and post-merge evidence

PR #227 exact head passed Backend CI, CI on Python 3.11/3.12, Defensive Python Scan, and real FFmpeg/FFprobe integration on Linux and Windows. All four push workflows on current main `fabafbad607aa6bcf254669a3ccb1b4b7ff9ce2d` also passed:
- Backend CI: `41724900988`
- CI: `41724901109`
- Defensive Python Scan: `41724900883`
- Video Render Integration: `41724900921`

### Current integrated video workflow

The RTL operator UI can now submit a render from a completed analysis with a non-empty timeline, preserve the per-analysis idempotency key during same-tab retries/reloads, refresh status, request queued/running cancellation, and download completed output through the authenticated media route. The media library also has authenticated download controls. Status refresh is manual; the pull Worker must be running separately.

### Current boundaries and next priorities

- Output remains silent and hard-cut-only; audio, transitions, captions, graphics, motion effects and AI-generated footage are not implemented.
- No operational AI video provider is registered.
- Real FFmpeg execution is verified on hosted Linux and Windows CI, not on the owner's actual device.
- Browser/UX acceptance, target Windows install/upgrade/rollback, coordinated restore drill, license/lockfile decisions, and external provider/social acceptance remain open.
- Continue worker-owned workflow execution and recovery semantics, Discovery source connectors, Memory/Knowledge integrity, defensive-lab advisory inventory, and end-to-end Operator UI coverage.
- Keep the target-device test request deferred until the complete product candidate and acceptance package are ready.

No public release or whole-product completion is claimed.


## Current hand-off snapshot — 2026-11-04 UTC

- Current main after the documentation-only readiness refresh: `320b62d0d7ef764ae7f0dbdde57a3cbaa10d3326`.
- Application/code baseline inspected for this snapshot: `92bc36e5a61446c258c558b151edcec582bf470b`; PR #233 only refreshed readiness documentation.
- Current repository inventory at the application baseline: 326 recursive tree entries, 94 Python test files, and 7 GitHub Actions workflow definitions.
- PR #231 is merged (operator UI DOM selector integrity regression test).
- PR #232 remains open/draft. Its six exact-head check runs completed successfully, but the combined commit-status endpoint reported pending at the time of review. Do not merge until that status is reconciled and the patch is reviewed.
- PR #233 is merged (documentation-only readiness audit refresh).
- Product acceptance remains incomplete: browser/UX acceptance, Windows target-device acceptance, controlled real provider/social-account tests, and a clean-destination database/media/key restore drill have not been established by hosted CI.


## Superseding current-main hand-off — 2026-11-04 UTC

This entry supersedes the earlier live-PR snapshot above. Current main at the start of this documentation refresh is `c5cd2ad114aa558099be6a2cf966df4564031853`.

### Newly merged and verified

- **PR #235** — bounded worker-cycle content dispatch. A worker cycle is covered by regression tests to execute at most one queued task and dispatch at most one due content schedule; later cycles continue the queue without duplicate dispatch. Merge commit: `d69c02544ec84fd40aa3871dd7c04300cf028f3f`.
- **PR #237** — clean-destination database and media recovery integration test. It restores a temporary SQLite backup, copies the associated media directory, validates metadata and SHA-256, then verifies owner login, listing, and authenticated byte-for-byte download in a fresh app. Merge commit: `57240dad59c50b7100554f57c5d7adc784428e75`. This is synthetic CI evidence, not a production restore or key-management drill.
- **PR #239** — historically added bounded handling for a free-tier quota response in the scheduled OpenCode workflow. That workflow was subsequently retired in PR #436; no provider quota or credential action remains.

PR #232 was closed without merging; PR #235 is the current-main replacement for its bounded worker-cycle regression coverage. PRs #236 and #238 were closed as superseded attempts; their final verified work is represented by PR #237 and PR #239 respectively.

All six exact-head checks on PR #239 completed successfully: Backend CI, Python 3.11 CI, Python 3.12 CI, Defensive Python Scan, and real FFmpeg/FFprobe integration on Linux and Windows. The four push-triggered workflows on main commit `c5cd2ad114aa558099be6a2cf966df4564031853` were still running at the time of this snapshot; do not report post-merge main CI as green until those runs finish.

### Current acceptance boundary

The synthetic recovery test improves automated confidence but does not establish a real target-machine restore, protected encryption-key recovery, or operational recovery of production data. Target-device/browser acceptance, real external-provider/social-account acceptance, packaging/install/upgrade/rollback drills, and whole-product release approval remain open. No production-ready or whole-project-complete claim is made.


## Follow-up verification — 2026-11-04 UTC

This is the newest status snapshot at main commit `c454f4d27c62f76ff6bef08362745eef3096eb2e`; it supersedes earlier snapshots in this file.

### Additional merged work

- **PR #241** — NEXUS static-analysis rule `PY106` detects literal `verify=False` in common Requests calls, including straightforward module and imported-function aliases. Merge commit: `0ae2a4fa3702d87d1d2f1dc1f3db7c811eb29f1f`.
- **PR #242** — extends `PY106` to common HTTPX request helpers and `Client`/`AsyncClient` constructors, with module/class alias tests and a `verify=True` negative control. Merge commit: `d54ed95c83aab1ab7a97278005c8ceee34b89036`.
- **PR #243** — strengthens the MCP/ToolRegistry/PolicyEngine boundary tests: an external-side-effect denial and missing permission grant both prove that the tool handler is never called. Merge commit: `c454f4d27c62f76ff6bef08362745eef3096eb2e`.

All exact-head checks passed for PR #242 and PR #243, including Backend CI, Python 3.11/3.12 CI, Defensive Python Scan, and Linux/Windows FFmpeg integration.

The push-triggered main workflows for `c454f4d27c62f76ff6bef08362745eef3096eb2e` were queued or running when this snapshot was prepared. Verify their final conclusions before claiming post-merge main CI is green.

### Security analysis limitations

PY106 is a targeted AST heuristic for literal `verify=False` on supported Requests and HTTPX call forms. It does not cover dynamic values, all HTTP clients, nested configuration patterns, or every TLS weakness. Findings are advisory; no finding is not proof of security.

### Remaining acceptance work

Continue coordinated integration across provider routing, workflow execution/recovery, content automation, video generation/rendering, MCP lifecycle, package/release validation and discovery provenance. Real target-device acceptance, live external-account verification, production restore/key-recovery drills, and install/upgrade/rollback testing remain open. No whole-product completion or production-readiness claim is made.


## Provider-router consistency follow-up — 2026-11-04 UTC

Latest main snapshot: `a7f4fb453da7ba70d3c20c684011f7076f12235b`.

- **PR #245** (`a7f4fb453da7ba70d3c20c684011f7076f12235b`) hardens AI Core provider registration: duplicate provider/model descriptors are rejected instead of silently overwriting router metadata. Provider registration preflights the router key before mutating the adapter registry, preventing a partial cross-registry state. Regression tests cover both preservation of the original descriptor and absence of a partially registered adapter.
- All six exact-head PR #245 checks passed: Backend CI, Python 3.11/3.12 CI, Defensive Python Scan, and Linux/Windows FFmpeg integration.
- Main push-triggered workflows for `a7f4fb453da7ba70d3c20c684011f7076f12235b` must still be checked independently; PR checks are not a substitute for post-merge main verification.

The project readiness boundary is unchanged: real target-device acceptance, external-account publishing, production restore/key recovery, package install/upgrade/rollback, full video-editor capabilities, and complete connector lifecycle acceptance remain open. No production-ready or whole-project-complete claim is made.



## Cross-system integration follow-up — 2026-11-04 UTC

Latest main commit: `1c531a97749b26ff05c9efde3944169e1a39b761`.

### Merged changes

- **PR #246** — refreshed readiness documentation after the NEXUS/MCP integration batch.
- **PR #247** (merge commit `77bf47a04931f6e629fa8f89400f329c1df462b6`) — introduced `ProviderContractError` and enforced response-type plus provider/model identity validation at the shared ModelRouter boundary. Invalid or misattributed adapter responses are rejected before reaching API consumers.
- **PR #248** (merge commit `80253101dee781d698aad1b9cce7451ea1c857f7`) — fenced content-publication confirmation against concurrent worker recovery. A late provider receipt cannot overwrite a durable `unknown_outcome` state or emit a false publication-success audit event.
- **PR #249** (merge commit `1c531a97749b26ff05c9efde3944169e1a39b761`) — routed the legacy remote text-generation endpoint through the shared remote-only ModelRouter, closing the direct-adapter bypass while excluding Stub and local Ollama fallback.

All six exact-head checks passed for PRs #247, #248 and #249: Backend CI, Python 3.11/3.12 CI, Defensive Python Scan, and Linux/Windows FFmpeg integration. PR #246 documentation checks also passed.

All four push-triggered workflows on main commit `1c531a97749b26ff05c9efde3944169e1a39b761` completed successfully: Backend CI, Python 3.11/3.12 CI, Defensive Python Scan, and Linux/Windows FFmpeg integration.

### Remaining acceptance boundary

The new tests strengthen provider response provenance and content-publication state integrity; they do not guarantee remote provider uptime, exactly-once delivery on providers without idempotency support, or successful live social-account publishing. Production restore/key-recovery drills, target-device/browser acceptance, package install/upgrade/rollback, full video-editor capabilities and connector permission lifecycle acceptance remain open. No production-ready or whole-project-complete claim is made.


## Follow-up verification — 2026-11-04 UTC, main `3134fb50d47f7ab87934971a27e2ba90c85263d8`

This snapshot supersedes earlier live-main statements in this status ledger. Historical snapshots remain as records of their respective commits.

### Latest merged hardening

- **PR #255** — workflow task-linked mutation lease validation.
- **PR #256** — Provider Router / Registry lifecycle hardening.
- **PR #258** — Agent Core / Tool Registry / MCP policy lifecycle revalidation.
- **PR #260** — preserve MCP `approval_required` outcomes.
- **PR #261** — shared provider-health contract validation.
- **PR #262** — Ollama malformed payload handling and metadata sanitization.
- **PR #263** — immutable validated Vision image batches.
- **PR #264** — persist unexpected video-provider submission outcomes as ambiguous, non-retryable results.

PR #264 merged as `3134fb50d47f7ab87934971a27e2ba90c85263d8`. Its exact PR head passed all six checks. All four post-merge workflows on the current main commit also completed successfully: Backend CI (`41809518846`), Python 3.11/3.12 CI (`41809518853`), Defensive Python Scan (`41809519071`), and real FFmpeg MP4 integration on Linux/Windows (`41809518974`).

### Verified integration gaps and next order

1. **Storyboard draft → prompt composition:** versioned owner-scoped beats are persisted, but prompt composition still derives its beats directly from analysis and does not consume a saved draft. The draft contains generation instructions and natural-language transitions, so it must not be passed directly to the cut-only FFmpeg renderer. Next: validate draft owner + analysis + asset + version, use its beats as a prompt-composition override, return draft ID/version with the prompt, then expose create/edit/save/compose in the UI. Composition must not call a provider.
2. **Video-generation reconciliation:** no generation provider adapter is registered. PR #266 is an open provider-contract proposal for read-only lookup by idempotency key; it is not merged and does not yet provide an end-to-end reconciliation endpoint or active provider.
3. **Renderer capabilities:** local rendering currently produces silent hard-cut MP4. Audio tracks, transitions, captions, graphics and motion effects remain unimplemented.
4. **Cross-system acceptance:** target-device/browser checks, external social-account publishing, protected encryption-key recovery, real database/media restore, and clean install/upgrade/rollback remain manual release gates.

### Current evidence boundary

The latest main inventory at this commit contains 327 recursive tree entries, 94 Python test files across `tests/` and `backend/tests/`, 19 backend package domains and 7 GitHub Actions workflows. These counts and green CI do not establish whole-product completion or production readiness.


## Follow-up after PR #266 — 2026-11-04 UTC, main `cbc12c0adf3994f28c49ca3ac4ff447ec029bade`

PR #266 merged as `cbc12c0adf3994f28c49ca3ac4ff447ec029bade`. Its exact PR head passed all six required checks. The video-generation adapter protocol now requires a read-only `find_by_idempotency_key` lookup, and the registry rejects adapters that omit it. This is a contract and registration gate only: there is still no registered provider, no reconciliation worker/API that calls the lookup, and no status-poll/output-finalization path for a recovered job. The next generation milestone must implement and test the owner-scoped non-replayable reconciliation flow before any adapter is enabled.

Post-merge CI for this new main commit was queued at the time of this note and must be rechecked before treating the commit as fully validated.

## Video storyboard and immutable render integration — 2026-11-04 UTC

This is the newest video-workstream hand-off and supersedes the earlier storyboard gap recorded above. The current `main` baseline is `589a038d09271ddbcb2e8c07fbbce983499c882a`.

### Merged into main

- **PR #271** (merge commit `e9055ebef035931a36b277b3ce5d76ee58ff60c4`) connects owner-scoped saved storyboard drafts to prompt composition and the dashboard editor. It validates draft identity, analysis/asset membership, exact version, beat intervals and source timestamp bounds. Composition remains text-only and returns `execution=not_started`; it does not invoke a provider or renderer.
- **PR #272** (merge commit `45c06562999a46861f89fca1438bd5b7776a850a`) adds the immutable renderer-timeline snapshot value object with canonical JSON, SHA-256 integrity, owner/analysis/draft-revision identity and revision-sensitive idempotency.
- Main commit `589a038d09271ddbcb2e8c07fbbce983499c882a` adds the architecture contract clarifying that storyboard beats and cut-only renderer timelines are distinct representations.

### PR #273 — merged

[PR #273](https://github.com/MRSIAVASSHIRBOT/MR_SIAVASH_HUB_AI/pull/273) was merged as `144b870e54713b3f80196c986b4864d547e301df`. Main now contains migrations 28–29, renderer-timeline/hash persistence on drafts, immutable owner-scoped snapshot rows, measured source-duration validation, atomic snapshot + render-task + render-record + idempotency persistence, and Worker consumption of immutable snapshots with fail-closed behavior and no fallback to mutable analysis data.

The merged PR head was `a01f865e907086cdc767a774fb1f2d94b8c57229`; its recorded Python 3.11/3.12, Defensive Python Scan, and Linux/Windows FFmpeg checks passed. A subsequent review found a narrower race: if a snapshot already existed and the draft advanced before a *new* render submission, the existing-snapshot replay path could bypass the current-draft fence. This does not invalidate already accepted immutable renders or their legitimate idempotent retries, but it must be fixed for new submissions.

### PR #276 — merged stale-revision fence

PR #276 merged as `6e0a41a52c5a9f28faaa9b5ffb15b971e1bbffd2`. New snapshot-backed render submissions now validate the exact current owner-scoped draft revision inside the same SQLite transaction, whether the caller supplies a snapshot value or an existing `snapshot_id`. The check binds owner, analysis, asset membership, version, canonical timeline and SHA-256. An already accepted render can still be replayed with its original idempotency key after the draft advances; a new render from that stale snapshot is rejected.

All exact-head checks on PR #276 passed: Python 3.11/3.12, Backend CI, Defensive Python Scan and Linux/Windows FFmpeg integration. Post-merge checks on main were still running when this update was prepared: Defensive Python Scan and Linux/Windows FFmpeg had passed; Python 3.11, Python 3.12 and the aggregate test workflow were in progress.

### Remaining video acceptance work

1. Add an operator-dashboard action to submit a render from a saved renderer-compatible timeline, with explicit draft-version display and idempotency behavior.
2. Define and implement snapshot retention/cleanup policy, including safe deletion rules and operational tests.
3. Validate the complete workflow on the target Windows device with representative source media, draft edits, accepted idempotent replay, stale-snapshot rejection, cancellation, output registration and download.
4. Preserve the explicit renderer boundary: local output remains silent and hard-cut-only. Audio, captions, graphics, motion effects, non-cut transitions and AI-generated footage are separate future capabilities.
5. Keep video-generation provider reconciliation separate from local FFmpeg rendering. PR #266 supplies only the read-only adapter lookup contract; no provider is registered and no end-to-end reconciliation worker is available.

Green CI is not target-device acceptance or production readiness. Whole-product install/upgrade/rollback, database/media/key restore, external-account verification and provider acceptance remain independent release gates.



## Post-merge stale snapshot submission fence — 2026-11-04 UTC

Current main: `6e0a41a52c5a9f28faaa9b5ffb15b971e1bbffd2`. PR #273 and PR #276 are merged. The current-draft fence now applies to new render submissions through both snapshot-value and snapshot-ID paths, while accepted idempotent retries and read-only historical snapshot lookup remain supported. PR #276 exact-head checks passed; post-merge Python 3.11/3.12 and aggregate test workflows were still running when this note was refreshed.

## Current cross-domain hand-off — 2026-11-04 UTC

**Main baseline at review start:** `a87855fbaa27e4d9406656937aad5eb329280280`. Earlier sections are historical snapshots and should not be read as current state where this section supersedes them.

### Recent mainline integration
- PR #273 introduced durable immutable renderer snapshots, atomic render acceptance and snapshot-backed Worker execution.
- PR #276 closed stale-snapshot submission races for both snapshot-value and snapshot-ID requests while preserving accepted idempotent replay.
- The current main commit also includes the Agent policy-outcome preservation fix. The recorded check set includes successful Python 3.11/3.12, scan, aggregate test and Linux/Windows FFmpeg runs, alongside cancelled duplicate runs. Successful exact-head checks are the evidence; cancelled duplicates are not failures.

### PR #289 — operator-facing saved storyboard prepare-and-render (merged)
PR #289 merged to main as `13c8acebc9c32d36b4d4f3de3f8e08d1866cb959`. It adds an owner-scoped preparation endpoint that validates the completed analysis Edit Specification, restricts the source to the selected draft asset, applies the saved duration/aspect ratio, derives a deterministic cut-only renderer timeline, and persists it with optimistic version fencing. The dashboard exposes an explicit preparation action and submits the prepared revision through the immutable snapshot render route. It also scopes render status, retry identity and cancellation to the exact analysis/draft revision. Preparation does not invoke FFmpeg, a generation provider or publishing. Storyboard beat instructions and transition labels remain prompt/editorial metadata and do not directly define MP4 cuts.

The merged change has route, persistence, UI and concurrency regression coverage. All six exact-head checks on PR head `df11bfed5b59797ce5d82a5f5a87364761732a3d` passed: Python 3.11/3.12, Backend CI, Defensive Python Scan, aggregate CI and Linux/Windows FFmpeg integration. Post-merge checks on main commit `13c8acebc9c32d36b4d4f3de3f8e08d1866cb959` were still running when this note was refreshed.

### PR #290 — merged durable Agent approval-required regression
PR #290 merged as `592e98221014ca897edfb09285830a6a3b990a76`. The test-only regression verifies that a high-risk external tool proposed by the model returns `approval_required` through the durable worker result, while the handler and tool-call counters remain untouched without explicit approval. All six exact-head checks passed, including Python 3.11/3.12, scan, aggregate tests and Linux/Windows FFmpeg integration. It does not introduce an approval UI or grant tool permissions. Post-merge checks on main were still running at this update.

### Remaining acceptance gates
- Snapshot retention/cleanup policy and tests for safe deletion of snapshots referenced by renders.
- Target Windows device acceptance with real media, prepared draft, render status, cancellation, retry and download.
- Audio, captions, graphics, motion effects, non-cut transitions and AI-generated footage remain unimplemented; local output remains silent and hard-cut-only.
- Provider reconciliation is separate from local FFmpeg rendering; no external generation provider is registered.
- Clean install/upgrade/rollback, database/media/key restore and external-account verification remain independent release gates.

## Video-generation outcome reconciliation proposal — 2026-11-04 UTC

Current main baseline at this review: `6cabc1e81dfc97c704c3ecd1506553a481bedb69`. PR #293 is open and not merged. Its branch `feat/video-generation-outcome-reconciliation-clean` is 36 commits ahead of and 0 behind current main at the latest comparison; this is a branch comparison, not a merge-readiness verdict.

The proposal adds owner-scoped generation status and explicit reconciliation endpoints. For ambiguous submissions, the worker looks up the original generation idempotency key and never calls `submit` again. When a provider job is discovered, the worker persists its opaque reference under the active lease, polls status and streams a successful result through bounded private storage before independent media probing and atomic asset registration. Provider job IDs remain excluded from the public status and task-result contracts. The original encrypted request is retained while the remote outcome remains ambiguous and purged only on terminal failure/cancellation or successful output finalization.

Exact-head CI is currently queued, not passed. A further operational merge gate is durable per-generation reconciliation throttling: repeated explicit lookup/status attempts need an atomic attempt budget and cooldown/backoff, with HTTP 429 and a stable `Retry-After` contract. Tests must cover concurrent requests, cooldown expiry, lookup miss, provider error and owner isolation. The provider registry remains empty by default; this PR does not activate a real provider. No production-readiness or external-provider acceptance is claimed.


## 24. Latest mainline, PR, and Cloudflare verification — 2026-11-06 UTC

This section supersedes the earlier main SHA, PR #303 state, exact-head CI, and live Worker observations above wherever they differ. Re-fetch exact refs before any merge or release decision.

### Verified mainline

- Current `main`: `e914652f2846758d6d6bf1fb18bef4a033c9be59`.
- PR #303 merged as `e914652f2846758d6d6bf1fb18bef4a033c9be59`. It adds allow-listed audit events for unregistered tool names and invalid registered-tool inputs, without persisting request payloads or validation details.
- Exact PR #303 head `e28a3fb20438e36de9e8ebf8b9a6d72d1047c35d` passed CI, Backend CI, Defensive Python Scan, and both Linux and Windows FFmpeg integration jobs. The first Windows attempt failed during Chocolatey package installation with HTTP 504; the targeted rerun completed successfully. The merged commit's post-merge workflow result was not returned by the PR-only commit-run lookup and is not claimed here.
- Main also includes the isolated Cloudflare Workers gateway source (PR #301), owner-scoped expiring `cloudflare.read` grants and audit foundation (PR #302), and the Hub-side typed read-only client and permission-gated tool registration (PR #300).

### PR #294 — optional Moonshot Kimi K3.1 Pro

- Open and draft. Current head: `2cf2ef554cdb5fc883b7c42298008508f1b8a1d9`; original base: `68f546747c1eeaaa9d15d05a2a98c38aa746e6cb`; comparison with current main: 4 commits ahead, 1 behind.
- The intermediate head `0803e5b6f38ae92a3df3c94cd5e5885bf3ec4113` failed 79 tests on each of Python 3.11 and 3.12 because five existing Cloudflare gateway settings had been removed from `Settings`. The current branch restores the Cloudflare settings and environment example; the correction is visible in the latest branch tree.
- Exact-head Defensive Python Scan passed. Backend CI and Video Render Integration were in progress and CI was in progress at the latest observation. No full exact-head pass is claimed.
- Before merge, synchronize with the new main commit `e914652f2846758d6d6bf1fb18bef4a033c9be59`, preserve the Cloudflare settings, and rerun all required workflows on the resulting exact SHA.
- Kimi remains disabled by default. Mocked tests do not establish live Moonshot availability, data retention, billing behavior, model quality, or provider-side spending controls. The SQLite sliding-window limit coordinates only processes sharing the same database file and is not a monetary budget.

### PR #296 — documentation synchronization

- Open and draft; latest observed head `22c25524100fc9f2a39fdcc6b4551be0bd4aba76`; comparison with current main: 24 commits ahead, 1 behind.
- Exact-head Defensive Python Scan passed; Backend CI and Video Render Integration were in progress; aggregate CI was pending at the latest observation.
- This documentation branch contains repeated historical checkpoint additions. Do not merge until it is synchronized with current main, the two-file diff is reviewed for stale/conflicting status, and all required workflows pass on the final exact head.

### PR #297 — scheduled development proposal

- Open; head `01ba94f29ad0ddf9f1db7af0b0957bebf8d2abdf`; 1 commit ahead and 4 behind current main.
- All four workflow groups report `action_required`. This is not a test pass and not a code-test failure. Do not bypass the repository's required workflow authorization. Rebase/synchronize and obtain authorized workflow approval before considering the small payload-envelope formatting/test change.

### PR #306 — superseded configuration fix

- Closed without merge after the Kimi branch itself restored the Cloudflare settings and environment example.
- No Cloudflare account resources or production settings were changed by the temporary branch.

### Cloudflare live-state acceptance — read-only inspection

- The connected account lists Workers `gahop` and `mr-siavash-ai-gateway`.
- `gahop` still owns the observed `gshop11.ir/api/*` route. The `mr-siavash-ai-gateway` Worker has no route in the inspected Worker inventory.
- The gateway Worker's deployed settings expose only `ALLOWED_ORIGINS` (plain-text) and `DB` (D1) bindings. The source-controlled gateway requires a separate gateway-auth secret and Cloudflare provider/account/zone configuration; those required binding names were not present in the observed binding list.
- The live script-content inspection did not match the source contract markers for the fixed Cloudflare API origin and read-only tool routes. The similarly named deployed Worker is therefore **not accepted as a verified deployment** of `cloudflare/gateway/src/index.js`.
- No secret values were read. No Worker code, bindings, secrets, routes, D1 resources, or production settings were modified.

### Required next actions

1. Synchronize PR #294 with current main and validate the exact resulting head; preserve the Cloudflare settings and keep Kimi disabled by default.
2. Keep the Hub Cloudflare integration disabled until a dedicated isolated staging Worker matches the source contract, has the required secret/variable bindings, and passes authenticated read-only acceptance tests.
3. Keep `gahop`, `gshop11.ir/api/*`, and production resources untouched during staging verification.
4. Resolve PR #297's `action_required` state through the authorized GitHub workflow approval path.
5. Reconcile PR #296's accumulated documentation history with current main before merge.

Workflow evidence is commit-specific. Pending, queued, in-progress, action_required, cancelled, and failed runs are not passes. This checkpoint is not a production-readiness or whole-project-completion declaration.


## 25. Post-synchronization CI and documentation queue refresh — 2026-11-06 UTC

This section supersedes the PR #294 and PR #296 state in section 24 where they differ.

- Main remains `e914652f2846758d6d6bf1fb18bef4a033c9be59`.
- PR #303 is merged in main. Its exact PR head passed all four required workflow groups, including both Linux and Windows FFmpeg integration.
- PR #294 current head is `115dfa8232ad7ac495b6a9bd5cb333b215743aeb`, 7 commits ahead / 0 behind main. The exact-head Defensive Python Scan passed; Backend CI was in progress; CI and Video Render Integration were pending at the latest observation. This head removes the redundant Kimi Vision health-probe round trip and adds a regression assertion for a single POST. No full pass is claimed.
- PR #296 was closed as superseded by the cleaner documentation-only PR #307. Its accumulated history is preserved in the replacement branch; the new branch was created from current main.
- PR #307's prior head `4b49aede8e8d7bae3d2ec00d17015a2eb5ebe5a7` passed all four workflow groups. The present documentation refresh creates a new head and requires its own exact-head checks.
- PR #297 remains 1 commit ahead / 4 behind main with all four workflow groups reporting `action_required`; no authorization bypass is permitted.
- PR #306 was closed without merge because the Kimi branch restored the Cloudflare settings and environment example independently.

No Cloudflare resources, production routes, bindings, secrets, or D1 data were modified. Workflow conclusions remain SHA-specific. This is not a production-readiness or whole-project-completion declaration.


## 26. Shared-account security and repository-governance follow-up — 2026-11-06 UTC

This section records read-only findings from the shared Cloudflare account and GitHub repository controls. No secrets or credential values were read.

### Existing GSHOP Worker security finding — tracked in issue #298

- A read-only settings inspection of production Worker `gahop` confirmed `DIGIPAY_CLIENT_ID`, `DIGIPAY_CLIENT_SECRET`, `DIGIPAY_PASSWORD`, and `DIGIPAY_USERNAME` are configured as `plain_text` bindings.
- `ADMIN_PASSWORD` and `TELEGRAM_BOT_TOKEN` are configured as `secret_text`.
- `ALLOWED_ORIGINS` is a plain-text binding; its value was not read.
- Worker observability and persistent invocation logs are enabled; query-string redaction is disabled and traces are disabled.
- The finding and owner-dependent remediation were recorded in issue #298. Credential rotation requires new values from the payment provider, and the exact frontend/admin origin allowlist requires owner confirmation.
- No credential values were retrieved, and no Worker settings, payment flows, routes, or production resources were modified.

### GitHub main protection — tracked in issue #304

- A read-only repository rulesets listing returned an empty array.
- The detailed branch-protection endpoint returned HTTP 403 (`Resource not accessible by integration`), so the current detailed protection configuration could not be independently read through this connection.
- Earlier repository metadata reported `protected: false`; no branch-protection or ruleset settings were changed in this session.
- An authorized repository owner/admin must verify and configure PR-required changes, exact-head required checks, force-push/deletion restrictions, and review-thread resolution with an owner-compatible approval policy.

### Hub gateway live acceptance — tracked in issue #305

The similarly named `mr-siavash-ai-gateway` Worker remains unaccepted as a deployment of the source-controlled gateway. It has no observed route, its settings do not match the source contract, and the deployed script did not match the expected fixed API-origin/read-only-route markers. The existing `gahop` route remains unchanged.

### Safety boundary

Do not rotate payment credentials, change CORS, modify logging settings, alter branch protection, deploy a staging Worker, or change production routes without the required owner confirmation and a reviewed rollback/acceptance plan. Issues #298, #304, and #305 remain open and are tracked separately from the code-only Hub PRs.


## 27. Kimi merge and GSHOP security remediation — 2026-11-06 UTC

This section supersedes the open-PR states in sections 24–26 where they differ.

### MR_SIAVASH_HUB_AI mainline

- Current `main`: `8ca7888f1b12fabe1083c2c0f45dd5739e082985`.
- PR #294 (optional Kimi K3.1 Pro provider) merged as `8ca7888f1b12fabe1083c2c0f45dd5739e082985`.
- Exact PR head `115dfa8232ad7ac495b6a9bd5cb333b215743aeb` passed CI (Python 3.11/3.12), Backend CI, Defensive Python Scan, and Linux/Windows Video Render Integration before merge.
- The provider remains disabled by default. The merge does not establish live Moonshot availability, billing, retention, external data-sharing acceptance, or provider-side budget controls.
- PR #303's tool invocation failure-audit events remain merged in main at `e914652f2846758d6d6bf1fb18bef4a033c9be59`.

### GSHOP mainline

- GSHOP PR #3 merged as `116e6336134c9acea8bd121803ce65a364f65b99`.
- Exact-head Quality checks run #31 passed JavaScript syntax validation and the complete automated Node test suite.
- The merged code rejects wildcard CORS grants, keeps same-origin as the fallback when no exact origin remains, bounds Digipay API response bodies, validates token response shape, and prevents raw Digipay provider error bodies/messages from being returned or persisted.
- No Cloudflare Worker settings, secret bindings, routes, D1 resources, or production deployment were changed.

### Remaining operational/security blockers

1. **DigiPay credentials:** live `gahop` still has `DIGIPAY_CLIENT_ID`, `DIGIPAY_CLIENT_SECRET`, `DIGIPAY_USERNAME`, and `DIGIPAY_PASSWORD` as `plain_text` bindings. Rotate/reissue them with the payment provider, then store new values as `secret_text` through an owner-approved Cloudflare operation.
2. **CORS:** confirm the exact frontend/admin origins before changing the live `ALLOWED_ORIGINS` binding. The GSHOP code now rejects wildcard grants; production configuration rollout remains separate.
3. **Worker logs:** live query-string redaction is disabled while persistent invocation logs are enabled. Review and approve the logging policy before changing production observability.
4. **Hub Cloudflare gateway:** `mr-siavash-ai-gateway` still does not match the source-controlled gateway contract and has no observed route. Keep it unaccepted until a dedicated staging Worker is configured and verified.
5. **GitHub governance:** repository rulesets listing is empty; detailed branch-protection read returned 403. An authorized owner/admin must verify and configure main protection. No rules were changed.
6. **PR #297:** remains blocked on `action_required` workflow authorization; do not bypass that gate.

The existing `gahop` route `gshop11.ir/api/*`, its D1 database, and payment configuration were not modified. No live credentials were read. Production credential rotation, CORS changes, Worker deployment, and branch-protection changes remain approval-gated.


## 27. Current verified integration and release snapshot — 2026-11-08 UTC

This section supersedes earlier mainline, PR, Cloudflare, and release observations in this ledger wherever they differ. All repository claims below are tied to the stated commit or exact PR head.

### Current mainline

- Current `main`: `95530b98584f80161268155600b088572da295d2`.
- PR #323 merged as `9e3f43e027a65672a12599fa20b999f443eec9a1`. It validates the requested GitHub repository identity against the returned upstream `full_name`, rejects malformed status flags, and bounds untrusted metadata text before registry persistence/evaluation. All exact-head PR workflow groups passed.
- PR #326 merged as `95530b98584f80161268155600b088572da295d2`. It exposes the existing synthetic, local-only Knowledge retrieval benchmark through an authenticated API; adds Windows clean-wheel build/install smoke coverage for Python 3.11 and 3.12; adds encoded workflow-key loading coverage; and pins checkout/setup-python/upload-artifact to verified immutable Node 24 action SHAs.
- PR #326 exact-head acceptance passed: CI, Backend CI, Defensive Python Scan, Video Render Integration on Linux and Windows, Windows Launcher Validation, and both Windows wheel smoke cells (Python 3.11 and 3.12). These hosted checks do not replace real-device acceptance.
- All four post-merge main workflows passed on exact commit `95530b98584f80161268155600b088572da295d2`: CI `42496885622`, Backend CI `42496885628`, Defensive Python Scan `42496885624`, and Video Render Integration `42496885716`.

### PR reconciliation

- The useful GitHub discovery hardening from stale PR #313 was rebuilt on current main and merged as PR #323.
- The useful Knowledge evaluation endpoint from stale PR #321, the encoded-key test from PR #297, and the Windows wheel/action-pin work from PR #314 were rebuilt on current main and merged as PR #326.
- PRs #297, #309, #312, #313, #314, #321, #324, and #325 were closed only after their useful changes were merged or their stale documentation/architecture snapshots were confirmed superseded.
- Historical note: Draft PR #315 and the related scheduled-development security work were superseded by the retirement of the provider-backed workflow in PR #436. No privileged scheduled publisher remains to dispatch.

### Cloudflare live-state acceptance — read-only inspection

The authenticated Cloudflare inventory returned three Workers: `gahop`, `mr-siavash-ai-gateway`, and `mr-siavash-ai-gateway-preview`; and three D1 databases: `gshop-db`, `mr-siavash-ai-prod`, and `mr-siavash-ai-preview`.

- The only observed custom-zone route for `gshop11.ir` remains `gshop11.ir/api/* -> gahop`. No Hub gateway route was observed.
- The live `mr-siavash-ai-gateway` settings expose binding metadata for `ADMIN_EMAILS`, `ALLOWED_ORIGINS`, `CF_ACCESS_AUD`, `CF_ACCESS_TEAM_DOMAIN`, and `DB`; the required Stage 1 Hub gateway bindings `CF_ACCOUNT_ID`, `CF_ZONE_ID`, `CF_API_TOKEN`, and `GATEWAY_AUTH_TOKEN` were not present in the projected binding list.
- The preview Worker exposes `ALLOWED_ORIGINS`, `DB`, and `SUPPORT_RETENTION_DAYS`; it is not accepted as the Hub gateway.
- The `gahop` Worker currently reports `DIGIPAY_CLIENT_SECRET` and `DIGIPAY_PASSWORD` as `secret_text`, while `DIGIPAY_CLIENT_ID` and `DIGIPAY_USERNAME` are `plain_text`. `ALLOWED_ORIGINS` is also `plain_text`. No binding values were requested, displayed, or changed.
- No Worker, route, D1 database, secret, or production setting was modified during this inspection. Issue #305 remains open for isolated staging acceptance; Issue #298 remains open for owner-confirmed credential and CORS remediation.

### Remaining hard release gates

1. Retire the scheduled provider-backed publisher and remove its credential dependency; completed and merged in PR #436.
2. Configure and verify repository protection for `main`. The available GitHub integration returned 403 for the branch-protection read endpoint; protection is not claimed as enabled. Issues #304 and #149 remain open.
3. Complete dedicated Cloudflare staging acceptance; do not attach the Hub gateway to the GShop production route or mutate `gahop`/ `gshop-db`.
4. Complete the owner-approved payment credential review and exact CORS-origin decision for `gahop`.
5. Register and test an explicitly selected Video Generation provider. The current generation registry remains empty by default and correctly returns `provider_unavailable`.
6. Complete the target Windows device acceptance, coordinated database/media/key backup and restore drill, clean upgrade/rollback, dependency lock, license decision, and external provider/social-account acceptance.

This snapshot does not declare the product release-ready. Merge and hosted CI evidence are not deployment or production acceptance evidence.


## 28. Central Project Control Center — verified implementation snapshot, 2026-11-08

This section supersedes earlier control-center status notes above.

- Current main: `0d03a7aac686255e6f895028ac4db1cae67dc2f4`.
- PR #310 merged as `2798200cc3f4fe0b96876e62ab18ccbe2c67b9dd`: owner-authenticated, read-only registry for the three explicitly enrolled projects; public GitHub repository metadata, default-branch commit, open PR sample, and default-branch CI observation; bounded cache and truthful unknown states.
- PR #329 merged as `0d03a7aac686255e6f895028ac4db1cae67dc2f4`: the Hub project card now uses the existing local `/health` and `/ready` functions to report liveness, database readiness, schema version, worker state, and heartbeat age. A ready database without a live worker is degraded, never healthy; unavailable readiness is failing/unknown with a sanitized reason code.
- PR #329 exact-head verification passed: Backend CI, CI (Python 3.11 and 3.12, including Windows wheel smoke), Defensive Python Scan, and Linux/Windows Video Render Integration.
- The registry remains owner-authenticated and read-only. The optional registry request is bounded and does not block the core operator overview.
- MR_SIAVASH_AI and Gshop still show runtime `unknown` and infrastructure `not_configured`. The Hub already contains a typed Cloudflare gateway client and fixed-route Stage 1 Worker source (ADR-0001/0002), but the client is disabled by default and no dedicated Hub gateway Worker appears in the current Cloudflare Worker inventory. The existing `mr-siavash-ai-gateway` and its preview belong to MR_SIAVASH_AI and must not be repurposed; keep `gahop` and the GShop route isolated. No Hub gateway service credential is configured in the backend. Do not infer Worker, Pages, D1, DNS, or deployment health from repository CI.
- Historical note: PRs #315 and #328 concerned the retired scheduled provider-backed workflow; PR #436 removes that execution path rather than extending it.
- No Cloudflare production deployment, DNS change, secret mutation, private repository access, or persistent infrastructure write was performed as part of the control-center work.

### Remaining accepted-scope work

1. After explicit owner approval, provision a dedicated isolated Hub staging Worker with `CF_ACCOUNT_ID` and `CF_ZONE_ID` variables, a least-privilege `CF_API_TOKEN` (Workers Scripts Read, Workers Routes Read, D1 Read), and a separate `GATEWAY_AUTH_TOKEN`; configure only the matching `MRH_CLOUDFLARE_GATEWAY_BASE_URL` and `MRH_CLOUDFLARE_GATEWAY_TOKEN` in the Hub server-side secret store. Never reuse the ChatGPT connector credential, the MR_SIAVASH_AI gateway, `gahop`, or the GShop production route.
2. Add independently configured runtime probes for MR_SIAVASH_AI and Gshop only when their exact health contracts are known; otherwise keep them unknown.
3. Add explainable risk summaries only from verified CI, runtime, and infrastructure observations.
4. Keep all action proposals separate from monitoring and require fresh action-bound owner approval for production changes.

---

## Hub stabilization and bounded device dispatch — 2026-11-20 UTC

This checkpoint records the current engineering branch work separately from merged `main` and live infrastructure.

### Merged baseline

- Current Hub `main` at branch creation: `9336e6e94421594d6da7b9a8ea32bcc2604dd533`.
- PR #456 merged migration 50 as `ba0cc7278cc94badfaeb0ef566023cd80112f6fb`, persisting bounded heartbeat runtime metadata. All 20 observed exact-PR-head checks passed; post-merge Backend CI and security checks passed.
- Device pairing remains owner-scoped, uses single-use enrollment, hashed/revocable access and refresh credentials, explicit scopes, authenticated heartbeats, owner listing/revocation, and audit events.
- Decision policy, bounded agent orchestration, specialist registry, durable workflow leases/fencing, safe retry/cancellation/recovery, owner-scoped FTS5 memory, provenance metadata, export/deletion, and read-only Dreaming proposals are already present in the merged codebase. Dreaming does not automatically rewrite or delete memory.
- The default specialist catalog now includes six reviewed profiles: architecture, knowledge synthesis, text helper, defensive security review, quality evaluation, and workflow planning. The three new reviewers are read-only with no tool grants; proposals still require owner-reviewed activation.

### Current device-task implementation branch

- Branch: `feat/device-task-dispatch-final-20261120`.
- Migration 51 adds an owner/device-scoped task queue with strict action and state constraints.
- Initial actions are limited to allow-listed application launch and explicitly owner-confirmed screenshot capture.
- The queue includes timezone-aware scheduling, per-device pending limits, hashed idempotency keys and claim leases, one active claim per device, explicit device scopes, audit events, queued-task cancellation, expiry, and revocation fencing.
- Expired claims become `unknown_outcome` and are not automatically replayed. Device-reported outcomes are labelled `reported_succeeded` / `reported_failed` with `outcome_verified=false`.
- Device-task submission/claim is not yet exposed as an autonomous AgentOrchestrator tool. A separate approval-aware tool adapter and the EL_AGENT client are required before natural-language requests can dispatch device actions; the model must never self-approve screenshots or other sensitive operations.
- Exact-head PR checks passed on `24428ebc8890c71bf384eceb9db83a525117d5cd`: Python 3.11 and 3.12 each reported 1,349 passed / 2 skipped; Backend CI reported the same; Windows wheel smoke, Linux/Windows FFmpeg integration, Workflow Security Audit, Defensive Python Scan, PowerShell parse, failed-startup cleanup, runtime smoke, and Windows backup/device regression passed (58 passed, 1 non-fatal Starlette/httpx TestClient deprecation warning). The PR remains Draft and unmerged pending scope review; it is Hub-side only, not a live device integration.

### Staging, security, and recovery

- `cloudflare/gateway/wrangler.toml` defines the isolated `mr-siavash-hub-gateway-staging` Worker with no routes or custom domains. The last recorded read-only Cloudflare inventory earlier on 2026-11-20 showed that this Worker was not deployed; this checkpoint did not re-query Cloudflare, so that is a last-recorded observation rather than fresh verification.
- Deployment requires `CF_ACCOUNT_ID`, `CF_ZONE_ID`, a dedicated least-privilege `CF_API_TOKEN`, and a separate `GATEWAY_AUTH_TOKEN`; the matching `MRH_CLOUDFLARE_GATEWAY_BASE_URL` and `MRH_CLOUDFLARE_GATEWAY_TOKEN` must be configured in the Hub server-side secret store. The ChatGPT connector credential must not be reused. No Cloudflare resource, route, DNS record, secret, or production environment was changed.
- Backup/restore helpers, checksums, integrity checks, and automated tests exist. The target Windows machine restore drill and protected media/encryption-key backup procedure remain unverified.
- Fresh GitHub branch metadata reports `protected=false` for all three main branches, with required-check enforcement off and no required contexts. No protection setting was changed.
- No live Windows task execution, Telegram action, Instagram publishing, or Production deployment was performed in this checkpoint.

### Remaining release gates

1. Keep PR #460 Draft until its device-task changes and specialist-profile changes are separated or its combined scope is explicitly accepted; the exact-head checks above are green, but the current branch is not merged or deployed.
2. Complete the separate EL_AGENT enrollment, secure credential storage, task polling/claim, outcome reporting, and revocation client; the current companion supports Hub pairing and heartbeat only.
3. Perform target-Windows installation, task execution, backup/restore, upgrade, and rollback acceptance.
4. Deploy the dedicated staging Worker only after its four configuration values and the Hub-side secret are securely configured; run authenticated staging acceptance.
5. Keep the public Website Production release gate closed until fresh Worker/D1 inventory, migration/backup/rollback verification, exact-candidate Preview acceptance, and explicit owner approval.
6. Run end-to-end tests for multi-device isolation, approvals, memory access, specialist delegation, cancellation, timeouts, and audit provenance.


## Cross-repository continuation checkpoint — 2026-11-22 UTC

This continuation refresh follows the merge of PR #477 and documentation checkpoint PR #478. Exact GitHub heads and CI states below were re-read during this continuation. This is not a live Cloudflare inventory, production release, Telegram bot, or physical-device acceptance.

### Exact default-branch heads and CI
- **MR_SIAVASH_HUB_AI:** `d72163f1a48c6ed56869e263f931050e5575f8de`. PR #476 merged as `21d160c872618fff4148ed0da3f73531239a1f8e` and aligned the owner-authenticated project registry with exactly the four enrolled repositories; Gshop is excluded. PR #477 merged as `1dbba378eae7a39b20600d75dce56ee06d069e98`; its exact PR-head CI passed 13/13 checks, with backend coverage logs reporting 1,380 passed, 2 skipped, and 86% coverage on Python 3.11. PR #478 merged the preceding documentation checkpoint as `d72163f1a48c6ed56869e263f931050e5575f8de`; a follow-up correction is needed because the source snapshot in that PR was superseded by the #477 merge. At the latest read, post-merge CI for current Hub main had 2/14 checks completed successfully and 12 still running, with no completed failures.
- **MR_SIAVASH_AI:** `fe48ad35320b5f595c2b14ec0f199967449aa87d`; exact-main CI 7/7 passed. The checked-in release status records a 2026-11-21 read-only Cloudflare audit: Production Worker version 14 was annotated with source `1616545a2e204cb378e2c824299412ca20ef598b`, 104 commits behind then-current Website main; Preview query-string redaction was disabled at that audit. These are dated historical observations, not a fresh Cloudflare read. Issue #120 remains open; no deployment or Worker/D1 mutation was performed.
- **MR_SIAVASH_EL_AGENT:** `d2511f57abe00451ada4b84e5fe1196742393505`; exact-main CI 4/4 passed. PR #23 (Windows consumer) head `dfd482971340fcfe69d36855e005e9fa397062aa` has 9/9 checks passed and is 26 commits ahead / 0 behind current main. PR #25 (Android planner/consumer) head `1f57a3810e6c0ed1bf7eb9959f13db1e8e8195a4` has 5/5 checks passed and is 22 commits ahead / 0 behind current main. Both remain Draft: physical Windows/Android device acceptance and a live isolated Hub Staging round-trip, including scope revocation/expiry, are outstanding. CI success is not device or production acceptance.
- **MR_SIAVASH_EL_AI:** `39ea9557b12ebc827e19b0e4d2f274073752b0a2`; exact-main CI 4/4 passed. Issue #5 remains open. No live Telegram token, bot connection, webhook, or deployment was verified.

### Hub PR queue and cleanup
- PR #476, #477, and #478 are merged. PR #477 exact-head matrix passed all 13 checks; its Python 3.11 backend run reported 1,380 passed, 2 skipped, 86% coverage.
- PR #475 was closed as superseded by #477. PR #472 and #474 were closed because their dated status/HQ snapshots were stale. No branch or source history was deleted.
- This follow-up documentation correction is intentionally separate from merged PR #478 and must pass exact-head CI before merge.

### Governance and operational gates
- A fresh read of all four default branch metadata reports `protected=false`. Required status-check enforcement is not verified as enabled. The connected GitHub action surface exposes no branch-protection/ruleset write operation; issues #304 (Hub), #70 (Website), #27 (EL_AGENT), and #5 (EL_AI) track administrator-side enforcement. Do not claim the governance gate is remediated.
- Hub issue #305 tracks dedicated isolated Cloudflare Staging provisioning and authenticated acceptance. No dedicated staging Worker deployment or Hub-side secret configuration was verified here. Do not reuse the Website Gateway, Preview, `gahop`, or Gshop resources.
- Website issue #120 tracks Cloudflare source/deployment drift and rollback verification. No Worker version, route, DNS, D1, secret, or Production resource was changed.
- Hub issue #182 tracks provider-backed video generation; provider registry remains intentionally unavailable until a provider is explicitly selected/configured. No paid provider was enabled.
- EL_AGENT Windows and Android consumers require physical-device and Staging acceptance before leaving Draft. No device operation or live credential was used.
- EL_AI Telegram runtime acceptance remains blocked on secure bot-token configuration and live owner-controlled verification. No token was created or exposed.
- No production resource, credential, branch-protection setting, device, Telegram account, paid provider, or external service was changed in this checkpoint.

### Immediate next work
1. Complete post-merge Hub main CI and record the final result for `d72163f`.
2. Merge this follow-up checkpoint only after exact-head CI passes.
3. Keep EL_AGENT PR #23 and #25 Draft until device and isolated Staging acceptance can be performed.
4. Keep governance issues open until administrators apply and verify required branch rules.
5. Do not deploy Cloudflare Production from dated source-drift evidence alone; require fresh inventory, backup/rollback validation, exact-candidate smoke tests, and owner-controlled release acceptance.


## Correction — Hub continuation after PRs #479 and #481 — 2026-11-22 UTC

This correction supersedes the Hub-head and post-merge CI statements in the preceding 2026-11-22 checkpoint. It is based on fresh GitHub reads after the two health-readiness fixes merged.

- **Hub `main`:** `41a0a111caae40377e81be5f0c1badf2363f699f`.
- **PR #479** (`fix(health): distinguish stale worker heartbeats`) merged as `1dbba378eae7a39b20600d75dce56ee06d069e98`. The health endpoint now distinguishes a live worker heartbeat from stale or absent detection; required-worker readiness does not treat stale heartbeat data as healthy.
- **PR #481** (`fix(health): reject future worker heartbeat timestamps`) merged as `41a0a111caae40377e81be5f0c1badf2363f699f`. Future-dated worker heartbeat timestamps are rejected as evidence of liveness, with regression coverage for optional and required readiness.
- PR #481 exact-head checks completed **15/15 successfully** before merge. The merged commit is the current `main` head.
- **Current-main post-merge CI** was still running at the latest read: 10/14 check-runs successful, 0 failed, and 4 pending (`test (3.11)`, `test (3.12)`, `test`, and `windows-backup-and-device-regression`). Do not describe current-main CI as fully green until those finish.
- This documentation correction PR #480 has **9/9 exact-head checks successful**. It remains a documentation-only change; no live Cloudflare, staging, production, device, Telegram, secret, or GShop operation is represented or authorized by this record.

The previously recorded Website, EL_AGENT, and EL_AI heads in the earlier checkpoint are historical snapshots and must be refreshed before decisions in those repositories. Operational gates listed above remain open unless separately verified with fresh evidence.


### Commit attribution correction — 2026-11-22 UTC

A review of the PR metadata identified one incorrect merge-SHA attribution in the earlier checkpoint text above:
- PR #477 (test: isolate integration tests from local launcher environment) merged as ff15b26009d642ffe3cdfdfa7c9fca60a4fb9f3b.
- PR #479 (fix(health): distinguish stale worker heartbeats) merged as 1dbba378eae7a39b20600d75dce56ee06d069e98.
The later PR #479 correction section above contains the correct attribution. This note supersedes the earlier sentence that assigned PR #479's SHA to PR #477.


### Follow-up correction — PR #480 and current Hub main — 2026-11-22 UTC

This note supersedes the preceding statement that PR #480 had 9/9 successful checks and the earlier instruction to finish CI for the former Hub head.

- Current Hub `main` was re-read as `41a0a111caae40377e81be5f0c1badf2363f699f` (after PRs #479 and #481).
- PR #480 branch head at this read was `0ec2d0e3c14a97beec30547cc7a3f090480cfce1`, based on `d72163f1a48c6ed56869e263f931050e5575f8de`; comparison against current `main` showed 6 commits ahead and 1 commit behind.
- Exact-head check-runs for `0ec2d0e3c14a97beec30547cc7a3f090480cfce1`: 6/9 successful, 3 in progress, 0 failures. The three running checks were `test (3.11)`, `test (3.12)`, and `test`. Therefore PR #480 was not yet eligible for merge at this read.
- The PR branch requires a fresh documentation checkpoint because the preceding 9/9 claim was premature and the branch is behind current `main`. Do not merge until the corrected commit is tested at its exact head and all required checks succeed.
- The two changed files remain documentation-only. No production, Cloudflare, staging, device, Telegram, credential, paid-provider, or GShop operation was performed.


## Current operational checkpoint — 2026-11-22 UTC

This section supersedes earlier repository-head and CI snapshots above where they conflict. It records GitHub source and CI evidence only; it does not imply live deployment, Staging, Telegram, or physical-device acceptance.

### Verified default branches
- **Hub:** `41a0a111caae40377e81be5f0c1badf2363f699f`; exact-main CI 14/14 successful.
- **Website:** `fe48ad35320b5f595c2b14ec0f199967449aa87d`; exact-main CI 7/7 successful.
- **EL_AGENT:** `d2511f57abe00451ada4b84e5fe1196742393505`; exact-main CI 4/4 successful.
- **EL_AI:** `6bbd8fea0ccb827ac0c2d1429daf707fe4a976d2`; exact-main CI 4/4 successful.

### Current integration gates
- Hub PR #479 and #481 are merged. The current device companion guide below reflects the merged Hub pairing/task contract and the current EL_AGENT consumer PRs.
- EL_AGENT PR #23 (Windows) and #25 (Android) remain Draft. Physical-device acceptance and authenticated Hub Staging round-trips, including expiry and revocation, are not complete.
- The latest read-only Cloudflare inventory found no dedicated Hub Staging Worker. No production Worker, D1, route, DNS, or secret mutation was performed.
- All four default branches remain unprotected; administrator-side branch-protection/ruleset configuration and enforcement verification are outstanding.
- No live Telegram message delivery, production deployment, paid-provider request, or physical-device action is claimed.

This documentation PR must pass exact-head CI before merge. All checks must be evaluated against its final head; cancelled checks are not passes.


### Post-merge correction — PR #483 — 2026-11-22 UTC

- PR #483 merged to Hub `main` as `8793043639d2b8e26590cb5943fd896641a04527`.
- The PR added only regression tests for timezone-naive and malformed worker heartbeat timestamps, covering optional and required-worker readiness behavior.
- Exact PR-head validation on `2542c01121d8b617b2c46dbbc471415d2bfd9a31`: all six observed workflows succeeded (Backend CI, CI matrix, Workflow Security Audit, Defensive Python Scan, Video Render Integration, and Windows Launcher Validation).
- The earlier 14/14 Hub main CI count above belongs to parent main `41a0a111caae40377e81be5f0c1badf2363f699f` and is a pre-#483 snapshot. Do not interpret it as post-merge CI for `8793043`; that post-merge state was not established by this PR-only workflow query.


### Post-merge correction — PR #486 — 2026-11-22 UTC

- PR #486 merged into Hub `main` as `fbf85fae4bcdc001a66675aee6367b8a66c2f0e1`.
- It adds fail-closed validation of the migration registry before SQLite DDL: a non-empty list of positive, non-boolean integer versions in strictly increasing order.
- Regression cases cover duplicate, out-of-order, zero, boolean, and empty registries, and assert that invalid definitions do not create `schema_migrations`.
- Exact PR-head validation on `ff1997562931aa3c543572714be9977fdb4c3e68`: all six workflows passed (Backend CI, CI matrix, Workflow Security Audit, Defensive Python Scan, Video Render Integration, Windows Launcher Validation). Backend CI reported 1,394 passed, 2 skipped, 86% coverage.
- This is source/CI acceptance evidence, not a production database migration. No production database was changed.
