# Product Strategy — G0 Vision & G1 Product Strategy

- **Date:** 2026-11-27
- **Status:** Draft strategy baseline derived from the owner's four-product architecture; measurable targets require owner approval.
- **Authority:** [ADR-0047](../architecture/decisions/ADR-0047-four-product-ecosystem-scope-and-telegram-ownership.md)
- **Governance:** [G0–G12](../GOVERNANCE_PRODUCT_STRATEGY_G0_G12.md)

## G0 — Vision & Mission

### Vision

A coherent, trustworthy personal AI ecosystem in which central intelligence, a personal conversational agent, independent local device execution and a public digital workspace work together through clear, user-controlled boundaries.

### Mission

Deliver an extensible AI environment that helps its owner understand goals, plan and complete useful work, interact naturally through Telegram and other interfaces, execute explicitly authorized local actions on Windows and Android, and publish a useful public learning and development workspace—while preserving privacy, security, transparency, local-first choice and verifiable outcomes.

### Product principles / values

1. **Owner control:** consequential actions, external publication, spending, destructive operations and production changes remain behind explicit approval.
2. **Evidence over claims:** distinguish source implementation, automated tests, integration, live operation, device acceptance and production release.
3. **Privacy by boundary:** public, private, channel, device-local and shared data have explicit owners and permitted flows.
4. **Least privilege:** identity, capabilities, scopes, expiry, revocation, bounded input/output and audit are required at trust boundaries.
5. **Local-first and hybrid by choice:** local execution is preferred when feasible; remote providers are explicit, replaceable and cost-visible.
6. **Modularity without needless services:** logical boundaries and versioned contracts matter more than microservice count.
7. **Recoverability:** workflows and devices expose clear state, cancellation, safe retries, checkpoints and unknown outcomes.
8. **Accessibility and clarity:** Persian-first/RTL support where relevant, multilingual readiness, keyboard and assistive-technology access, truthful status.
9. **Responsible evolution:** new models, providers, tools and workflows must pass quality, security, cost and compatibility review.

### Long-term strategic outcomes

- One authoritative intelligence/control plane without duplicating policy, memory or durable workflow ownership.
- One personal conversational product, with the ecosystem Telegram bot owned inside EL_AI.
- A device agent that remains useful without HUB, internet or remote inference.
- A public digital platform that clearly separates public services from private owner capabilities.
- Replaceable model/provider/tool adapters and versioned inter-product contracts.
- A measurable, secure delivery lifecycle covering planning through verification and recovery.

### Short-term outcomes (next portfolio increment)

1. Adopt the four-product scope in ADR-0047 and remove active planning ambiguity.
2. Complete requirements, actor/use-case catalogue and RACI.
3. Publish and sequence the new four-product technical phase inventory.
4. Reconcile each repository's current mainline source, tests, dependencies and release evidence against that inventory.
5. Close high-priority integration and security gaps before expanding capability count.
6. Establish branch protection and release evidence as operating controls.
7. Keep live Telegram, physical-device, paid infrastructure and production actions separately authorized and verified.

### Outcome metrics — definitions first, target values pending owner review

Numeric SLOs must be set only after capturing a baseline over a representative period. The following metrics are the proposed measurement contract:

| Metric | Definition | Owner / source |
|---|---|---|
| Verified task completion rate | Completed Work Orders with trusted evidence / eligible Work Orders | HUB workflow/evaluator records |
| Unauthorized action prevention | Denied out-of-scope actions / observed authorization-denial test cases; any successful unauthorized action is a release blocker | Each capability owner; security tests/audit |
| Recovery correctness | Recoverable interrupted workflows restored to a valid terminal or checkpoint state / injected recovery scenarios | HUB and EL_AGENT recovery tests |
| Cross-product contract compatibility | Consumer contract cases passing for every supported contract version / executed cases | Contract CI in producer and consumer repos |
| Local independence | Defined core device tasks completed with HUB/cloud/network disabled / eligible offline acceptance tasks | EL_AGENT automated and physical-device tests |
| Telegram delivery integrity | Confirmed deliveries, duplicates, quarantined ambiguous outcomes and loss rate, separated by state | EL_AI Telegram adapter and delivery records |
| Public experience quality | Core user journeys passing responsive, accessibility, SEO and browser-quality gates | MR_SIAVASH_AI CI and browser acceptance |
| Security remediation time | Time from confirmed severity assignment to verified closure | Independent Security Program register |
| Cost per verified outcome | Provider/infrastructure cost / successfully verified eligible outcome | HUB cost telemetry and owner-approved billing evidence |

**Target policy:** do not invent percentage or latency goals before workload and baseline data exist. Establish the data collection contract, collect a representative baseline, then approve numeric SLOs with the owner.

## G1 — Product Strategy

### Product portfolio

| Product | Primary user / actor | Value proposition | Core success outcome |
|---|---|---|---|
| MR_SIAVASH_HUB_AI | Ecosystem owner/operator and authorized product consumers | A central intelligence and orchestration platform for planning, decisions, memory, capabilities, workflows and evidence | Owner-authorized goals become recoverable, evidence-backed outcomes |
| MR_SIAVASH_EL_AI | Ecosystem owner using the personal assistant; separately authorized Telegram contacts/customers only where a product feature explicitly enables them | A Persian-capable conversational agent and dedicated Telegram bot with clear identity, privacy and access modes | Correct, bounded and traceable conversations and task delegation |
| MR_SIAVASH_EL_AGENT | Device owner on Windows and Android | Independent local execution, local models/providers, scheduler and approved device capabilities | Useful local tasks remain available offline and sensitive actions remain owner-controlled |
| MR_SIAVASH_AI | Public visitors, learners and developers | Digital identity, portfolio, learning, development workspace and public AI services | Visitors find trustworthy evidence, learn and use public tools without private-data exposure |

### Product boundaries and non-goals

- HUB is not a Telegram UI, public website or unrestricted remote-control shell.
- EL_AI is not the global policy authority or a competing durable workflow database.
- EL_AGENT is not a mandatory HUB thin client; it must remain independently useful.
- MR_SIAVASH_AI is not a private HUB mirror or owner-runtime dashboard.
- The ecosystem does not require one deployable service per logical architecture layer.
- `MR_SIAVASH_EL_IR_BOT` is outside active product scope. No current roadmap or phase may assign it work.

### Product positioning

- **HUB:** private central intelligence and operating control plane.
- **EL_AI:** personal assistant and Telegram interaction product.
- **EL_AGENT:** local/device execution product.
- **MR_SIAVASH_AI:** public digital platform and AI workspace.

### Portfolio prioritization

1. Trustworthy foundations, governance, identity, policy, recovery and observability.
2. Complete the core value paths already under development in each product.
3. Close inter-product contracts and end-to-end acceptance gaps.
4. Expand specialist capabilities only when supported by usage, evaluation and cost evidence.
5. Add multi-user/business-facing capabilities only as explicit product decisions, with separate actor contexts and permissions.

### G0/G1 acceptance

- The four product identities and owners match ADR-0047.
- The mission, principles, short/long-term outcomes and product positioning are recorded.
- Proposed metrics have clear definitions and sources.
- Numeric targets, priority trade-offs and audience expansion are recorded as owner-approved decisions rather than silently assumed.
- No product is described as production-ready solely from source code or CI.
