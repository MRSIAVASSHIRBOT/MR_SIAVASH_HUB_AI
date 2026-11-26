# Ecosystem Governance & Product Strategy — G0–G12

- **Baseline date:** 2026-11-27
- **Portfolio:** four canonical products
- **Canonical home:** `MR_SIAVASH_HUB_AI`
- **Status:** Initial evidence-based governance baseline; G0–G12 are not collectively complete
- **Decision reference:** [ADR-0047 — Four-product ecosystem scope and Telegram ownership](architecture/decisions/ADR-0047-four-product-ecosystem-scope-and-telegram-ownership.md)

## 1. Purpose and authority

This document establishes the governance and product-strategy layer that must precede scalable execution across the MR_SIAVASH ecosystem. It consolidates the owner's current product model, the G0–G12 governance phases, repository evidence, cross-project risks and the next acceptance gates.

This is a living governance baseline, not a claim that every product requirement, legal condition, runtime integration or release gate is already satisfied. Repository source, exact-commit CI, contract tests, live operational evidence and owner decisions remain separate sources of truth. A plan, branch, open PR or green CI run is not proof of production readiness.

The active portfolio and Telegram ownership are governed by ADR-0047. ADR-0046 is retained as historical evidence and is superseded for current and future portfolio scope.

## 2. Canonical ecosystem vision

Build a coherent personal AI ecosystem in which:

- HUB provides shared intelligence, planning, decision-making, orchestration, workflows, policy, memory and evidence.
- EL_AI provides a personal conversational agent and the ecosystem's Telegram bot, with identity, personalization and user-facing delivery.
- EL_AGENT provides independent, local-first execution on Windows and Android, with bounded device capabilities.
- MR_SIAVASH_AI provides digital identity, public website, AI workspace, learning/development experiences and public services.

The ecosystem should remain modular, replaceable, observable, privacy-preserving and cost-aware. Prefer local-first execution where practical and explicit hybrid routing where needed. Preserve clear public/private and model/tool/device trust boundaries. Do not introduce distributed services merely because the architecture has multiple logical layers.

A proposed mission, principles, strategic outcomes, product positioning and metric definitions are now documented in [Product Strategy G0/G1](product/PRODUCT_STRATEGY_G0_G1.md). Numeric SLO targets and final priority trade-offs remain owner-review decisions; they are not invented from insufficient usage data.

## 3. Canonical product portfolio and ownership

| Product | Product role | Owns | Must not become |
|---|---|---|---|
| `MR_SIAVASH_HUB_AI` | Central intelligence and orchestration | GPI/AWI/CGI, decisions, workflows, orchestration, shared private memory/knowledge, policy, approvals, tools/skills registry, audit and cross-product task state | Telegram UI, public website, or platform-specific device implementation |
| `MR_SIAVASH_EL_AI` | Personal AI agent and Telegram bot | Identity, conversation, personalization, Telegram transport/update intake, command routing, message/media handling, user-facing delivery and channel lifecycle | A competing global policy authority, private-memory database, or duplicate cross-product workflow engine |
| `MR_SIAVASH_EL_AGENT` | Local and device execution runtime | Windows/Android local runtime, device-local state, local policy, scheduler, local models/providers and bounded platform actions | A mandatory HUB thin-client or Telegram transport owner |
| `MR_SIAVASH_AI` | Digital platform and AI workspace | Digital identity, public site, public modules, learning, development workspace, public content and public Gateway | A mirror of private HUB memory, credential store, task state or device-control surface |

### Explicit portfolio exclusion

`MR_SIAVASH_EL_IR_BOT` is outside the current architecture, portfolio, repository work and phase plan. The Telegram bot is developed inside EL_AI. No separate legacy Bridge repository, edge transport service or B0–B11 workstream is assumed. Historical records may remain available as historical records; they do not authorize work on that repository.

## 4. Logical ecosystem architecture

The following layers define responsibilities and contracts. They do not prescribe a one-layer/one-service or microservice deployment model.

### 4.1 Interaction & Experience

**Surfaces:** Telegram, Web, Desktop, Android and API.

Owns channel-specific presentation and interaction. Identity and permissions are resolved by the service responsible for the relevant actor and trust boundary; a presentation surface does not grant authority.

### 4.2 Personal Agent — EL_AI

**Responsibilities:** Identity, conversation, personalization and Telegram.

