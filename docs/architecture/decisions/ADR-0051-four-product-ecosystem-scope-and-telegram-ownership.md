# ADR-0051 — Four-product ecosystem scope and Telegram ownership

- **Status:** Accepted by the ecosystem owner; repository integration pending review
- **Date:** 2026-11-27
- **Decision owner:** MR_SIAVASH ecosystem owner
- **Supersedes:** ADR-0046 for current and future portfolio scope; supersedes the product-taxonomy and legacy-Bridge assumptions in proposed ADR-0050
- **Scope:** HUB, EL_AI, EL_AGENT, and MR_SIAVASH_AI

## Context

The portfolio has accumulated conflicting scope statements. ADR-0046 and proposed ADR-0050 treated `MR_SIAVASH_EL_IR_BOT` as a separate active Telegram Bridge repository and placed `MR_SIAVASH_EL_AGENT` outside the active four-repository execution set. The current owner-approved product architecture explicitly defines a different four-product portfolio and places the dedicated Telegram bot inside `MR_SIAVASH_EL_AI`.

The four products have distinct responsibilities. They are product and repository boundaries, not a requirement to deploy every logical layer as a separate service.

## Decision

### 1. Canonical active portfolio

The active ecosystem consists of exactly these four repositories:

| Product | Primary responsibility | Canonical authority |
|---|---|---|
| `MR_SIAVASH_HUB_AI` | Central intelligence, planning, decisions, workflows, orchestration, shared owner memory, capabilities, policy and audit | Cross-product private intelligence and control plane |
| `MR_SIAVASH_EL_AI` | Personal conversational agent, identity, personalization, Telegram bot, conversation and user-facing delivery | Telegram/channel interaction and personal-agent experience |
| `MR_SIAVASH_EL_AGENT` | Local and device execution runtime for Windows and Android, with independent local state and bounded device capabilities | Device-local execution and policy boundary |
| `MR_SIAVASH_AI` | Digital identity, public website, AI workspace, learning/development experience, public services and public Gateway | Public-facing product and public data boundary |

### 2. Explicit exclusion of EL_IR_BOT

`MR_SIAVASH_EL_IR_BOT` is outside this portfolio and outside the active execution map.

- It is not a fifth product, an active dependency, a Telegram transport service, a queue owner, a migration source, or a phase owner for this plan.
- No B0–B11 work is scheduled under the current portfolio.
- This ADR does not authorize reading, changing, deploying, migrating, archiving, or deleting that repository or its infrastructure.
- Historical references and previously recorded evidence remain historical records; they do not create current execution scope.
- Reintroducing that repository requires a new explicit owner decision and a superseding ADR.

### 3. Telegram belongs inside EL_AI

The ecosystem's dedicated Telegram bot is developed and owned within `MR_SIAVASH_EL_AI`.

EL_AI owns the Telegram-specific lifecycle and user experience, including transport adapters, update intake, Telegram identity mapping, commands, conversation, channel/session state, message/media normalization, delivery, retries and delivery-state handling. These are EL_AI implementation responsibilities even if internal modules, workers or separate deployment processes are later justified.

No separate `MR_SIAVASH_EL_IR_BOT` repository or external Bridge is assumed by the architecture. The exact internal topology remains an EL_AI implementation decision subject to versioned contracts, bounded execution, observability, privacy, security and release gates.

### 4. Product authority and integration boundaries

- **HUB:** authoritative for cross-product planning and orchestration, private owner memory, durable tasks/workflows, policy, approvals, capability registry, evidence and audit.
- **EL_AI:** owns conversation, Telegram identity/channel operations and user-facing delivery. It delegates privileged or durable cross-product work to HUB through authenticated, scoped and versioned interfaces.
- **EL_AGENT:** remains a standalone Windows/Android local execution runtime. HUB integration is optional and must not be required for basic local operation. Model output is proposal data; deterministic local policy authorizes actions.
- **MR_SIAVASH_AI:** owns public digital identity, public workspace, learning/development experience, public content and public Gateway. It does not inherit private HUB memory, credentials, task state or device-control authority.

No shared database, ambient trust, implicit permission inheritance or unrestricted forwarding of private context is introduced.

### 5. Logical architecture and security program

The ecosystem uses the logical layers recorded in `docs/GOVERNANCE_PRODUCT_STRATEGY_G0_G12.md`:

1. Interaction & Experience
2. Personal Agent
3. Central Intelligence
4. AI Intelligence
5. Capability
6. Data & Knowledge
7. Execution
8. Shared Infrastructure

These are responsibility boundaries, not a mandated microservice topology. A modular monolith or a small number of deployable processes is preferred until operational evidence justifies separation.

An independent Security Program overlays all products and layers. It owns security architecture, defensive cyber assurance, AI safety, audit, threat modelling and security verification. It is an assurance workstream, not a fifth product repository.

### 6. Active roadmap and phase accounting

- G0–G12 (Governance & Product Strategy) is the prerequisite governance program for the active four-product portfolio.
- The former 73-phase baseline and PAIOS execution roadmap contain EL_IR_BOT-specific scope and are retained for historical traceability only until a revised four-product technical phase inventory is accepted.
- The new technical phase inventory must include a dedicated EL_AGENT workstream and assign Telegram-specific implementation to EL_AI.
- No phase is complete merely because source code exists, a branch exists, a PR is open, or CI passed. Completion requires the phase's own acceptance evidence and the required mainline integration.
- Historical B-phase evidence must not be relabelled as EL_AI completion without independently verifying the corresponding EL_AI implementation and acceptance criteria.

## Consequences

- The current product taxonomy is unambiguous and aligned to the owner's latest architecture.
- EL_AI is the sole in-scope owner of the ecosystem Telegram bot.
- EL_AGENT is a first-class product, not an auxiliary or fifth repository.
- HUB remains the central intelligence and policy authority without becoming the owner of every transport or device implementation.
- The former 73-phase count is not a valid active portfolio count; it must be replaced after G0–G12 establish requirements, use cases, ownership and dependencies.
- All cross-product contracts and status reports must use these four product identities and must separately report source, CI, integration, device and production evidence.

## Non-goals

This ADR does not authorize production deployment, Telegram webhook registration, live message sending, remote device actions, cloud-resource provisioning, paid infrastructure, secret changes, destructive operations, or legal claims. Those require their own operational preflight, authorization and evidence.
