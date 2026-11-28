# Product Portfolio & Capability Catalogue — G10

- **Baseline:** 2026-11-27
- **Portfolio authority:** [ADR-0051](../architecture/decisions/ADR-0051-four-product-ecosystem-scope-and-telegram-ownership.md)
- **Strategy:** [G0/G1 Product Strategy](PRODUCT_STRATEGY_G0_G1.md)
- **Requirements:** [G2 Requirements](../requirements/ECOSYSTEM_REQUIREMENTS.md)
- **Use Cases:** [G3 Use Cases](../architecture/USE_CASE_CATALOG.md)
- **Technical phases:** [76-phase inventory](../roadmap/FOUR_PRODUCT_TECHNICAL_PHASES.md)
- **Status:** Initial capability catalogue; ownership is defined at product/role level, and capability-level product outcomes/priorities require ongoing owner review

## 1. Purpose and portfolio model

This document is the G10 index of products and capability families. It makes the product portfolio actionable without duplicating the detailed technical phase inventory.

Use the following distinctions:

- **Product:** an independently owned user-facing or platform outcome, with its own repository and operational boundary.
- **Capability:** a coherent outcome or service family owned by one product; a capability may span multiple technical phases.
- **Technical phase:** an implementation/acceptance slice in the 76-phase inventory (H/E/D/A/X).
- **Work Order:** a bounded delivery item with one accountable owner, acceptance criteria and exact evidence.
- **Release:** an accepted set of changes promoted to a named environment/version under the G11 release gates.

A product is not complete merely because all of its capability families have a row in this catalogue. A capability is not Done merely because a technical phase has code or an open PR.

## 2. Canonical product portfolio

| Product | Primary actors | Product promise / outcome | Capability authority | Explicit boundary |
|---|---|---|---|---|
| **MR_SIAVASH_HUB_AI** | Ecosystem owner/operator; authenticated product consumers | Turn owner goals into planned, authorized, durable and evidence-backed outcomes | Shared intelligence, planning, workflows, private memory, policy, approvals, evidence and portfolio coordination | Not the Telegram UI, public website or arbitrary device-control shell |
| **MR_SIAVASH_EL_AI** | Owner through personal assistant; separately enabled contacts only under distinct permissions | Provide a Persian-capable conversational agent and the ecosystem Telegram experience with clear actor identity and truthful delivery state | Conversation, Telegram lifecycle, identity mapping, commands, message/media handling and user-facing delivery | Not the global policy authority, private-memory database or duplicate workflow engine |
| **MR_SIAVASH_EL_AGENT** | Device owner on Windows and Android | Provide useful local-first device capabilities that remain independent of HUB, network and cloud availability | Device-local identity/state, policy, scheduler, local provider routing, platform adapters and bounded actions | Not a mandatory HUB thin client, Telegram transport or unrestricted remote-control agent |
| **MR_SIAVASH_AI** | Public visitors, learners and developers | Provide digital identity, public information, learning/workspace modules and bounded public services | Public site, portfolio, education, public Gateway/content and browser-local experiences | Not a mirror of private HUB memory, credentials, task state or device controls |

The current portfolio contains these four products only. The former `MR_SIAVASH_EL_IR_BOT` repository is excluded from active scope; Telegram belongs inside EL_AI.

## 3. Capability catalogue

The rows below define stable portfolio-level capability IDs. Technical phase status, current source evidence and acceptance gates remain authoritative in [FOUR_PRODUCT_TECHNICAL_PHASES.md](../roadmap/FOUR_PRODUCT_TECHNICAL_PHASES.md). The “priority posture” is a planning recommendation, not an owner-approved delivery commitment.

### 3.1 HUB — central intelligence and orchestration