Owns the conversational turn, Telegram lifecycle, user-facing command and response experience. Delegates shared private state, durable workflows and privileged capabilities to HUB through scoped, authenticated, versioned interfaces.

### 4.3 Central Intelligence — HUB

**Responsibilities:** GPI, AWI, CGI, decisions, workflows and orchestration.

Coordinates goals, context gathering, planning, dependency/risk analysis, policy checks, capability selection, authorized execution, evaluation, recovery and evidence-backed completion. HUB is the authoritative shared intelligence/control plane, not an unrestricted execution shell.

### 4.4 AI Intelligence

**Responsibilities:** Models, prompts, retrieval-augmented generation (RAG), context construction and evaluation.

Provider/model adapters remain replaceable. Model output is untrusted input to deterministic application policy. Routing, privacy disclosure, cost limits and local/cloud preference must be explicit.

### 4.5 Capability

**Responsibilities:** Tools, skills, extensions and plugins.

Capabilities declare ownership, schemas, permissions, data classification, failure behavior, version, resource limits and evidence requirements. Registry discovery does not itself authorize execution.

### 4.6 Data & Knowledge

**Responsibilities:** Memory, knowledge, application data and events.

Data ownership remains with the owning product. Private owner memory, public website knowledge, device-local state, conversational session state and workflow history remain distinguishable. Cross-product access uses versioned APIs/events with explicit scopes and provenance, never shared database files.

### 4.7 Execution

**Responsibilities:** Workers, bounded sandboxes and EL_AGENT.

HUB workers execute durable cross-product jobs under HUB policy. Sandboxes constrain tools and workloads. EL_AGENT executes approved device-local actions and remains useful without HUB, internet or cloud availability. No layer grants arbitrary shell, filesystem, network or remote-control access.

### 4.8 Shared Infrastructure

**Responsibilities:** Identity, data governance, APIs, observability, reliability and cost.

Infrastructure contracts cover service identity, authentication, scopes, version compatibility, correlation, idempotency, bounded retries, health/readiness, secrets, backup/recovery and cost visibility. Each product remains accountable for its own deployment and data.

### 4.9 Independent Security Program

Security is an independent, cross-cutting assurance program across all four products and every layer:

- Security architecture and trust-boundary review.
- Defensive cyber assurance and threat modelling.
- AI safety and model/tool boundary validation.
- Auditability, provenance and security evidence.
- Dependency, workflow, configuration and release assurance.
- Incident readiness, recovery, rollback and revocation.

The program is an independent workstream, not a fifth product or repository. Security-sensitive changes require negative tests and evidence; a passing static scan is not a complete security assessment.

## 5. Governance phases G0–G12

Status values:

- **PARTIAL** — useful artifacts or implementation exist, but material acceptance gaps remain.
- **IN_PROGRESS** — a specific change is being prepared; it is not merged or accepted yet.
- **OWNER ACTION REQUIRED** — an account, legal, financial, physical-device or operational decision cannot be inferred from source code or CI.
- **DONE** — all phase acceptance criteria and evidence are met. No G phase is declared DONE by this initial baseline.

