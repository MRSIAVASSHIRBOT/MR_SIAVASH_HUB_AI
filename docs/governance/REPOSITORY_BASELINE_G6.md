# Repository Baseline — G6

- **Baseline date:** 2026-11-27
- **Scope:** HUB, EL_AI, EL_AGENT, MR_SIAVASH_AI
- **Portfolio authority:** [ADR-0051](../architecture/decisions/ADR-0051-four-product-ecosystem-scope-and-telegram-ownership.md)
- **Governance:** [G0–G12](../GOVERNANCE_PRODUCT_STRATEGY_G0_G12.md)
- **Status:** PARTIAL — first source-backed inventory; full source-tree, exact-main, deployment and runtime reconciliation remains open

## 1. Evidence method and limits

This inventory was prepared by reading the four repositories' default-branch README/manifests and selected CI/deployment files directly from GitHub on 2026-11-27. Blob SHAs are recorded where a file was fetched. A blob SHA identifies that file content; it is not a repository commit SHA.

The inventory does **not** claim a complete recursive tree listing, exhaustive dependency/lockfile discovery, source-code line-by-line audit, secret inspection, live infrastructure readback, or production acceptance. No credentials or secret values were read. Branch protection status is included only as recorded in the G0–G12 baseline and must be freshly re-read by a repository administrator before release.

## 2. Portfolio-level snapshot