| Capability ID | Capability family | Technical phases | Requirement / use case references | Outcome | Priority posture |
|---|---|---|---|---|---|
| CAP-HUB-01 | Goal understanding, planning and strategy | H2–H5 | FR-HUB-01; UC-01 | A goal becomes a bounded, dependency-aware plan with visible assumptions and risk | P1 — core path |
| CAP-HUB-02 | Durable workflow execution and recovery | H1, H7, H8, H16 | FR-HUB-02; UC-02 | Approved work executes with stable state, cancellation, checkpoints and safe recovery | P1 — core path |
| CAP-HUB-03 | Identity, authorization, policy and approvals | H11; X2 | FR-HUB-03/04; UC-01/02/07/10 | Only the correct actor, scope and current approval can authorize a capability | P0/P1 — trust foundation |
| CAP-HUB-04 | Private memory and knowledge | H9, H16 | FR-HUB-04; UC-02/11 | Owner memory and workflow context remain private, attributable and controllable | P1 — trust foundation |
| CAP-HUB-05 | Evidence evaluation and verified completion | H10 | FR-HUB-06; UC-02/12 | Completion decisions rely on trusted, current, criterion-bound evidence | P1 — trust foundation |
| CAP-HUB-06 | Capability registry and provider/model routing | H6, H14 | FR-HUB-05; UC-11 | Tools and providers are replaceable, versioned, permissioned and budgeted | P1 — platform foundation |
| CAP-HUB-07 | Observability, operations and control center | H15, H17, H18 | FR-HUB-07; UC-12 | Operators can see task state, health, costs and failures without secret/payload leakage | P1 — operating foundation |
| CAP-HUB-08 | Quality, release and bounded research | H19, H20 | NFR-SEC-01, NFR-REC-01; UC-12 | Changes are testable, recoverable and safely evaluated before broader autonomy | P2 — gated evolution |

### 3.2 EL_AI — personal assistant and Telegram

| Capability ID | Capability family | Technical phases | Requirement / use case references | Outcome | Priority posture |
|---|---|---|---|---|---|
| CAP-ELAI-01 | Identity, pairing, actor and conversation context | E1, E2, E13 | FR-ELAI-01/03/07; UC-03 | Owner, public and optional customer contexts remain distinct | P0/P1 — trust foundation |
| CAP-ELAI-02 | Intent, command routing and plan preview | E3, E4 | FR-ELAI-06; UC-01/03 | Requests become explainable plans without implicit execution | P1 — core path |
| CAP-ELAI-03 | HUB task submission and evidence-aware result handling | E5, E8 | FR-ELAI-03/06; UC-01/02 | Task handoff is scoped, idempotent and reports execution separately from goal satisfaction | P1 — core integration |
| CAP-ELAI-04 | Telegram transport, update intake and delivery state | E10 | FR-ELAI-02/04/05; UC-03/04 | Telegram updates and outbound messages have validated, deduplicated and truthful states | P1 — core channel |
| CAP-ELAI-05 | Approved capability discovery and model/provider selection | E6, E9 | FR-ELAI-06; UC-03/11 | Each route is scope-checked, budgeted and explicitly configured | P2 — capability expansion |
| CAP-ELAI-06 | Bounded autonomy and continuation controls | E12 | FR-ELAI-06; UC-02/03 | Pause, resume, deadlines, budgets and grants are revalidated at continuation points | P1 — safety foundation |
| CAP-ELAI-07 | Security, operations and release acceptance | E13, E14 | FR-ELAI-01/07; NFR-PRIV-01; UC-03/12 | Conversation and channel operation remain auditable and independently accepted | P1 — release foundation |

### 3.3 EL_AGENT — independent local/device execution

| Capability ID | Capability family | Technical phases | Requirement / use case references | Outcome | Priority posture |
|---|---|---|---|---|---|
| CAP-AGENT-01 | Local runtime, identity and deterministic action policy | D0–D4 | FR-AGENT-02/04/07; UC-05/06 | Local actions are typed, bounded, allowlisted, recoverable and owner-controlled | P0/P1 — trust foundation |
| CAP-AGENT-02 | Local/cloud provider abstraction and offline planning | D5, D6 | FR-AGENT-01/03/05; UC-06 | Core local operation remains useful without hidden cloud fallback | P1 — product independence |
| CAP-AGENT-03 | Windows desktop tools and control center | D7, D12 | FR-AGENT-02/07; UC-05/06 | Approved Windows actions expose clear confirmation and observed outcomes | P1 — platform path |
| CAP-AGENT-04 | Android companion and platform adapters | D8, D12 | FR-AGENT-01/02/07; UC-05/06 | Android capabilities respect OS permissions, foreground limits and physical-device behavior | P1 — platform path |
| CAP-AGENT-05 | Voice and device-local memory | D9, D10 | FR-AGENT-05; NFR-PRIV-01; UC-06 | Local voice and memory are explicit, bounded and private by default | P2 — capability expansion |
| CAP-AGENT-06 | Optional HUB pairing and typed task relay | D11; X1, X2, X9 | FR-AGENT-06; UC-07 | HUB integration is revocable and optional; local policy remains authoritative | P2 — integration |
| CAP-AGENT-07 | Device security, release and physical acceptance | D13, D14 | NFR-SEC-01/02; NFR-REC-01; UC-05/12 | Packages, updates, rollback and physical-device support are verifiable | P1 — release foundation |

