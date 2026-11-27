# Repository Baseline — G6

- **Baseline date:** 2026-11-28
- **Scope:** HUB, EL_AI, EL_AGENT, MR_SIAVASH_AI
- **Portfolio authority:** [ADR-0051](../architecture/decisions/ADR-0051-four-product-ecosystem-scope-and-telegram-ownership.md)
- **Governance:** [G0–G12](../GOVERNANCE_PRODUCT_STRATEGY_G0_G12.md)
- **Status:** PARTIAL — first source-backed inventory; full source-tree, exact-main, deployment and runtime reconciliation remains open

## 1. Evidence method and limits

Evidence combines exact default-branch commit reads, complete recursive Git tree reads (`truncated=false`), selected README/manifest/workflow reads, and exact-commit Actions check-runs, all fetched directly from GitHub on 2026-11-27. Blob SHAs identify individual file contents; they are not repository commit SHAs.

The recursive path scan covers the complete source trees and common dependency-lock/build-wrapper filenames. It does **not** claim a source-code line-by-line audit, exhaustive dependency resolution, secret inspection, live infrastructure readback, or production acceptance. No credentials or secret values were read. Branch protection status remains unverified through the current integration and must be freshly read by a repository administrator before release.

## 2. Portfolio-level snapshot

| Repository | Product boundary | Runtime / primary stack | Build and CI evidence | Current acceptance boundary |
|---|---|---|---|---|
| [MR_SIAVASH_HUB_AI](https://github.com/MRSIAVASSHIRBOT/MR_SIAVASH_HUB_AI) | Central intelligence, planning, workflows, private memory, policy, approvals and audit | Python 3.11+; FastAPI; Pydantic; HTTPX; SQLite; local-first model adapters | Setuptools project; Python 3.11/3.12 CI; pytest/coverage, Ruff, Node gateway checks, Linux/Windows wheel smoke in the CI definition | Local runtime and CI are distinct from paid Render deployment and live operations |
| [MR_SIAVASH_EL_AI](https://github.com/MRSIAVASSHIRBOT/MR_SIAVASH_EL_AI) | Personal conversational agent and complete Telegram implementation boundary | Python 3.11+; HTTPX; Keyring; python-dotenv; cryptography | Setuptools project; Python 3.11/3.12 CI; Ruff and pytest | Durable SQLite outbox for local polling replies is merged; local polling remains unconfigured and live/test-bot acceptance is not claimed |
| [MR_SIAVASH_EL_AGENT](https://github.com/MRSIAVASSHIRBOT/MR_SIAVASH_EL_AGENT) | Standalone local/device runtime for Windows and Android | Python 3.11+ for Windows/local runtime; Android Gradle/Kotlin module | Python 3.11/3.12 on Ubuntu and Windows; PowerShell syntax validation; Android debug build/unit test workflow | Hosted CI is not physical Windows/Android acceptance; README says Hub Staging and physical-device acceptance remain pending |
| [MR_SIAVASH_AI](https://github.com/MRSIAVASSHIRBOT/MR_SIAVASH_AI) | Public digital identity, static website, learning workspace and public Gateway | Static Persian-first web app; Cloudflare Worker Gateway package using Node.js | Gateway CI uses Node.js 22, syntax checks and Node test runner under `cloudflare/gateway`; static site quality/Pages has separate deployment evidence | Public/Preview/Production source and D1 state require fresh control-plane readback; historical notes are not current release authorization |

### Fresh exact-main source, tree and Actions checkpoint — 2026-11-28

This checkpoint supersedes the 2026-11-27 18:32 UTC inventory. It was refreshed after the H8, H23, H18, H10 owner-lifecycle, E8 Hub catalog, E8 EL_AI command and H10 priority/deadline merges. Every recursive Git tree returned truncated=false. File counts below count blobs only and exclude directory entries. Actions results are tied to the exact main SHA in each row.

| Repository | Exact main SHA | Recursive files | Exact-head Actions | Open PRs observed |
|---|---|---:|---:|---:|
| HUB | 69f569e1314fc17e2d3edbc03ec838c329852970 | 555; complete | 7/10 successful; 3 in progress; 0 failed | 5 |
| EL_AI | 3d44520117c6d032dd6ea95bff4ab318bb1fb017 | 106; complete | 6/6 successful | 1 |
| EL_AGENT | d98aaff9593b7ffac996e0841c1232bae1dee4df | 85; complete | 5/5 successful | 0 |
| MR_SIAVASH_AI | 2a37c00d06b34a29c78c8b6b3aa9da3f0dd6d00a | 193; complete | 8/8 successful | 1 |

Exact-head workflow references:
- HUB: [Backend CI — running at checkpoint](https://github.com/MRSIAVASSHIRBOT/MR_SIAVASH_HUB_AI/actions/runs/46080287696), [Windows launcher validation](https://github.com/MRSIAVASSHIRBOT/MR_SIAVASH_HUB_AI/actions/runs/46080287884), [FFmpeg Linux/Windows integration](https://github.com/MRSIAVASSHIRBOT/MR_SIAVASH_HUB_AI/actions/runs/46080287760), [Defensive Python scan](https://github.com/MRSIAVASSHIRBOT/MR_SIAVASH_HUB_AI/actions/runs/46080287823), [Workflow security audit](https://github.com/MRSIAVASSHIRBOT/MR_SIAVASH_HUB_AI/actions/runs/46080287685), [Supply-chain security posture](https://github.com/MRSIAVASSHIRBOT/MR_SIAVASH_HUB_AI/actions/runs/46080287744). At this read, Backend CI, Windows backup/device regression and Windows FFmpeg were still in progress; no failed check was present.
- EL_AI: [Python 3.11/3.12 CI](https://github.com/MRSIAVASSHIRBOT/MR_SIAVASH_EL_AI/actions/runs/46080141251), [Supply-chain security posture](https://github.com/MRSIAVASSHIRBOT/MR_SIAVASH_EL_AI/actions/runs/46080063817), [Workflow security audit](https://github.com/MRSIAVASSHIRBOT/MR_SIAVASH_EL_AI/actions/runs/46080063808).
- EL_AGENT: [Python Linux/Windows matrix](https://github.com/MRSIAVASSHIRBOT/MR_SIAVASH_EL_AGENT/actions/runs/45896743567), [Android debug build and unit tests](https://github.com/MRSIAVASSHIRBOT/MR_SIAVASH_EL_AGENT/actions/runs/45896743467).
- MR_SIAVASH_AI: [Static-site/Gateway CI and Pages](https://github.com/MRSIAVASSHIRBOT/MR_SIAVASH_AI/actions/runs/45896518955), [Preview runtime smoke](https://github.com/MRSIAVASSHIRBOT/MR_SIAVASH_AI/actions/runs/45896518971), [Gateway runtime smoke](https://github.com/MRSIAVASSHIRBOT/MR_SIAVASH_AI/actions/runs/45896518550), [Workflow security audit](https://github.com/MRSIAVASSHIRBOT/MR_SIAVASH_AI/actions/runs/45896518989), [OpenSSF Scorecard](https://github.com/MRSIAVASSHIRBOT/MR_SIAVASH_AI/actions/runs/45896519002).

Current open work observed:
- HUB: #659 (this G6 baseline refresh), #650 (G10/G11 portfolio catalogue), #637 (PromptForge integration), #636 (portfolio status refresh), and #618 (Draft Render infrastructure proposal).
- EL_AI: #153 (guarded opt-in for Telegram Business updates).
- EL_AGENT: no open PRs observed.
- MR_SIAVASH_AI: #318 (Dependabot update for OpenSSF Scorecard action).

Mainline changes since the earlier snapshot:
- HUB: H8 readiness consistency (#657), shared Agent execution budget (#658), WorkOrder evidence revision binding (#660), owner-scoped Task lifecycle routes/history (#661), E8 read-only Telegram tool catalog (#662), and H10 priority/deadline scheduling (#663) are merged.
- EL_AI: durable Telegram outbox (#149) and the owner-only /tools catalog command (#151) are merged.
- The exact-current-main HUB CI was still running when this checkpoint was written. Individual feature PRs passed their exact-head gates before merge; post-merge main checks remain a separate acceptance item until all current runs finish.

The latest branch-protection endpoint remains unavailable through the current GitHub integration (403). Therefore this checkpoint does not assert effective branch protection. The G0–G12 baseline recorded protected=false on 2026-11-27; that is a historical snapshot, not proof of the current state. A repository administrator must freshly verify rulesets and required checks before release.
 
### Recursive tree and build-input findings

| Repository | Key configuration/manifests found in the complete tree | Lock/constraint artifacts found |
|---|---|---|
| HUB | `.env.example`, `pyproject.toml`, `render.yaml`, `cloudflare/gateway/wrangler.toml` | No standard Python/Node/Go/Cargo/Gradle lock or dependency-constraint artifacts found in the recursive tree |
| EL_AI | `.env.example`, `pyproject.toml`, `cloudflare/telegram-edge/package.json` | No standard Python/Node/Go/Cargo lock or dependency-constraint artifacts found in the recursive tree |
| EL_AGENT | `pyproject.toml`, root and Android `build.gradle.kts`, `settings.gradle.kts`, `gradle.properties` | No Python/Gradle lockfiles or Gradle wrapper files found; the Android workflow installs Gradle 8.9 directly |
| MR_SIAVASH_AI | `cloudflare/gateway/package.json` | No Node lockfile found in the recursive tree |

The check covered common Python lock/constraints files (`uv.lock`, `poetry.lock`, `Pipfile.lock`, `requirements*.txt`, `constraints*.txt`), Node lockfiles, Go/Cargo lockfiles, Gradle wrapper JAR/properties and Gradle version catalogs. It did not attempt to invent or adopt a new dependency manager. Direct dependencies remain declared in the existing manifests; full transitive resolution is not pinned in the checked tree.

The file counts and artifact-name scan are repository-tree evidence only. They do not replace a source-level audit of every module or prove a clean-room reproducible build. In particular, the lack of a Gradle Wrapper in EL_AGENT means local Android build tooling is less self-contained than a wrapper-pinned project.

### H10, H18, H23 and E8 implementation status — 2026-11-28

The merged changes are implementation slices, not claims that their full expanded phases are DONE:
The portfolio uses two phase-numbering views: FOUR_PRODUCT_TECHNICAL_PHASES lists compact H0–H20 phases, while EXTENDED_PHASE_CROSSWALK lists expanded H0–H32 phases. In particular, expanded H10 (Task Lifecycle) maps to compact H1/H7, expanded H18 (Evaluation & Verification) maps to compact H10, and expanded H28 (Scalability & Performance) maps to compact H18. Read phase IDs together with their taxonomy, not as interchangeable labels.

- **Expanded H10 Task Lifecycle** (maps to compact H1/H7 in FOUR_PRODUCT_TECHNICAL_PHASES): owner-scoped task detail/result/list/history/cancel routes are merged; priority and timezone-aware deadline fields are persisted through additive migration 60; worker dispatch uses priority aging, deadline ordering and deterministic tie-breakers. Remaining work includes a first-class task owner column/backfill, post-create rescheduling/reprioritization, overdue/SLA notifications, configurable fairness and cooperative cancellation of running workers. Deadline expiry does not change lifecycle state or auto-cancel a task.
- **Expanded H18 Evaluation & Verification** (maps to compact H10 in FOUR_PRODUCT_TECHNICAL_PHASES): encrypted WorkOrder plan records now bind explicit WorkOrder/plan revisions and a canonical WorkOrder digest; the owner-scoped evidence evaluation path stays read-only and fails closed on stale or mismatched digests. Production evidence adapters, a plan supersede/edit lifecycle and an EL_AI E8 consumer contract remain pending.
- **H23 Resource & Budget Management:** one in-memory execution budget is shared across root Agent runs and delegated specialists, with aggregate input/output reservations, model/tool/delegation ceilings and a shared deadline. Provider quota enforcement, durable compute/storage accounting, cross-product cost accounting and representative load/fairness validation remain pending.
- **E8 Tool & Skill Interface:** a versioned, read-only telegram_tool_catalog.v1 endpoint and owner-only EL_AI /tools command are merged. The explicit tools:read scope exposes metadata only; it does not invoke tools or grant execution permissions. Full tool/skill invocation remains separately permission- and approval-gated.

The HUB exact-main workflow set in the checkpoint above had 7/10 successful checks and 3 in progress at the time of the read. Feature-PR success before merge is not a substitute for completing this post-merge check set. None of these CI results proves production deployment, live Telegram operation, provider billing accuracy or physical-device acceptance.

## 3. Repository details

### 3.1 HUB

**Observed project manifest:** `pyproject.toml`, blob `389333b9f60cda6180b5dce3dca7dafc4e76cae9`.

- Package: `mr-siavash-hub-ai`; Python requirement: `>=3.11`; setuptools build backend.
- Runtime dependencies declared include FastAPI, Uvicorn, Pydantic, pydantic-settings, HTTPX and cryptography.
- The README documents separate API and pull-worker processes, SQLite persistence and a persistent `MRH_WORKFLOW_PAYLOAD_KEY` for durable encrypted workflow payloads.
- `.github/workflows/ci.yml` blob `dc9e899dd80c5a04478a3c65a81334fe6694b919` defines Python 3.11/3.12, backend tests/coverage, Ruff, Node syntax/contract tests and Linux/Windows wheel packaging smoke.
- `.github/workflows/backend-ci.yml` blob `9fa0f27967e31d4b50406714746115fb12f205bd` defines Python 3.11 install, pip-audit, Ruff and pytest coverage.
- `render.yaml` blob `a269b7ef05989b80493d837c7a7777626947f306` describes a paid Starter service with a 10 GB persistent disk, auto-deploy off and host-supplied secrets. This file is configuration evidence only; it does not prove that resources are provisioned or authorize provisioning.

**G6 follow-up:** capture one exact default-branch commit SHA and its complete workflow/check-run set; inventory all backend modules, migrations, test layers, config names and backup/restore evidence; reconcile dependency lock strategy. Keep Render cost/provisioning separate under G12.

### 3.2 EL_AI

**Observed project manifest:** `pyproject.toml`, blob `068890611111c5e4a95bc6192835f6375e4f07db`.

- Package: `mr-siavash-el-ai`; Python requirement: `>=3.11`; setuptools build backend.
- Runtime dependencies include HTTPX, Keyring, python-dotenv and cryptography.
- Development extras include pytest, pytest-asyncio and Ruff.
- `.github/workflows/ci.yml` blob `8245a10535eecf04438a3fee3e9b0cbe0a69e0d6` defines Python 3.11/3.12, editable dev installation, Ruff and pytest.
- The README defines EL_AI as owner of Telegram update intake, identity, commands, conversation, message delivery and channel lifecycle; HUB remains authoritative for private memory, tasks and policy.
- The README states that the local Python polling runtime is not configured, no current test-bot end-to-end result is claimed, and production bot activation is not claimed.

**G6 follow-up:** inventory every Telegram adapter/worker and its tests; verify configuration validation and credential storage paths without reading secret values; map each delivery state to a test; distinguish local simulation, test-bot acceptance and production activation. No production Telegram action is implied.

### 3.3 EL_AGENT

**Observed Python manifest:** `pyproject.toml`, blob `f06cd8ce10dc3a58de1b725bf0f5002d0401db20`.

- Package: `mr-siavash-el-agent`; Python requirement: `>=3.11`; setuptools build backend.
- Python runtime dependencies include FastAPI, Uvicorn, mss and Pillow. Optional extras define voice dependencies and Keyring support for cloud/pairing features.
- Root `build.gradle.kts`, blob `c7ad7549e74f63b6958ba4e171cc08161976da49`, declares Android Gradle Plugin 8.7.3 and Kotlin Android 2.0.21.
- `.github/workflows/ci.yml` blob `5b45b2ec32b65acea86ad6fe25a1c7539cd0ea82` defines an Ubuntu/Windows × Python 3.11/3.12 matrix, PowerShell installer syntax validation and pytest.
- `.github/workflows/android.yml` blob `1ba45b9c849e52f5e5876f13601fa52b4b05d980` defines Java 17, Android SDK 35, Gradle 8.9, Android unit tests and a debug APK build.
- The README describes a Windows local API/CLI/control center and Android companion; it explicitly states Hub Staging and physical-device acceptance remain pending.

**G6 follow-up:** finish Android module/Gradle wrapper/source inventory; verify reproducible APK build inputs and artifact provenance; establish supported Windows/Android device matrix; keep physical-device acceptance in D14/G12 and do not infer it from hosted CI.

### 3.4 MR_SIAVASH_AI

**Observed public product:** README blob `7577c92ec477160ff9ceeae9d64236a38047b37a`.

- The README describes a Persian-first public web application, learning modules, browser-local workspace and public Gateway. Private HUB memory, credentials, durable tasks and EL_AGENT device execution are outside this product boundary.
- `cloudflare/gateway/package.json`, blob `86dfcdf19450952d3ca68865a609e8d6c91106fc`, declares a private ES module package with a Node test script.
- `.github/workflows/ci.yml`, blob `1ceb0538463bf8f773fbdceb089097f90641805a`, defines Node.js 22, JavaScript syntax checks and `npm test --prefix cloudflare/gateway`.
- The Gateway source path observed is `cloudflare/gateway/src/index.js`; it uses bounded method/header allowlists and public FAQ/module knowledge in the inspected source excerpt.
- The tested root paths did not contain `package.json` or `wrangler.toml`; the Gateway package did not contain a `package-lock.json` at the inspected path. This is a bounded path check, not a claim that no build metadata or lockfile exists anywhere in the repository.
- `docs/ROADMAP.md` is dated 2026-11-23 and includes historical production/preview observations and explicit release gates. Treat these as dated historical records, not fresh live control-plane state.

**G6 follow-up:** map all static build/deploy workflows and their artifact provenance; locate the current Worker/Pages configuration and dependency lock strategy; obtain fresh read-only Production/Preview/D1 inventory before any deployment or migration; confirm public/private isolation on the exact current source.

## 4. Cross-repository standards findings

| Area | Observed state | Required follow-up |
|---|---|---|
| Runtime versions | Python 3.11+ in HUB, EL_AI and EL_AGENT; CI matrices differ by repo. Website Gateway uses Node 22 in its workflow. | Publish a current per-product support matrix and keep developer/CI versions aligned. |
| Python packaging | Setuptools-based `pyproject.toml` in the three Python repositories. | Confirm lock/constraints strategy and clean-install reproducibility for each repository. |
| Android packaging | EL_AGENT has a dedicated Android Gradle/Kotlin workflow. | Inventory Gradle wrapper, module plugins, SDK/NDK requirements, signing and release provenance. |
| Automated checks | All products have documented CI; tests differ by runtime and product. | Add a required-check map and verify status checks on protected PRs/default branches. |
| Secrets | HUB/EL_AI/EL_AGENT docs describe isolated secret/key handling. No secret contents were inspected. | Verify secret names, scopes, rotation and environment separation by metadata only; never log values. |
| Deployments | HUB Render config describes paid persistent storage; Website uses Cloudflare Gateway/Pages workflows; EL_AI/EL_AGENT have separate runtime/operator paths. | Keep source CI, preview, production, Telegram and device evidence separate. |
| Branch governance | G0–G12 baseline recorded all four default branches as `protected=false` on 2026-11-27 and linked existing owner/admin issues. | Repository admin must freshly configure and read back rulesets/required checks; documentation cannot change GitHub access policy. |

## 5. Dependency and lockfile audit boundary

The recursive trees for all four exact `main` commits were scanned for common Python lock/constraint files (`uv.lock`, `poetry.lock`, `Pipfile.lock`, `requirements*.txt`, `constraints*.txt`), Node lockfiles (`package-lock.json`, `pnpm-lock.yaml`, `yarn.lock`, `bun.lock`), Go/Cargo lockfiles, and Gradle wrapper files. No matching dependency lock/constraint artifacts were found. This is a filename/path scan, not a dependency vulnerability audit or proof that all build inputs are hermetic.

The manifests prove direct dependency declarations, not complete transitive dependency resolution. Do not introduce a new dependency manager or make speculative dependency changes as part of G6 documentation. A future packaging task should choose a lock strategy per repository and verify clean-install reproducibility.

## 6. G6 exit criteria

G6 can advance from PARTIAL only when each product has:

1. An exact default-branch commit SHA and timestamped source inventory.
2. A module/architecture map covering entry points, boundaries, data stores and external interfaces.
3. A verified manifest, lock/constraints and build-tool inventory.
4. A configuration and secret-*name* inventory without exposing secret values.
5. A test/CI map with exact workflow names, tested commit SHAs and observed results.
6. A deployment/runtime map that distinguishes local, CI, staging, production, Telegram and physical-device evidence.
7. A risk/dependency list with owners and linked Work Orders.

Until those items are reconciled, G6 remains PARTIAL.

## 7. Evidence files

- HUB: `README.md`, `pyproject.toml`, `.github/workflows/ci.yml`, `.github/workflows/backend-ci.yml`, `render.yaml`.
- EL_AI: `README.md`, `pyproject.toml`, `.github/workflows/ci.yml`, `docs/operations/portfolio-checkpoint-2026-11-26.md`.
- EL_AGENT: `README.md`, `pyproject.toml`, `build.gradle.kts`, `.github/workflows/ci.yml`, `.github/workflows/android.yml`.
- Website: `README.md`, `cloudflare/gateway/package.json`, `cloudflare/gateway/src/index.js`, `.github/workflows/ci.yml`, `docs/ROADMAP.md`.
