# Engineering Standards & CI Matrix — G7

- **Baseline:** 2026-11-27
- **Portfolio:** HUB, EL_AI, EL_AGENT, MR_SIAVASH_AI
- **Authority:** [ADR-0051](../architecture/decisions/ADR-0051-four-product-ecosystem-scope-and-telegram-ownership.md)
- **Governance:** [G0–G12](../GOVERNANCE_PRODUCT_STRATEGY_G0_G12.md)
- **Status:** PARTIAL — a cross-repository baseline is recorded; enforcement, parity and named maintainer review remain open

## 1. Purpose

This document records the engineering and CI practices observed in the four product repositories and defines the minimum portfolio standard. It does not replace product-specific toolchains. Each repository may use its native stack while meeting the same evidence, security, review and release outcomes.

## 2. Current observed CI/tooling matrix

| Repository | Language/build | Automated checks observed in workflow definition | Platform matrix | Notable gap / follow-up |
|---|---|---|---|---|
| HUB | Python 3.11+ / setuptools; FastAPI; Node checks for bundled Worker gateway | pytest with coverage, Ruff, pip-audit in Backend CI, Node syntax and contract tests, wheel/package smoke | Python 3.11/3.12; Linux and Windows wheel smoke | Make required-check policy explicit; preserve immutable action pinning; establish exact-main evidence and reproducible dependency install |
| EL_AI | Python 3.11+ / setuptools | pytest, Ruff selective lint rules | Python 3.11/3.12 | Verify format/type/security gates and coverage policy; map Telegram delivery requirements to exact tests |
| EL_AGENT | Python 3.11+ / setuptools; Android Gradle/Kotlin | pytest, PowerShell syntax parser, Android unit tests and debug APK build | Ubuntu + Windows × Python 3.11/3.12; Android build on Ubuntu with Java 17 / SDK 35 / Gradle 8.9 | CI currently references several actions by version tags (e.g. checkout/setup-python v4/v5) rather than immutable commit SHA; align supply-chain pinning and document Android toolchain reproducibility |
| MR_SIAVASH_AI | Static website; Cloudflare Worker Gateway (Node.js) | Gateway JS syntax checks and Node test runner; separate site Quality/Pages workflow is documented | Node.js 22 for Gateway CI; browser/Pages workflow is separate | Map full static build/accessibility/E2E workflow and exact artifact provenance; verify deployment configuration and lock strategy |

### Source files inspected

| Repository | Evidence path | Observed blob SHA |
|---|---|---|
| HUB | `.github/workflows/ci.yml` | `dc9e899dd80c5a04478a3c65a81334fe6694b919` |
| HUB | `.github/workflows/backend-ci.yml` | `9fa0f27967e31d4b50406714746115fb12f205bd` |
| EL_AI | `.github/workflows/ci.yml` | `8245a10535eecf04438a3fee3e9b0cbe0a69e0d6` |
| EL_AGENT | `.github/workflows/ci.yml` | `5b45b2ec32b65acea86ad6fe25a1c7539cd0ea82` |
| EL_AGENT | `.github/workflows/android.yml` | `1ba45b9c849e52f5e5876f13601fa52b4b05d980` |
| MR_SIAVASH_AI | `.github/workflows/ci.yml` (Gateway CI) | `1ceb0538463bf8f773fbdceb089097f90641805a` |

A blob SHA identifies the fetched workflow file content; it is not the commit SHA on which an Actions run executed.

## 3. Portfolio minimum engineering standard

### 3.1 Code and packaging

- Keep language/runtime versions explicit in project manifests and CI matrices.
- Keep public APIs, schemas, persistence and inter-product contracts versioned.
- Use the repository's existing package manager/build system; do not introduce a second manager without an ADR and migration plan.
- Keep build artifacts reproducible enough to identify source commit, toolchain and artifact digest.
- Do not commit generated secrets, local databases, private user data or production credentials.
- Keep optional provider/voice/device dependencies optional when the product can operate without them.

### 3.2 Tests and acceptance evidence

