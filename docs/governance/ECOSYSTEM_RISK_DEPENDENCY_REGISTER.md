# Ecosystem Risk & Dependency Register — G9

- **Baseline:** 2026-11-27
- **Authority:** [G0–G12 governance baseline](../GOVERNANCE_PRODUCT_STRATEGY_G0_G12.md) and [ADR-0047](../architecture/decisions/ADR-0047-four-product-ecosystem-scope-and-telegram-ownership.md)
- **Portfolio:** HUB, EL_AI, EL_AGENT, MR_SIAVASH_AI
- **Status:** Initial centralized register; active items remain open until their closure evidence is recorded
- **Review rule:** Refresh this register whenever a material repository, architecture, security, deployment, cost, legal, or operational fact changes, and during each milestone/release review

## 1. Purpose and operating rules

This register is the canonical G9 record for portfolio-level risks and dependencies. It consolidates the initial risk summary in the G0–G12 baseline and makes each item actionable.

A risk is not closed because a mitigation was proposed, a branch exists, a PR was opened, or CI passed. Closure requires the named evidence and a dated review decision. A dependency is not satisfied by an assumption; its evidence must be linked.

### Rating model

**Likelihood:** Unlikely / Possible / Likely.

**Impact:** Low / Moderate / High / Critical.

**Priority mapping:**

| Priority | Rule | Response |
|---|---|---|
| P0 | Critical impact, or a credible path to unauthorized data/action or irreversible production harm | Stop affected release/action; owner/security review required |
| P1 | High impact with Possible/Likely likelihood, or any unmitigated high-impact owner gate | Must be mitigated or explicitly accepted before dependent release |
| P2 | Moderate impact or a material engineering/reliability gap with bounded impact | Schedule in a milestone and track to acceptance |
| P3 | Low impact / improvement | Maintain as backlog; reassess on change |

Ratings are initial qualitative assessments based on recorded repository evidence, not measured incident probabilities. Re-rate when new evidence changes likelihood or impact.

### Status vocabulary

- **OPEN:** risk exists and has not met its closure criteria.
- **MITIGATING:** an implementation or review action is in progress; risk remains open.
- **OWNER GATE:** only the ecosystem owner, repository admin, legal adviser, billing owner, or physical-device operator can satisfy the dependency.
- **ACCEPTED:** an authorized owner has explicitly accepted a documented residual risk with a review date.
- **CLOSED:** objective closure evidence is linked and the reviewer/date are recorded.

## 2. Active risk register