| Phase | Title | Current status | Evidence already present | Next acceptance gate |
|---|---|---|---|---|
| G0 | Vision & Mission | IN_PROGRESS | Draft vision, mission, principles, outcomes and measurement definitions in [Product Strategy G0/G1](product/PRODUCT_STRATEGY_G0_G1.md) | Owner review of mission/values and numeric targets after a representative baseline |
| G1 | Product Strategy | IN_PROGRESS | Draft positioning, primary actors, value propositions, non-goals and metric definitions in [Product Strategy G0/G1](product/PRODUCT_STRATEGY_G0_G1.md) | Owner approval of audience expansion, portfolio priorities and numeric success targets |
| G2 | Requirements Engineering | IN_PROGRESS | Initial FR/NFR catalogue, priorities, owners and verification methods in [ECOSYSTEM_REQUIREMENTS.md](requirements/ECOSYSTEM_REQUIREMENTS.md) | Decompose each requirement into repository issues/Work Orders and verify implementation traceability |
| G3 | Use Case Architecture | IN_PROGRESS | Actor model and 12 primary/exception use cases in [USE_CASE_CATALOG.md](architecture/USE_CASE_CATALOG.md) | Add sequence diagrams and product-specific executable acceptance scenarios linked to tests |
| G4 | Ecosystem Architecture | IN_PROGRESS | PAIOS target architecture, logical module boundaries and integration contracts exist; ADR-0047 and this layer model update the portfolio boundary | Reconcile the target architecture and active roadmap with the four-product model; approve contract and data-flow diagrams |
| G5 | Project Ownership | IN_PROGRESS | Product capability owners and reserved owner decisions in [OWNERSHIP_RACI.md](governance/OWNERSHIP_RACI.md) | Owner validates named maintainers and release operators; mirror ownership into repo issue/PR templates |
| G6 | Repository Baseline | PARTIAL | Current main heads, root inventories, open PRs and latest mainline Actions observations were inspected for all four repositories | Complete per-repository code/architecture/dependency/configuration/test/deployment/live-runtime inventories and record evidence freshness |
| G7 | Engineering Standards | PARTIAL | HUB `AGENTS.md`, continuous execution standard, per-repository CI and security workflows exist | Apply and verify required branch protection/rulesets; align contribution, testing, review, dependency-lock and release standards across four repositories |
| G8 | Architecture Decisions | IN_PROGRESS | ADRs 0041–0047 and Website decisions 0001/0003/0004 exist; shared structure in [ADR_TEMPLATE.md](architecture/decisions/ADR_TEMPLATE.md) is now available | Review/merge ADR-0047; maintain a cross-product ADR index and record contract, data-ownership, security and deployment decisions before implementation |
| G9 | Risk & Dependency Register | IN_PROGRESS | Initial actionable register with stable risk/dependency IDs, likelihood, impact, accountable roles, mitigations and closure evidence in [ECOSYSTEM_RISK_DEPENDENCY_REGISTER.md](governance/ECOSYSTEM_RISK_DEPENDENCY_REGISTER.md) | Reconcile owners and ratings against fresh evidence; maintain P0/P1 review and record explicit accept/close decisions |
| G10 | Product Portfolio | IN_PROGRESS | 76-phase four-product technical inventory in [FOUR_PRODUCT_TECHNICAL_PHASES.md](roadmap/FOUR_PRODUCT_TECHNICAL_PHASES.md) | Audit each technical phase against exact mainline code/tests and publish prioritized Work Orders |
| G11 | Delivery Management | IN_PROGRESS | [Delivery lifecycle and release gates](management/DELIVERY_MANAGEMENT_STANDARD.md), [Work Order template](management/WORK_ORDER_TEMPLATE.md), and [initial governance Work Order registry](management/ECOSYSTEM_WORK_ORDERS.md), alongside the technical phase DoD | Adopt the lifecycle across repositories; assign named maintainers; create repository-level milestones and link exact-SHA evidence/release checkpoints |
| G12 | Legal & Operational Readiness | OWNER ACTION REQUIRED | Repository copyright/security documents and operational runbooks exist; several deployment and live-acceptance gates are explicitly separate from CI | Owner/legal review of IP, licenses, privacy/terms and data handling; confirm operational ownership, backup/incident plans, provider costs and live acceptance before production use |

### G-phase exit rule

A phase advances only when its deliverables are linked to source-of-truth artifacts, owners are assigned, dependencies are recorded, acceptance criteria are testable, and residual risks are explicit. A phase may contain parallel workstreams, but its acceptance gate remains evidence-based.

## 5.1 G0–G5 and G10–G11 deliverables

| Governance area | Canonical artefact | Purpose |
|---|---|---|
| G0/G1 | [Product Strategy](product/PRODUCT_STRATEGY_G0_G1.md) | Proposed mission, values, outcomes, product positioning and metric definitions |
| G2 | [Requirements Catalogue](requirements/ECOSYSTEM_REQUIREMENTS.md) | Cross-product functional and non-functional requirements with IDs and verification gates |
| G8 | [ADR Template](architecture/decisions/ADR_TEMPLATE.md) | Consistent architecture-decision context, options, owner approval, security/data-flow impact and verification record |
| G3 | [Use-Case Catalogue](architecture/USE_CASE_CATALOG.md) | Actors, primary flows, exceptions, privacy boundaries and acceptance conditions |
| G5 | [Ownership RACI](governance/OWNERSHIP_RACI.md) | Product capability ownership, reserved owner decisions and independent assurance |
| G9 | [Risk & Dependency Register](governance/ECOSYSTEM_RISK_DEPENDENCY_REGISTER.md) | Stable risk/dependency IDs, ratings, accountable roles, mitigations and closure gates |
| G10/G11 | [Four-Product Technical Phase Inventory](roadmap/FOUR_PRODUCT_TECHNICAL_PHASES.md) | 76 technical phases, dependencies, evidence posture and global Definition of Done |
| G11 | [Delivery Management Standard](management/DELIVERY_MANAGEMENT_STANDARD.md) | Work Order lifecycle, priority, milestone model, release gates and progress evidence |
| G11 | [Work Order Template](management/WORK_ORDER_TEMPLATE.md) and [Work Order Registry](management/ECOSYSTEM_WORK_ORDERS.md) | Reusable Work Order schema and initial owned governance backlog |