- Every behavior change adds or updates focused unit tests.
- Authentication, policy, tools, Telegram, device actions and cross-project APIs require negative tests for invalid identity, missing scope, expiry, revocation, malformed input and unexpected failure.
- Retry/idempotency paths must include duplicates, timeouts, unknown outcomes, cancellation and recovery.
- Persistence changes require migration-order, upgrade, backup and restore coverage.
- Cross-project contracts require both producer and consumer verification; fixture equality is not proof of a live integration.
- Physical-device, live Telegram, cloud control-plane and production acceptance remain separate from hosted CI.
- A reported PASS names the exact commit SHA, workflow/check, result and run URL.

### 3.3 Lint, format and static quality

- Python repositories use a consistent Ruff baseline for lint and, where adopted, formatting; exceptions are documented rather than silently divergent.
- Android/Kotlin code uses the project's configured Gradle/Android validation and unit tests; any added lint tool requires a recorded config and CI gate.
- Website JavaScript uses syntax checks and Node test coverage for Gateway logic; browser accessibility/E2E checks belong to the site quality workflow.
- A green test suite does not replace dependency, secret, workflow and security review.

### 3.4 CI workflow and supply-chain controls

- Workflows use least-privilege permissions; `contents: read` is the normal default for test-only jobs.
- Checkout must not leave a write-capable token persisted unless a specific later step requires it; that need must be justified.
- Prefer immutable full-SHA action pins with a human-readable version comment. Version tags alone are weaker against tag movement.
- Use bounded job timeouts and concurrency groups; cancellation behavior is selected intentionally so a newer run cannot silently erase required evidence.
- Separate test, security, packaging, deployment and production workflows so each status means one clear thing.
- Required check names must be configured in branch rules and must run on the exact PR head.

### 3.5 Documentation and review

- Each repository entry point links product goals, ownership, technical phases, security model, install/run instructions and operational status.
- Use ADRs for cross-product boundaries, data ownership, contract versions, deployment topology and material dependency decisions.
- Every Work Order records owner, scope, non-goals, risk, dependencies, test plan, exact SHA evidence, rollback and acceptance decision.
- PRs are focused and reviewable. Do not overwrite another contributor's branch or duplicate overlapping files.
- Historical status snapshots retain their date and are not reused as current deployment evidence.

## 4. Current portfolio-level gaps

1. **Branch governance:** the G0–G12 baseline records all four default branches as `protected=false` on 2026-11-27 and links the existing owner/admin issues. The effective rules must be freshly configured and read back by repository administration.
2. **Action pinning parity:** HUB, EL_AI and Website workflow examples inspected here pin major actions by commit SHA; the EL_AGENT workflows inspected here use version tags such as `@v4`/`@v5`. Align the remaining actions after verifying the exact action revisions and update process.
3. **Dependency reproducibility:** root-level lock/constraints paths have not been exhaustively inventoried. Select a repository-appropriate reproducible install strategy only after complete tree inspection.
4. **Python lint parity:** Ruff is visible in HUB and EL_AI CI; the inspected EL_AGENT CI does not invoke Ruff. Determine whether that is intentional and align a minimal shared baseline.
5. **Website quality parity:** Gateway CI is explicit; the complete static site quality/accessibility/browser workflow still needs a separate file-level and exact-run inventory.
6. **Required check policy:** workflow existence does not make a check mandatory. Admin read-back of protected-branch rules and exact required check names remains outstanding.
7. **Named maintainers:** role-level RACI exists, but the ecosystem owner must still confirm named maintainers, security reviewers and release operators.

## 5. Work required to advance G7

- Inventory every workflow in each repository and classify it as test, security, package, preview, deployment or manual.
- Compare action references, token permissions, secret exposure, checkout persistence, timeout and concurrency behavior.
- Confirm the exact test/lint/format/type/dependency audit gates for each runtime.
- Decide and document the required status checks and branch policy; the actual repository settings require owner/admin configuration.
- Link each mandatory standard to a workflow file and exact run evidence on the current candidate.
- Re-review the matrix after material CI/toolchain changes.

Until those controls are enforced and independently verified, G7 remains PARTIAL.