| Repository | Product boundary | Runtime / primary stack | Build and CI evidence | Current acceptance boundary |
|---|---|---|---|---|
| [MR_SIAVASH_HUB_AI](https://github.com/MRSIAVASSHIRBOT/MR_SIAVASH_HUB_AI) | Central intelligence, planning, workflows, private memory, policy, approvals and audit | Python 3.11+; FastAPI; Pydantic; HTTPX; SQLite; local-first model adapters | Setuptools project; Python 3.11/3.12 CI; pytest/coverage, Ruff, Node gateway checks, Linux/Windows wheel smoke in the CI definition | Local runtime and CI are distinct from paid Render deployment and live operations |
| [MR_SIAVASH_EL_AI](https://github.com/MRSIAVASSHIRBOT/MR_SIAVASH_EL_AI) | Personal conversational agent and complete Telegram implementation boundary | Python 3.11+; HTTPX; Keyring; python-dotenv; cryptography | Setuptools project; Python 3.11/3.12 CI; Ruff and pytest | README states local polling runtime is unconfigured and current test-bot end-to-end acceptance is not claimed |
| [MR_SIAVASH_EL_AGENT](https://github.com/MRSIAVASSHIRBOT/MR_SIAVASH_EL_AGENT) | Standalone local/device runtime for Windows and Android | Python 3.11+ for Windows/local runtime; Android Gradle/Kotlin module | Python 3.11/3.12 on Ubuntu and Windows; PowerShell syntax validation; Android debug build/unit test workflow | Hosted CI is not physical Windows/Android acceptance; README says Hub Staging and physical-device acceptance remain pending |
| [MR_SIAVASH_AI](https://github.com/MRSIAVASSHIRBOT/MR_SIAVASH_AI) | Public digital identity, static website, learning workspace and public Gateway | Static Persian-first web app; Cloudflare Worker Gateway package using Node.js | Gateway CI uses Node.js 22, syntax checks and Node test runner under `cloudflare/gateway`; static site quality/Pages has separate deployment evidence | Public/Preview/Production source and D1 state require fresh control-plane readback; historical notes are not current release authorization |

### Fresh exact-main source, tree and Actions checkpoint — 2026-11-27 16:15 UTC

This checkpoint supersedes the older SHA/check-run table and is based on the current default-branch refs fetched directly from GitHub. All four recursive Git trees returned `truncated=false`; file counts below are blob counts, not code-line counts.

| Repository | Exact `main` SHA | Recursive tree | Exact-head Actions observed | Open PRs observed |
|---|---|---:|---|---:|
| HUB | `0c2bf63b5ac55477cd13f12bd0f673e320164392` | 550 files; complete | 7 successful runs; 1 CI run still in progress | 6 |
| EL_AI | `43765c5749b18e3c29c3987e4ed58884e8a80788` | 103 files; complete | CI, Workflow Security Audit and OpenSSF Scorecard: 3 successful | 1 |
| EL_AGENT | `d98aaff9593b7ffac996e0841c1232bae1dee4df` | 85 files; complete | Python/Windows/Linux CI and Android workflow: 2 successful | 0 |
| MR_SIAVASH_AI | `2a37c00d06b34a29c78c8b6b3aa9da3f0dd6d00a` | 193 files; complete | 6 successful: Gateway CI, Preview/Gateway runtime smoke, Workflow Security, OpenSSF, Pages quality/deploy workflow | 0 |

Exact-head references:
- HUB: [CI](https://github.com/MRSIAVASSHIRBOT/MR_SIAVASH_HUB_AI/actions/runs/46029627968), [Backend CI](https://github.com/MRSIAVASSHIRBOT/MR_SIAVASH_HUB_AI/actions/runs/46029627894), [Workflow Security Audit](https://github.com/MRSIAVASSHIRBOT/MR_SIAVASH_HUB_AI/actions/runs/46029627908), [Windows validation](https://github.com/MRSIAVASSHIRBOT/MR_SIAVASH_HUB_AI/actions/runs/46029627885), [Video integration](https://github.com/MRSIAVASSHIRBOT/MR_SIAVASH_HUB_AI/actions/runs/46029627914), [OpenSSF](https://github.com/MRSIAVASSHIRBOT/MR_SIAVASH_HUB_AI/actions/runs/46029628083). At observation time CI was still in progress; the other listed checks succeeded.
- EL_AI: [CI](https://github.com/MRSIAVASSHIRBOT/MR_SIAVASH_EL_AI/actions/runs/45994569039), [Workflow Security Audit](https://github.com/MRSIAVASSHIRBOT/MR_SIAVASH_EL_AI/actions/runs/45994568968), [OpenSSF](https://github.com/MRSIAVASSHIRBOT/MR_SIAVASH_EL_AI/actions/runs/45994569015).
- EL_AGENT: [CI](https://github.com/MRSIAVASSHIRBOT/MR_SIAVASH_EL_AGENT/actions/runs/45896743567), [Android](https://github.com/MRSIAVASSHIRBOT/MR_SIAVASH_EL_AGENT/actions/runs/45896743467).
- MR_SIAVASH_AI: [Gateway CI](https://github.com/MRSIAVASSHIRBOT/MR_SIAVASH_AI/actions/runs/45896518569), [Preview runtime smoke](https://github.com/MRSIAVASSHIRBOT/MR_SIAVASH_AI/actions/runs/45896518971), [Gateway runtime smoke](https://github.com/MRSIAVASSHIRBOT/MR_SIAVASH_AI/actions/runs/45896518550), [Workflow Security](https://github.com/MRSIAVASSHIRBOT/MR_SIAVASH_AI/actions/runs/45896518989), [OpenSSF](https://github.com/MRSIAVASSHIRBOT/MR_SIAVASH_AI/actions/runs/45896519002), [Quality/Pages workflow](https://github.com/MRSIAVASSHIRBOT/MR_SIAVASH_AI/actions/runs/45896518955).

Open work observed on HUB: #657 (H8 readiness consistency), #658 (H23 shared execution budget), #650 (G10/G11 portfolio catalogue), #637 (PromptForge integration), #636 (portfolio status refresh), and #618 (Draft Render proposal). EL_AI has #149 (Telegram local polling delivery outbox). The latter branches are work-in-progress evidence, not merged mainline capability.

The branch-protection endpoint could not be read through the current GitHub integration (403). Therefore this checkpoint does not assert current protection state. The prior G0–G12 snapshot recorded `protected=false`; an administrator must freshly verify effective rules before release.

### Recursive tree and build-input findings

| Repository | Key configuration/manifests found in the complete tree | Lock/constraint artifacts found |
|---|---|---|
| HUB | `.env.example`, `pyproject.toml`, `render.yaml`, `cloudflare/gateway/wrangler.toml` | None among the inspected standard lock/constraints filenames |
| EL_AI | `.env.example`, `pyproject.toml`, `cloudflare/telegram-edge/package.json` | None among the inspected standard lock/constraints filenames |
| EL_AGENT | `pyproject.toml`, root and Android `build.gradle.kts`, `settings.gradle.kts`, `gradle.properties` | No Python/Gradle lock or wrapper artifacts found; the Android workflow installs Gradle 8.9 directly |
| MR_SIAVASH_AI | `cloudflare/gateway/package.json` | No Node lockfile found |

The check covered common Python lock/constraints files (`uv.lock`, `poetry.lock`, `Pipfile.lock`, `requirements*.txt`, `constraints*.txt`), Node lockfiles, Go/Cargo lockfiles, Gradle wrapper JAR/properties and Gradle version catalogs. It did not attempt to invent or adopt a new dependency manager. Direct dependencies remain declared in the existing manifests; full transitive resolution is not pinned in the checked tree.

The file counts and artifact-name scan are repository-tree evidence only. They do not replace a source-level audit of every module or prove a clean-room reproducible build. In particular, the lack of a Gradle Wrapper in EL_AGENT means local Android build tooling is less self-contained than a wrapper-pinned project.

### H10 API merge — post-merge exact-main checkpoint — 2026-11-27

HUB `main` now points to `4f684b8a8494ffe263db6769b312f884cd6df311`, which integrates PR #641 (owner-scoped, read-only WorkOrder evidence evaluation API). At the latest read, GitHub reported 10 check-runs on this exact SHA: 5 succeeded, 3 were in progress and 2 were queued; no failed checks had been observed. Do not treat this snapshot as fully green until all ten conclude successfully.

The PR-head validation suite passed before merge. The post-merge runtime smoke, Windows FFmpeg, backup/device and full test results remain separately tracked on the exact main SHA.

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

The inspected manifests prove direct dependency declarations, not complete transitive dependency resolution. The root-level paths `uv.lock`, `poetry.lock` and `requirements.txt` were checked for HUB and EL_AI; the inspected `uv.lock` path was checked for EL_AGENT; the Website Gateway's `package-lock.json` path was checked. These checks did not locate those files at those exact paths.

This is not yet an exhaustive recursive lockfile inventory. Before adopting a lock tool, inspect each full repository tree and choose a strategy appropriate to its existing packaging workflow. Do not introduce a new dependency manager or make speculative dependency changes as part of G6 documentation.

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