The technical inventory contains 21 HUB phases (H0–H20), 15 EL_AI phases (E0–E14), 15 EL_AGENT phases (D0–D14), 15 Website phases (A0–A14) and 10 shared phases (X1–X10). Governance phases G0–G12 are separately tracked. The inventory deliberately declares no phase globally DONE until its specific acceptance criteria and exact-mainline evidence are reconciled.

## 6. Repository and CI baseline — observed 2026-11-27

This is a GitHub source/CI snapshot. It does not establish live service, physical-device or production acceptance.

| Repository | Observed `main` SHA | Open PRs observed | Latest exact-main Actions observation |
|---|---|---:|---|
| HUB | `235d44c900540e193b9116bc982fe244400d9e66` | #637, #636, #618 (Draft) | 7 observed workflows succeeded: CI, Backend CI, Video Render Integration, Windows Launcher Validation, Workflow Security Audit, Defensive Python Scan and OpenSSF Scorecard |
| EL_AI | `234b81b6521413661799d3044c34697724016d8f` | 0 | CI, Workflow Security Audit and OpenSSF Scorecard succeeded |
| EL_AGENT | `9d830ef05468db90da39cf8572f73192bec00e0b` | 0 | CI and Android workflows succeeded |
| MR_SIAVASH_AI | `e55d4a04dd9d59e54c8c1fa13ef864117fae6c4c` | 0 | Quality/Pages, Gateway CI, Production and Preview Runtime Smoke, Workflow Security Audit and OpenSSF Scorecard succeeded |