### 3.4 MR_SIAVASH_AI — public digital platform

| Capability ID | Capability family | Technical phases | Requirement / use case references | Outcome | Priority posture |
|---|---|---|---|---|---|
| CAP-WEB-01 | Digital identity, navigation and learning workspace | A0–A4 | FR-WEB-01/04; UC-09 | Visitors can find accurate public information and use learning/workspace experiences | P1 — core public path |
| CAP-WEB-02 | Public assistant and Gateway boundary | A5–A7 | FR-WEB-02/03; NFR-PRIV-01; UC-08 | Public queries use disclosed, approved public context and never proxy private HUB state | P0/P1 — trust foundation |
| CAP-WEB-03 | Admin, editorial workflow and publishing | A8, A9 | FR-WEB-05; UC-10 | Authenticated content changes follow review, approval, audit and rollback rules | P1 — controlled operations |
| CAP-WEB-04 | Public tools and external integrations | A10, A11 | FR-WEB-06; UC-08/09/10 | Public tools are bounded and integrations disclose scopes and failure states | P2 — capability expansion |
| CAP-WEB-05 | Consent-based analytics, support and CRM | A12 | FR-WEB-05; NFR-PRIV-01; UC-10 | Data collection and retention are explicit, minimized and controllable | P1 — privacy gate |
| CAP-WEB-06 | Security, accessibility, performance and SEO | A13 | NFR-SEC-02, NFR-ACC-01, NFR-I18N-01, NFR-PERF-01 | Public journeys remain usable, fast, accessible and hardened | P1 — release foundation |
| CAP-WEB-07 | Public release and operational readiness | A14 | NFR-REC-01; UC-12 | Release provenance, live health, migration, backup and rollback are verified | P1 — release gate |

### 3.5 Shared contracts and cross-product platform

| Capability ID | Capability family | Technical phases | Requirement references | Outcome |
|---|---|---|---|---|
| CAP-X-01 | Versioned schemas and contract compatibility | X1 | FR-X-01/02 | Consumers and producers agree on typed, versioned message and data contracts |
| CAP-X-02 | Service identity, pairing, scopes and revocation | X2 | FR-X-01/04 | Cross-product access is authenticated, least-privilege and revocable |
| CAP-X-03 | Permissioned shared memory/knowledge | X3 | FR-X-02 | Data ownership and provenance are preserved across explicit sharing |
| CAP-X-04 | Agent/device/capability registry | X4, X5 | FR-X-01/02 | Registered capabilities carry ownership, trust, lifecycle and permission metadata |
| CAP-X-05 | Model/provider and budget contracts | X6 | FR-X-01, NFR-COST-01 | Providers are substitutable and routing/cost consent is explicit |
| CAP-X-06 | Correlation, observability and health vocabulary | X7 | FR-X-03, NFR-OBS-01 | Cross-product operation state is observable without exposing sensitive data |
| CAP-X-07 | Security baseline and independent assurance | X8 | FR-X-02/04, NFR-SEC-01/02/03 | Trust boundaries are tested and independently reviewed |
| CAP-X-08 | Workflow, event and task relay | X9 | FR-X-03/04 | Cross-product handoffs handle idempotency, expiry, cancellation and unknown outcomes |
| CAP-X-09 | Portfolio visibility and release metadata | X10 | FR-X-03 | Owners can distinguish source, CI, live, device and release evidence |

## 4. Portfolio lifecycle

A capability moves through these states. Status must be backed by evidence and must not be inferred from roadmap position.