| ID | Risk and evidence | Likelihood | Impact | Priority / status | Accountable owner | Mitigation and closure evidence |
|---|---|---|---|---|---|---|
| R-01 | **Main-branch governance is not enforced.** The 2026-11-27 baseline records `protected=false` for all four repositories and links existing admin issues: [HUB #304](https://github.com/MRSIAVASSHIRBOT/MR_SIAVASH_HUB_AI/issues/304), [EL_AI #5](https://github.com/MRSIAVASSHIRBOT/MR_SIAVASH_EL_AI/issues/5), [EL_AGENT #27](https://github.com/MRSIAVASSHIRBOT/MR_SIAVASH_EL_AGENT/issues/27), [Website #70](https://github.com/MRSIAVASSHIRBOT/MR_SIAVASH_AI/issues/70). | Likely | High | P1 / OWNER GATE | Repository owner/admin | Configure branch protection or rulesets for all four default branches; require PR review and the correct exact-head checks; restrict force-push/deletion and document bypass policy. Close only after independently reading back each repository's effective rules. |
| R-02 | **Portfolio scope can drift while the correction is unmerged.** Historical ADR/roadmap material described a different active portfolio and Telegram ownership. ADR-0047 and PR #639 define the owner-approved four-product scope, but the change is not canonical on `main` until reviewed and merged. | Possible | High | P1 / MITIGATING | Ecosystem owner + HUB architecture | Review and merge ADR-0047/G0–G12 baseline; preserve historical records but mark them superseded for active execution; verify all current entry points and roadmaps point to the four-product source. |
| R-03 | **CI evidence can be mistaken for production/live acceptance.** The governance baseline explicitly distinguishes GitHub source/CI from live Telegram, cloud control planes, physical devices, and production services. | Likely | High | P1 / OPEN | Each product operational owner | Keep separate evidence states for unit/CI, integration, staging, real device, external provider, deployment, and production. Release reports must name exact commit, environment, test identity, and observed outcome. |
| R-04 | **Cross-product identity, authorization, or private-data boundaries can drift.** The architecture assigns private shared intelligence/policy to HUB, Telegram interaction to EL_AI, device-local execution to EL_AGENT, and public-only website behavior to MR_SIAVASH_AI. | Possible | Critical | P1 / OPEN | HUB security + all product maintainers | Keep versioned contracts and least-privilege scopes; add negative consumer contract tests for unauthorized scope, stale credentials, revocation, public/private leakage, replay, and malformed responses. Close per contract and exact-main CI evidence, plus independent security review for high-risk paths. |
| R-05 | **Paid infrastructure may be provisioned before cost approval.** HUB PR #618 is a Draft Render proposal involving paid services/disks and explicitly requires owner review of the full plan, recurring charges, and auto-sync settings before provisioning. | Possible | High | P1 / OWNER GATE | Ecosystem billing owner | Keep PR #618 Draft and resources unprovisioned until the account owner inspects the current plan and recurring amount, confirms auto-sync state, and gives explicit approval. CI is not financial authorization. |
| R-06 | **Telegram end-to-end behavior remains short of live acceptance.** The EL_AI technical inventory marks E10 partial and requires test-bot acceptance for update intake, delivery, duplicate/unknown/expired/rate-limit/media paths. | Possible | High | P1 / OWNER GATE | EL_AI maintainer + bot operator | Complete isolated adapter/contract tests first; then perform a controlled test-bot acceptance with a non-production identity, bounded traffic, sanitized evidence, and rollback/disable path. Do not send production messages as a substitute. |
| R-07 | **Windows/Android physical-device acceptance is not established by CI alone.** EL_AGENT D14 is an owner/environment gate and requires supported-platform install, security, offline, and rollback evidence on real devices. | Possible | High | P1 / OWNER GATE | EL_AGENT maintainer + device operator | Maintain a device/OS matrix; execute documented physical-device acceptance with permission-denial and offline paths; retain redacted logs and package hashes. Do not mark device phases done from hosted CI only. |
| R-08 | **Legal/IP/privacy readiness is not independently approved.** HUB `COPYRIGHT.md` records that no project-wide open-source license has been selected or granted; the governance baseline also reserves privacy, terms, data-processing and legal sufficiency for owner/qualified review. | Possible | High | P1 / OWNER GATE | Ecosystem owner + qualified legal adviser | Inventory first- and third-party assets/dependencies; select or explicitly retain licensing terms; review attribution, privacy notices, terms, data collection/retention, provider processing and jurisdictional obligations. Record reviewer, date, scope, and approved documents. Do not make legal-compliance claims before review. |
| R-09 | **Loss of the local workflow-encryption key can make queued workflow payloads unrecoverable.** The HUB README states that the database and `MRH_WORKFLOW_PAYLOAD_KEY` must be backed up together. | Possible | High | P1 / OPEN | HUB operations owner | Document protected key custody and backup pairing; test restore of both database and key in an isolated environment; record recovery time, integrity checks, and key rotation/recovery limitations. Never place the key in source control or logs. |
| R-10 | **Dependency reproducibility and standards enforcement are not consistently evidenced across repositories.** The 2026-11-25 status checkpoint recorded no Python lockfile in inspected root manifests; current inventory must reconfirm each repository before prescribing a locking tool. | Possible | Moderate | P2 / OPEN | Maintainers of each repository | Inventory actual package managers, lockfiles, runtime matrices and build inputs at exact main SHAs; adopt a repository-appropriate reproducibility strategy; prove clean installation and CI parity. Avoid speculative dependency changes. |
| R-11 | **Evidence freshness can silently decay.** Repository heads, PR queues, Actions runs, provider versions and deployment state change independently; the governance/technical inventories are dated snapshots. | Likely | Moderate | P2 / OPEN | HUB delivery coordinator + product maintainers | Timestamp each checkpoint with exact SHAs and run identifiers; refresh after merges/releases and before dependent work; mark stale observations rather than presenting them as current. |
| R-12 | **Unowned or overly broad Work Orders can create duplicate/conflicting changes.** The RACI currently defines product/capability ownership but named maintainers and release operators still require owner validation. | Possible | High | P1 / OPEN | Ecosystem owner + delivery coordinator | Require one accountable owner, one repository scope, explicit paths/contracts, dependencies, acceptance criteria and overlap check for every Work Order; do not start when ownership or file-level coordination is ambiguous. |
| R-13 | **Requirements and use cases are not yet fully traceable to implementation and executable verification.** G2/G3 catalogues exist, but their acceptance scenarios still need product-level sequence/contract tests and stable links to Work Orders. | Possible | Moderate | P2 / OPEN | Product/requirements owner + product maintainers | Link each requirement/use case to owning product, technical phase, Work Order, test/acceptance evidence and explicit not-implemented state. Close only after sample-based audit confirms traceability and gaps remain visible. |
| R-14 | **Architecture decisions may be recorded inconsistently across repositories.** Existing ADRs exist, but a shared required structure for alternatives, security/data-flow impact, owner decision and verification was not present in this baseline. | Possible | Moderate | P2 / MITIGATING | HUB architecture owner + product architects | Adopt [ADR_TEMPLATE.md](../architecture/decisions/ADR_TEMPLATE.md); maintain a cross-product ADR index with status/supersession and link consequential decisions to Work Orders and exact verification evidence. |

## 3. Cross-product dependency register

| ID | Dependency | Provider → consumer | Why it matters | Required evidence / gate | Status |
|---|---|---|---|---|---|
| D-01 | Four-product scope authority | Ecosystem owner → all four products | Prevents duplicate ownership and legacy scope drift | ADR-0047 reviewed/merged; all current roadmaps and agent instructions aligned | OWNER GATE |
| D-02 | Protected integration branches | Repository owner/admin → all four repositories | Ensures reviewed and checked changes reach `main` | Read-back of required rulesets/checks on each default branch | OWNER GATE |
| D-03 | HUB authenticated, versioned contracts | HUB → EL_AI / optional EL_AGENT / approved consumers | Shared private workflows and intelligence must not create ambient trust | Consumer contract tests, scope-negative tests, compatibility matrix, revocation and audit evidence | OPEN |
| D-04 | Telegram test environment | EL_AI configuration + test-bot operator → E10 acceptance | Allows safe real transport acceptance without production messaging | Test identity, isolated credentials, controlled update/send tests, redacted evidence, disable procedure | OWNER GATE |
| D-05 | Physical Windows/Android devices | Device operator → EL_AGENT | Hosted CI cannot prove real-device permissions, UX, offline and recovery behavior | Device/OS matrix and signed acceptance record | OWNER GATE |
| D-06 | Legal and privacy decisions | Ecosystem owner / qualified adviser → all products | Licensing, notices, data processing and public-service terms are owner/legal decisions | Written review outcome and approved public-facing documents | OWNER GATE |
| D-07 | Billing and deployment authorization | Account/billing owner → optional Render/cloud deployment | Prevents unapproved recurring cost and external side effects | Current provider plan, exact recurring charges, auto-sync state, explicit approval | OWNER GATE |
| D-08 | Backup and encryption-key custody | HUB operator → HUB recovery | Encrypted workflow payloads require the matching key during restoration | Isolated restore drill proving database/key pairing and integrity | OPEN |
| D-09 | Cross-repository source compatibility | Each provider repository → each consumer repository | Prevents stale pins and schema/API mismatch | Exact source SHAs, contract fixtures, consumer tests and revalidated deployment pins | OPEN |
| D-10 | Representative product metrics | Product owner → G0/G1 review | Numeric targets must be based on real usage rather than invented values | Agreed measurement period, baseline, metric definition and privacy-safe source | OWNER GATE |

## 4. Review and escalation

- Review all P0/P1 risks before every release candidate and any production-impacting action.
- Reconcile P2 risks during milestone planning and at least once per portfolio checkpoint.
- Every update must record **date, editor/role, changed field, evidence link, and reason** in the relevant PR or checkpoint.
- Escalate immediately when a risk crosses into unauthorized access/data disclosure, unapproved recurring cost, unrecoverable data loss, or an irreversible production action.
- Do not downgrade a risk solely because a mitigation PR was opened; require merged code/configuration and relevant verification evidence.
- Keep the small summary table in the G0–G12 document synchronized with this detailed register.

## 5. Change log

| Date | Change | Evidence |
|---|---|---|
| 2026-11-27 | Initial centralized G9 register created from the four-product governance baseline, repository status evidence, HUB operating guidance and documented owner gates; R-13/R-14 added for G2/G3 traceability and ADR consistency | [G0–G12 baseline](../GOVERNANCE_PRODUCT_STRATEGY_G0_G12.md), [HUB project status](../PROJECT_STATUS.md), [HUB README](../../README.md), [HUB copyright notice](../../COPYRIGHT.md), [four-product phase inventory](../roadmap/FOUR_PRODUCT_TECHNICAL_PHASES.md) |