Exact workflow run pages:
- [HUB mainline checks](https://github.com/MRSIAVASSHIRBOT/MR_SIAVASH_HUB_AI/actions)
- [EL_AI mainline checks](https://github.com/MRSIAVASSHIRBOT/MR_SIAVASH_EL_AI/actions)
- [EL_AGENT mainline checks](https://github.com/MRSIAVASSHIRBOT/MR_SIAVASH_EL_AGENT/actions)
- [MR_SIAVASH_AI mainline checks](https://github.com/MRSIAVASSHIRBOT/MR_SIAVASH_AI/actions)

### Repository governance finding

All four current `main` branches report `protected=false`. Existing owner/admin tracking issues are:

- [HUB #304](https://github.com/MRSIAVASSHIRBOT/MR_SIAVASH_HUB_AI/issues/304)
- [EL_AI #5](https://github.com/MRSIAVASSHIRBOT/MR_SIAVASH_EL_AI/issues/5)
- [EL_AGENT #27](https://github.com/MRSIAVASSHIRBOT/MR_SIAVASH_EL_AGENT/issues/27)
- [MR_SIAVASH_AI #70](https://github.com/MRSIAVASSHIRBOT/MR_SIAVASH_AI/issues/70)

No branch protection was changed by this baseline. The owner/admin must configure and independently verify required checks, PR review policy, force-push/deletion restrictions and any appropriate bypass rules. CI success does not compensate for unprotected main branches.

## 7. G9 risk summary — detailed register is authoritative

The canonical G9 record is the [Ecosystem Risk & Dependency Register](governance/ECOSYSTEM_RISK_DEPENDENCY_REGISTER.md). It owns stable risk IDs, likelihood/impact ratings, priorities, accountable roles, mitigation, cross-product dependencies and closure evidence. The summary below intentionally uses the same IDs and titles as that register; do not create a second competing risk ID space.

| ID | Risk summary | Priority / status | Next control |
|---|---|---|---|
| R-01 | Main-branch governance is not enforced across the four repositories | P1 / OWNER GATE | Owner/admin configures and independently verifies rulesets and exact required checks |
| R-02 | Four-product scope correction is not yet canonical on main | P1 / MITIGATING | Review and merge ADR-0047/G0–G12 and align current entry points |
| R-03 | CI evidence can be mistaken for live/runtime/production acceptance | P1 / OPEN | Keep source, CI, integration, device, external provider and deployment evidence distinct |
| R-04 | Cross-product identity, authorization or private-data boundaries can drift | P1 / OPEN | Maintain versioned least-privilege contracts and negative security tests |
| R-05 | Paid infrastructure may be provisioned before cost approval | P1 / OWNER GATE | Keep paid infrastructure draft/unprovisioned until explicit billing-owner approval |
| R-06 | Telegram end-to-end behavior remains short of live acceptance | P1 / OWNER GATE | Complete isolated E10 tests, then use a controlled non-production bot acceptance |
| R-07 | Windows/Android physical-device acceptance is not established by CI alone | P1 / OWNER GATE | Record supported device/OS matrix and physical acceptance evidence |
| R-08 | Legal/IP/privacy readiness is not independently approved | P1 / OWNER GATE | Obtain written owner/qualified-adviser review; do not claim legal compliance |
| R-09–R-14 | Workflow encryption-key recovery, reproducibility, evidence freshness, Work Order ownership, requirement traceability and ADR consistency | P1/P2 / OPEN or MITIGATING | Follow the detailed per-item mitigation and closure criteria in the canonical register |

The detailed register also defines dependencies D-01 through D-10. A mitigation PR or passing CI does not close a risk; closure requires its specified evidence and a dated review decision.



## 8. Delivery and change-control rules

The executable delivery workflow, milestone/release gates and Work Order fields are defined in the [G11 Delivery Management Standard](management/DELIVERY_MANAGEMENT_STANDARD.md), [Work Order Template](management/WORK_ORDER_TEMPLATE.md), and [Work Order Registry](management/ECOSYSTEM_WORK_ORDERS.md). These are the operational detail behind the concise rules below.

1. Read current repository instructions, mainline status, open PRs and relevant contracts before every change.
2. Make a focused change on a dedicated branch. Do not edit `main` directly.
3. Preserve user work and open PRs. Do not duplicate a feature already in progress.
4. State the owning product and the cross-product contract for each Work Order.
5. Add or update tests for behavior changes; use consumer-driven contract tests for cross-project APIs/events.
6. Report exact changed files, commit/PR identifiers, commands and test outcomes. Separate passed, failed, skipped and unavailable evidence.
7. Never treat an open PR, branch, generated document or passing CI as merged/accepted/released.
8. Keep production deployment, Telegram activation, device-side operations, secret changes, paid infrastructure, destructive actions and legal declarations behind their own owner authorization and operational preflight.
9. Reconcile roadmap status from current mainline evidence; preserve historical snapshots without presenting stale values as current.
10. Review the architecture at least every six months and after material changes to models, runtimes, providers, channels, data stores or deployment topology.

## 9. Immediate execution queue

1. **Merge the scope correction:** review ADR-0047 and this G0–G12 baseline; then make the four-product boundary the canonical portfolio source.
2. **Reconcile architecture docs:** apply the logical-layer model and ensure the PAIOS target architecture no longer treats EL_IR_BOT as an active component.
3. **Retire stale active-roadmap assumptions:** preserve the old 73-phase/legacy roadmap as historical evidence, but do not execute its B0–B11 or legacy migration tasks.
4. **Complete G0–G3:** approve measurable vision/product outcomes, requirements and actor-based use cases.
5. **Complete G6–G8:** deepen per-repository inventories, align and verify engineering standards, and review/record architecture decisions before dependent implementation.
6. **Operate G9–G11:** maintain the canonical risk register, reconcile the 76 technical phases against exact mainline evidence, and adopt the Work Order/milestone/release lifecycle across the four repositories.
7. **Close G12 owner actions:** legal/privacy/cost/operational review and real environment/device acceptance before any production-impacting release.

## 10. Evidence limitations

- The repository snapshot and workflow conclusions above are based on GitHub metadata and Actions results observed on 2026-11-27.
- No private environment values, credentials or secret contents were inspected.
- A successful workflow is evidence only for the checks that workflow performed.
- No live Telegram message flow, physical Windows/Android acceptance, remote database mutation, paid infrastructure provisioning or production deployment is claimed by this document.
- Legal ownership, license compatibility, privacy compliance and terms-of-service sufficiency have not been independently certified.