| State | Meaning | Minimum entry/exit evidence |
|---|---|---|
| DISCOVERY | Need or opportunity is being understood | Actor, problem, product fit, constraints and evidence source |
| PROPOSED | Capability is described but not approved for delivery | Stable capability ID, intended outcome, owner, non-goals and rough dependencies |
| READY | Bounded work can start | Linked requirements, phase, Work Order, acceptance, risk and prerequisites |
| IN_PROGRESS | Implementation is active | Branch/PR or named operational task, source SHA and progress evidence |
| VERIFY | Candidate is under verification | Exact candidate SHA, required tests, review and manual gates |
| ACCEPTED | Acceptance criteria have passed | Named reviewer, exact evidence, residual risk and decision date |
| RELEASED | Accepted capability is enabled in an identified environment/version | Release record, source/artifact identity and post-release verification |
| DEFERRED / RETIRED | Capability is postponed, replaced or removed from active use | Reason, owner decision, migration/deprecation path and dependent consumer notice |

## 5. Prioritization and portfolio balancing

Priorities are assigned to bounded Work Orders, not to a whole product as a label. The following rules are the default decision framework; final product strategy and major priority trade-offs remain with the ecosystem owner.

### Priority classes

- **P0 — Stop-the-line:** credible unauthorized access/action, private-data leakage, unrecoverable data loss, critical supply-chain compromise or irreversible production risk. Stop the affected release/action and escalate.
- **P1 — Foundation / blocker:** identity, policy, recovery, contract compatibility, high-impact defect, or prerequisite that blocks a core value path or release.
- **P2 — Core value / quality:** improves a core user journey, observability, maintainability or product completeness after P0/P1 gates.
- **P3 — Exploration / enhancement:** optional experiments, broad capability expansion or polish without a current critical dependency.

### Ranking rules within a priority class

Compare each candidate using the following evidence, without inventing a single numeric score:

1. **User outcome:** Which actor task or measurable outcome improves?
2. **Risk reduction:** Which security, privacy, reliability or recovery risk is removed?
3. **Dependency leverage:** How many blocked phases/consumers become unblocked?
4. **Evidence confidence:** Are source, user need, test and operational facts current and reproducible?
5. **Cost and effort:** What engineering effort, provider cost, migration and support burden are introduced?
6. **Reversibility:** Can the change be disabled, rolled back or replaced safely?

Prefer work that removes a P0/P1 blocker or unlocks a verified core path. Do not prioritize by feature count, PR count, model novelty or optimistic percentage estimates.

### Mandatory portfolio constraints

- Security/privacy/trust gates cannot be traded away for feature velocity.
- Product ownership cannot be moved by implementation convenience; use an ADR for material boundary changes.
- Paid infrastructure, external publication, live messaging and production mutations remain explicit owner decisions.
- EL_AGENT core functionality must not become dependent on HUB/cloud availability.
- The public Website must never gain access to private HUB memory, owner credentials or device-control authority.
- One logical architecture layer does not imply one deployable service.
- Numeric SLOs are approved only after representative baseline measurements.

## 6. Portfolio review cadence and change control

At each portfolio checkpoint:

- Refresh each product's exact default-branch SHA and open PR/issue state.
- Reconcile capability/phase posture from source and exact-head CI, not older README snapshots.
- Review P0/P1 risks and external dependencies.
- Reassess capability priority where evidence, costs, user outcomes or dependencies changed.
- Keep capability IDs stable. Split or materially change a capability through a recorded change decision rather than silently reusing the ID.
- Record portfolio decisions in the G11 milestone register and link to the owning Work Order/ADR.

A newly proposed capability enters active delivery only after it has an owner, capability ID, product boundary, requirement/use-case links, technical phase, Work Order, acceptance criteria and G9 risk review.

## 7. G10 acceptance

G10 remains IN_PROGRESS until the portfolio owner and product maintainers have:

1. Reviewed the product promises, actors and non-goals.
2. Confirmed capability IDs and accountable product ownership.
3. Accepted the priority framework and recorded material trade-offs.
4. Linked all active capabilities to technical phases, requirements/use cases and Work Orders.
5. Reconciled capability maturity against exact source/CI and any applicable live/device evidence.
6. Identified duplicates, obsolete capabilities and dependencies for defer/retire decisions.

This document establishes a stable portfolio catalogue. It does not declare every capability implemented, prioritized, accepted or released.
