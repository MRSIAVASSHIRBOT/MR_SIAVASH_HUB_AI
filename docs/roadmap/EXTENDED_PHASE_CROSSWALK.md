# Extended Ecosystem Phase Crosswalk

- **Baseline:** 2026-11-27
- **Purpose:** Map the owner's expanded G/H/E/L/A/X/I/ML phase taxonomy to the accepted four-product architecture without duplicating existing implementation.
- **Portfolio authority:** [ADR-0051](../architecture/decisions/ADR-0051-four-product-ecosystem-scope-and-telegram-ownership.md)
- **Governance baseline:** [G0–G12](../GOVERNANCE_PRODUCT_STRATEGY_G0_G12.md)
- **Current executable phase inventory:** [Four-product technical phases](FOUR_PRODUCT_TECHNICAL_PHASES.md)
- **Delivery policy:** [G11 delivery standard](../management/DELIVERY_MANAGEMENT_STANDARD.md)

## 1. Rules

The expanded taxonomy is accepted as a **capability decomposition and long-range roadmap**, not as permission to create duplicate services or rename existing phases in-place.

1. The four product boundaries remain unchanged: HUB owns central intelligence and shared private control plane; EL_AI owns Telegram and conversational delivery; EL_AGENT owns Windows/Android local execution; MR_SIAVASH_AI owns public website, workspace and Gateway.
2. The compact H0–H20 / E0–E14 / D0–D14 / A0–A14 / X1–X10 inventory remains the current implementation baseline. The expanded identifiers below are crosswalk identifiers. They do not overwrite compact identifiers or historical records.
3. An expanded phase is DONE only when its own requirements, source paths, tests, dependent-consumer acceptance and environment gates are evidenced. A mapped source file, planned task, open PR or green CI alone is insufficient.
4. Where a capability belongs to multiple products, one repository owns the implementation and other repositories own consumer compatibility tests. There is no shared database and no ambient cross-product trust.
5. Statuses are conservative: **PARTIAL** means some implementation exists but phase acceptance is incomplete; **EVIDENCE / ACCEPTANCE PENDING** means meaningful code exists but full acceptance is not reconciled; **PLANNED / GATED** means no sufficient phase-level implementation evidence was established; **OWNER / ENVIRONMENT GATE** means code alone cannot close the phase.
6. The Innovation Engine and Foundation Model Lab are programs hosted by HUB and its existing research/model boundaries, not additional products or repositories.

## 2. Governance G0–G12

The existing [G0–G12 governance baseline](../GOVERNANCE_PRODUCT_STRATEGY_G0_G12.md) is canonical and must not be duplicated.

| Phase | Initial status | Existing authority / next gate |
|---|---|---|
| G0 | IN_PROGRESS | Product Strategy G0/G1; owner review of mission, values and measurable targets |
| G1 | IN_PROGRESS | Product Strategy G0/G1; owner approval of audience, positioning and priorities |
| G2 | IN_PROGRESS | Requirements catalogue and requirement-to-use-case traceability |
| G3 | IN_PROGRESS | Use-case catalogue and sequence diagrams; reconcile with executable APIs and state transitions |
| G4 | IN_PROGRESS | ADR-0051, PAIOS architecture and module boundaries; finish diagrams and contract/data-flow review |
| G5 | IN_PROGRESS | Ownership RACI; validate named maintainers and operators |
| G6 | PARTIAL | Four-repository baseline; finish recursive config/dependency and fresh environment inventory |
| G7 | PARTIAL | Engineering standards matrix; align test/security/review and required CI policies |
| G8 | IN_PROGRESS | ADR index/template and accepted ADR-0051; reconcile historical ID collisions and cross-product decisions |
| G9 | IN_PROGRESS | Central risk/dependency register; refresh owners, priorities and closure evidence |
| G10 | IN_PROGRESS | Product portfolio catalogue and extended phase crosswalk; prioritize phase Work Orders |
| G11 | IN_PROGRESS | Delivery lifecycle, Work Orders, milestones and release evidence |
| G12 | OWNER ACTION REQUIRED | Legal, privacy, IP, operations, cost, backup, incident and live acceptance review |

## 3. HUB extended phases H0–H32

**Owner:** `MR_SIAVASH_HUB_AI`. The expanded phases refine the central intelligence/control plane. Existing compact mappings are references, not duplicate implementation targets.

| Phase | Capability | Existing mapping / evidence | Initial status |
|---|---|---|---|
| H0 | Core foundation and runtime | Compact H0; backend/configuration/architecture and CI | EVIDENCE / ACCEPTANCE PENDING |
| H1 | Data and persistence architecture | Compact H16; SQLite, migrations, transactions, backup foundations | EVIDENCE / ACCEPTANCE PENDING |
| H2 | Contracts, APIs and events | Compact H12 and X1; versioned hybrid contracts and API schemas | EVIDENCE / ACCEPTANCE PENDING |
| H3 | Context and state management | Agent context assembler, task/workflow state and shared-context boundaries | PARTIAL |
| H4 | CGI capability intelligence | Compact H4; capability registry, assessment and gap reporting | EVIDENCE / ACCEPTANCE PENDING |
| H5 | Tool, skill and plugin intelligence | Compact H6 and X5; tool manifest, validation, lifecycle and grants | EVIDENCE / ACCEPTANCE PENDING |
| H6 | GPI intelligence engine | Compact H3; intent, context and WorkOrder generation | EVIDENCE / ACCEPTANCE PENDING |
| H7 | AWI planning engine | Compact H2; DAG planning, dependency checks and plan revision | EVIDENCE / ACCEPTANCE PENDING |
| H8 | Decision intelligence | Compact H5; planning readiness consistency and blocker-aware policy selection merged in HUB PR #657 | PARTIAL |
| H9 | Workflow engine | Compact H1; durable DAG execution, checkpoint and state transitions | EVIDENCE / ACCEPTANCE PENDING |
| H10 | Task lifecycle engine | Compact H1/H7; owner-scoped task list/detail/result/history/cancel APIs merged in PR #661; priority and timezone-aware deadline scheduling with migration 60 merged in PR #663 | PARTIAL — first-class owner column/backfill, editing, SLA/overdue policy and running-worker cancellation remain |
| H11 | Execution engine | Compact H7; pull worker, leases, fencing and bounded registered handlers | EVIDENCE / ACCEPTANCE PENDING |
| H12 | Recovery and fault tolerance | Compact H8; idempotency, retry, leases, recovery and unknown-outcome handling | EVIDENCE / ACCEPTANCE PENDING |
| H13 | Model intelligence and routing | Compact H14; provider registry, local/remote routing and adapter boundaries | EVIDENCE / ACCEPTANCE PENDING |
| H14 | Prompt and context intelligence | Prompt registry, versioned templates and bounded context assembly | PARTIAL |
| H15 | Knowledge and RAG intelligence | Compact H9; ingestion, chunk integrity, retrieval and owner-declared reranking (PR #655 merged) | PARTIAL |
| H16 | Memory intelligence | Compact H9; owner-scoped memory CRUD/search and lifecycle; bounded owner-scoped expiry cleanup merged in PR #656 | PARTIAL |
| H17 | Memory governance and consolidation | Memory review/deduplication/contradiction proposals; selective cross-project ACL remains incomplete | PARTIAL |
| H18 | Evaluation and verification | Compact H10; encrypted WorkOrder/plan revision and canonical digest binding plus owner-scoped read-only evaluation merged in PR #660; production verifier adapters and E8 consumer contract remain | PARTIAL |
| H19 | Self-correction and replanning | Compact H10; bounded review-only plan revisions exist; end-to-end correction and approved learning remain | PARTIAL |
| H20 | Agent registry and lifecycle | Frozen specialist registry, profile fingerprints, authenticated discovery and traceable profile versions on HUB main | EVIDENCE / ACCEPTANCE PENDING |
| H21 | Multi-agent orchestration | Bounded specialist handoff and shared-context/result aggregation in the orchestrator | PARTIAL |
| H22 | Agent coordination and conflict resolution | Two-specialist handoff and disagreement preservation are tested; broader coordination and quality metrics remain | PARTIAL |
| H23 | Resource and budget management | Shared root/specialist input/output/model-call/tool/delegation/deadline budget merged in PR #658; provider quota and compute/storage/cross-product cost accounting plus load/fairness validation remain | PARTIAL |
| H24 | Scheduler and event-driven automation | Durable jobs/workers and content scheduling exist; generalized recurring/event-triggered workflows need a unified contract | PARTIAL |
| H25 | Observability and operations | Compact H15; health/readiness, logs, metrics and task/audit records exist; end-to-end trace coverage remains | PARTIAL |
| H26 | Admin and control center | Compact H17; operator APIs/UI exist in slices; unified authorized control-center acceptance remains | PARTIAL |
| H27 | Integration and developer platform | Compact H12, X1/X4/X5/X9 and MCP/API adapters; SDK and extension lifecycle remain incomplete | PARTIAL |
| H28 | Scalability and performance | Compact H18; bounded worker concurrency exists, but representative benchmarks/capacity/fairness are not complete | PARTIAL |
| H29 | Quality engineering and release | Compact H19; CI, security scans and broad suites exist; exact-main completion, protected branches and release gates remain | PARTIAL |
| H30 | Experimental and innovation intelligence | Experiment registry, prototype lifecycle and hypothesis evidence are not yet a complete workflow | PLANNED / GATED |
| H31 | Adaptive intelligence | Controlled strategy adaptation and benchmark-gated policy changes are not yet accepted | PLANNED / GATED |
| H32 | Advanced intelligence and research | Long-horizon research/simulation and verified knowledge evolution remain a governed research program | PLANNED / GATED |

## 4. EL_AI expanded phases E0–E21

**Owner:** `MR_SIAVASH_EL_AI`. Telegram transport, user/session interaction and channel delivery stay here. HUB remains the authority for shared private policy, memory and durable cross-product workflows; EL_AGENT remains the device-action owner.

| Phase | Capability | Existing mapping / evidence | Initial status |
|---|---|---|---|
| E0 | Agent foundation | Compact E0; Python runtime, configuration, CI and health diagnostics | EVIDENCE / ACCEPTANCE PENDING |
| E1 | Identity and personality | Compact E1; owner identity, pairing and credential handling; full personality profile controls remain limited | PARTIAL |
| E2 | User profile and personalization | Compact E1/E2; identity/session boundaries exist, persistent preference model is incomplete | PARTIAL |
| E3 | Conversational intelligence | Compact E2; multi-turn session and actor separation foundations | EVIDENCE / ACCEPTANCE PENDING |
| E4 | Intent and goal understanding | Compact E3; command/intent routing with HUB GPI integration | EVIDENCE / ACCEPTANCE PENDING |
| E5 | Context and personal knowledge interface | Compact E7 and HUB scoped memory/knowledge APIs; full selective context controls remain | PARTIAL |
| E6 | Planning and task experience | Compact E4/E5; dependency-aware plan preview and durable task submission | EVIDENCE / ACCEPTANCE PENDING |
| E7 | Agent delegation interface | Compact E5; HUB task submission exists; user-visible specialist routing/hand-off UX remains limited | PARTIAL |
| E8 | Tool and skill interface | Compact E6; versioned read-only Telegram tool catalog merged in HUB PR #662 and owner-only EL_AI /tools command in PR #151; tools:read does not authorize invocation | PARTIAL — governed invocation UX and broader skill lifecycle remain |
| E9 | Telegram bot platform | Compact E10; update intake, polling and typed Telegram APIs; durable outbox and ambiguous-reply quarantine merged in EL_AI PR #149; full test-bot/production delivery E2E remains an owner/environment gate | PARTIAL |
| E10 | Telegram session and interaction | Compact E2/E10; sessions, commands, callbacks and progress are implemented in slices | PARTIAL |
| E11 | Multimodal intelligence | Telegram media/file normalization and media routes exist; end-to-end multimodal reasoning remains incomplete | PARTIAL |
| E12 | Voice and speech interface | No complete EL_AI-owned voice conversation path established; do not count EL_AGENT local voice as EL_AI completion | PLANNED / GATED |
| E13 | Knowledge and research assistant | HUB knowledge/research services can be consumed through scoped contracts; EL_AI research UX/evaluation remains incomplete | PARTIAL |
| E14 | Personal productivity | Durable task plans and task status exist; calendar/notes/reminder integration is not complete | PARTIAL |
| E15 | Learning and development assistant | MR_SIAVASH_AI owns public Academy/learning content; EL_AI learning orchestration/interface remains a consumer-side capability | PLANNED / GATED |
| E16 | Local Agent interface | EL_AGENT is standalone; EL_AI device handoff is an optional, separately scoped integration | PLANNED / GATED |
| E17 | Memory control and feedback | HUB owns memory authority; EL_AI owner-facing memory controls and feedback lifecycle remain incomplete | PARTIAL |
| E18 | Autonomous operations | Compact E12; bounded plans, pause/checkpoints and task watches exist; all continuation gates need acceptance | EVIDENCE / ACCEPTANCE PENDING |
| E19 | Session isolation and privacy | Compact E13; public/owner separation and privacy regression tests exist; full independent review remains | EVIDENCE / ACCEPTANCE PENDING |
| E20 | Integration and production | Compact E14; contract/CI integration exists; real Telegram and production acceptance are owner/environment gates | OWNER / ENVIRONMENT GATE |
| E21 | Advanced personal intelligence | Digital twin, personal graph and safely governed evolution are not implemented as accepted capabilities | PLANNED / GATED |

## 5. EL_AGENT expanded phases L0–L19

**Owner:** `MR_SIAVASH_EL_AGENT`. The compact D0–D14 inventory is the current source baseline. L identifiers are the owner's expanded decomposition and do not create a second device runtime.

| Phase | Capability | Existing mapping / evidence | Initial status |
|---|---|---|---|
| L0 | Runtime foundation | D0/D1; Python runtime, CLI/API/desktop and Android application structure | EVIDENCE / ACCEPTANCE PENDING |
| L1 | Device identity and registration | D2/D11; local credentials and Hub device registration foundations | PARTIAL |
| L2 | Secure pairing interface | D2/D11; owner-initiated single-use pairing and scoped credential foundations | PARTIAL |
| L3 | Task runtime and state | D1/D4; local scheduler, persistence, cancellation and recovery | EVIDENCE / ACCEPTANCE PENDING |
| L4 | Windows runtime | D7; allowlisted application launch, desktop control and local commands | PARTIAL — physical Windows acceptance pending |
| L5 | Android runtime | D8; native companion, permissions, Keystore and adapters | PARTIAL — physical-device acceptance pending |
| L6 | File and document operations | Android document picker/access foundations; full cross-platform safe file lifecycle requires acceptance | PARTIAL |
| L7 | Application integration | D7/D8; allowlisted application intents and launch adapters | PARTIAL |
| L8 | Browser and web integration | Basic allowlisted browser launch exists; bounded browser interaction/permission model is not complete | PLANNED / GATED |
| L9 | Local tool ecosystem | D3; capability catalogue and deterministic local policy | PARTIAL |
| L10 | Local model runtime | D5; Ollama/local provider and Android native runtime foundations | PARTIAL |
| L11 | Offline and edge operations | D5; local-first provider fallback exists; network-blocked end-to-end acceptance remains | PARTIAL |
| L12 | Local scheduling and automation | D4; scheduled app launch, idempotency and unknown-outcome recovery | EVIDENCE / ACCEPTANCE PENDING |
| L13 | Device data and persistence | D10; SQLite/local storage foundations; memory lifecycle controls remain | PARTIAL |
| L14 | Remote communication | D11; outbound pairing, heartbeat and typed Hub client | PARTIAL — live staging acceptance pending |
| L15 | Monitoring and recovery | D4/D13; heartbeat, task recovery and audit foundations | PARTIAL |
| L16 | Update and runtime lifecycle | D13/D14; packaging/update integrity and rollback not fully accepted | PLANNED / GATED |
| L17 | Cross-device coordination | No accepted multi-device coordinator or conflict model established | PLANNED / GATED |
| L18 | HUB and EL_AI integration | D11; optional scoped Hub task consumer; EL_AI handoff remains separately gated | PARTIAL |
| L19 | Device testing and production | D14; CI exists, physical Windows/Android and signed release acceptance remain | OWNER / ENVIRONMENT GATE |

## 6. MR_SIAVASH_AI expanded phases A0–A22

**Owner:** `MR_SIAVASH_AI`. It remains the public-facing platform. Private HUB state, credentials and device control must not move into the browser or public Gateway.

| Phase | Capability | Existing mapping / evidence | Initial status |
|---|---|---|---|
| A0 | Platform foundation | Compact A0; static site, routing, CI and deployment source | EVIDENCE / ACCEPTANCE PENDING |
| A1 | Identity and account | Compact A1 public identity/navigation; full persistent user account/session capability is separate and not assumed complete | PARTIAL |
| A2 | UI/UX and design system | Compact A2; responsive design, accessibility and theme foundations | EVIDENCE / ACCEPTANCE PENDING |
| A3 | Digital identity and portfolio | Compact A3; project portfolio and public status metadata | EVIDENCE / ACCEPTANCE PENDING |
| A4 | Documentation and knowledge center | Compact A4; learning paths, guides and public knowledge content | EVIDENCE / ACCEPTANCE PENDING |
| A5 | Learning and interactive labs | Compact A4/A10; Academy and browser-local labs exist; isolated server execution and curriculum administration remain | PARTIAL |
| A6 | AI Workspace | Compact A5; public assistant/workspace foundations | EVIDENCE / ACCEPTANCE PENDING |
| A7 | AI chat and multimodal interface | Compact A5; assistant chat/API exists; broader streaming and multimodal end-to-end coverage remains | PARTIAL |
| A8 | AI Gateway and API | Compact A6; Cloudflare Gateway, validation, quotas and provider boundary | EVIDENCE / ACCEPTANCE PENDING |
| A9 | HUB integration | Compact A7; proposed owner-initiated connector; private pairing and remote execution are not enabled | PLANNED / GATED |
| A10 | EL_AGENT integration | EL_AGENT owns device control; website integration remains a separately authorized scoped feature | PLANNED / GATED |
| A11 | Agent and task dashboard | Public-safe task/status surfaces exist in slices; private agent operations remain HUB-only | PARTIAL |
| A12 | Admin and control center | Compact A8; Access-protected admin and audit slices exist | PARTIAL |
| A13 | Content and publishing engine | Compact A9; revisioned server-backed editorial workflow merged; live D1 migrations/deployment remain separate | PARTIAL |
| A14 | AI and developer tools | Compact A10; bounded tools/content utilities exist; sandboxed code execution remains incomplete | PARTIAL |
| A15 | Integration platform | Compact A11; selected public integrations and links exist; broader credentialed integration lifecycle remains | PARTIAL |
| A16 | Analytics and CRM | Compact A12; privacy-minimized analytics/support functions exist; live retention/release acceptance remains | PARTIAL |
| A17 | Localization and accessibility | Compact A2/A13; Persian RTL/accessibility foundations exist; full localization framework requires acceptance | PARTIAL |
| A18 | Privacy and user data interface | Privacy policy/control UI and Gateway privacy boundaries exist; full account data lifecycle is incomplete | PARTIAL |
| A19 | SEO and performance | Compact A13; asset budgets and SEO/security foundations exist; full browser/performance budget acceptance remains | PARTIAL |
| A20 | Developer ecosystem | Compact A11/A14; public integration/API documentation exists; SDK/extension ecosystem is planned | PARTIAL |
| A21 | Production and operations | Compact A14; CI and runtime smoke exist; fresh Cloudflare/D1, backup/restore and release verification are owner gates | OWNER / ENVIRONMENT GATE |
| A22 | Platform expansion | API platform and advanced workspace expansion are future scope | PLANNED / GATED |

## 7. Shared infrastructure X0–X23

**Coordinator:** HUB. Each producer owns its implementation; every consumer owns compatibility, privacy and authorization tests. Shared means shared contracts/services, not shared databases or unrestricted trust.

| Phase | Capability | Existing mapping / owner | Initial status |
|---|---|---|---|
| X0 | Architecture ownership and boundaries | G4/G5, ADR-0051, module boundaries; HUB coordinates | EVIDENCE / ACCEPTANCE PENDING |
| X1 | Shared contracts and schema registry | Compact X1; HUB contract owner, all consumers validate | EVIDENCE / ACCEPTANCE PENDING |
| X2 | Identity directory | Compact X2; HUB pairing authority, EL_AI actor identity, EL_AGENT device identity | PARTIAL |
| X3 | Organization and tenant management | Per-product owner isolation exists; a unified organization/tenant lifecycle is not established | PLANNED / GATED |
| X4 | API and service registry | Compact X4; HUB API/service ownership and consumer contract tests | PARTIAL |
| X5 | Event and messaging infrastructure | Compact X5; durable queues and Telegram updates exist; cross-product event schema/lifecycle remains | PARTIAL |
| X6 | Shared configuration | Project-local validated settings exist; centralized profile/config distribution is not established | PARTIAL |
| X7 | Artifact and data registry | Versioned attachment/artifact references exist in slices; complete shared registry/lineage remains | PARTIAL |
| X8 | Data governance | G9/G12 and security policies; data classes, retention and lineage need cross-product closure | PARTIAL |
| X9 | Shared memory services | HUB is the sole private memory authority; granular project/agent sharing remains incomplete | PARTIAL |
| X10 | Shared knowledge services | HUB knowledge/RAG; consumer-side source attribution and access tests remain | PARTIAL |
| X11 | Shared model registry | HUB model/provider registry; cross-product model metadata compatibility remains | PARTIAL |
| X12 | Shared capability registry | HUB CGI/tool registry; local EL_AGENT capabilities remain locally authoritative | PARTIAL |
| X13 | Shared agent registry | HUB specialist registry exists; device/client registry and federation remain distinct | PARTIAL |
| X14 | Shared scheduler and notification | HUB jobs, EL_AI Telegram delivery and EL_AGENT local scheduler are separate owners; common contract remains | PARTIAL |
| X15 | Shared observability infrastructure | Compact X7 and HUB H15; end-to-end multi-product trace continuity remains | PARTIAL |
| X16 | Cost and resource accounting | HUB H23 shared execution budget is in progress; cross-product cost accounting is not complete | IN_PROGRESS |
| X17 | Localization infrastructure | Website/Telegram/device locale handling exists in product-specific slices; shared catalog/service is not established | PARTIAL |
| X18 | Developer portal and SDK | Website developer docs and HUB API/MCP exist; supported SDK lifecycle is planned | PLANNED / GATED |
| X19 | Release and compatibility management | Versioned contracts and CI exist; coordinated compatibility/deprecation policy remains | PARTIAL |
| X20 | Cross-project workflow | HUB durable jobs and optional EL_AI/EL_AGENT clients exist; full cross-product saga and recovery acceptance remains | PARTIAL |
| X21 | Service discovery and federation | Authenticated registries exist in narrow scopes; federated service discovery is not established | PLANNED / GATED |
| X22 | Public and private API platform | Website public Gateway and HUB private APIs are separated; full API product/version lifecycle remains | PARTIAL |
| X23 | Ecosystem integration verification | Consumer contract tests exist; full four-product staging/device/production acceptance remains | PARTIAL |

## 8. Innovation Engine I0–I15

**Program owner:** HUB research/architecture. Innovation is an evidence-managed program, not an autonomous permission to change production architecture.

| Phase | Capability | Host / dependency | Initial status |
|---|---|---|---|
| I0 | Innovation governance | G8/G9/G11; HUB architecture and delivery governance | PARTIAL |
| I1 | Problem and opportunity discovery | H30, G2/G10; evidence-backed problem register | PLANNED / GATED |
| I2 | Research and prior art | H32 and ML0; citations, source dates and license review | PLANNED / GATED |
| I3 | Creative idea generation | H30; idea proposals remain untrusted until evaluated | PLANNED / GATED |
| I4 | Cross-domain synthesis | H22/H32; specialist outputs require provenance and disagreement retention | PARTIAL |
| I5 | Hypothesis and experiment design | H30/ML1; reproducible protocol and acceptance criteria | PLANNED / GATED |
| I6 | Prototype engineering | H30; isolated branch/sandbox and prototype lifecycle | PLANNED / GATED |
| I7 | Simulation and benchmarking | H28/ML12; benchmark harness and baseline dataset | PLANNED / GATED |
| I8 | Automated experiment management | H30/ML1; resource-bounded experiment registry | PLANNED / GATED |
| I9 | Adaptive architecture | H31; ADR and rollback required for adoption | PLANNED / GATED |
| I10 | Advanced customization | H14/X6/ML8; versioned profiles and safe defaults | PARTIAL |
| I11 | Plugin and extension innovation | H5/H27/X5; manifest, permission and sandbox boundaries | PARTIAL |
| I12 | Algorithm and model research | ML5–ML17; reproducible evaluation before adoption | PLANNED / GATED |
| I13 | Invention documentation | G8/G11; prior-art, provenance and disclosure review | PLANNED / GATED |
| I14 | Controlled adoption | G8/H19; independent acceptance and reversible rollout | PLANNED / GATED |
| I15 | Innovation portfolio | G10/G11; value, priority, owners and lifecycle evidence | PARTIAL |

## 9. Foundation Model & AI Research Lab ML0–ML17

**Program owner:** HUB research/model architecture. Existing provider use, local inference and model routing are not evidence of pretraining or ownership of a foundation model.

| Phase | Capability | Host / dependency | Initial status |
|---|---|---|---|
| ML0 | AI research strategy | G0/G1/H32; research roadmap and capacity constraints | PLANNED / GATED |
| ML1 | Research reproducibility | H30/I5; dataset/model/config/version and repeatable runs | PLANNED / GATED |
| ML2 | Dataset governance | G12/X8; licensing, consent, provenance, retention and quality gates | PLANNED / GATED |
| ML3 | Data engineering | ML2/H15; lawful ingestion, cleaning and documented transformations | PLANNED / GATED |
| ML4 | Compute and training infrastructure | H23/H28; approved capacity, cost controls and isolated training environment | PLANNED / GATED |
| ML5 | Model architecture research | ML1/ML4; literature and reproducible small experiments | PLANNED / GATED |
| ML6 | Tokenizer and data-mixture research | ML2/ML5; multilingual benchmark and tokenizer experiments | PLANNED / GATED |
| ML7 | Foundation-model pretraining | ML2–ML6; no accepted pretraining pipeline/evidence established | PLANNED / GATED |
| ML8 | Fine-tuning and specialization | ML1/ML2/ML12; local model use is not fine-tuning evidence | PLANNED / GATED |
| ML9 | Post-training and alignment | ML8/ML12/ML13; controlled evaluation required | PLANNED / GATED |
| ML10 | Multilingual intelligence | ML6/ML8/ML12; Persian UI support is not model capability evidence | PLANNED / GATED |
| ML11 | Multimodal model research | ML4–ML9/ML12; media adapters are not multimodal model training | PLANNED / GATED |
| ML12 | Model evaluation and benchmarking | H29/I7; standardized model/task datasets and reproducible scores | PARTIAL |
| ML13 | Model safety and reliability | H11/H19/X8; cross-model safety and robustness evaluation | PARTIAL |
| ML14 | Inference optimization | H23/H28; quantified latency/memory/quality trade-offs | PARTIAL |
| ML15 | Model serving infrastructure | H13/H14/H23; provider adapters exist, research-grade serving operations remain | PARTIAL |
| ML16 | Model registry and lifecycle | H13/H14; model/provider registry exists, training artifact lifecycle is incomplete | PARTIAL |
| ML17 | Advanced AI research | H32/I12; long-horizon research program | PLANNED / GATED |

## 10. First delivery sequence

Do not start every phase in parallel. Use dependency-first slices and keep one active implementation workstream at a time.

1. **Close the current HUB core review queue:** H8 PR #657, H23 PR #658, H18 PR #660, H10 owner-lifecycle PR #661, E8 PR #662 and H10 scheduling PR #663 are merged. H15 PR #655 and bounded H16 expiry cleanup PR #656 are also merged. Do not recreate their work.
2. **H23 resource accounting:** the shared per-run budget is merged; extend owner-scoped provider/API quota enforcement to all applicable inference paths, then compute/storage/cross-product resource accounting and representative load/fairness tests.
3. **H18/H19 evidence loop:** WorkOrder digest/revision persistence and the read-only evaluator API are merged; add trusted production verifiers, plan supersede/revision lifecycle, the EL_AI E8 consumer contract and the complete negative evidence matrix.
4. **G2/G3/G6/G7/G9/G10/G11:** complete requirement traceability, source/test mappings, repository standards, risk register, portfolio priorities and Work Orders.
5. **EL_AI E9/E10:** finish Telegram delivery outbox, unknown-outcome handling, duplicate/update and rate-limit matrix; keep test-bot and production acceptance gated.
6. **EL_AGENT L4–L19:** complete Windows/Android physical-device, pairing, policy, offline and release acceptance; do not make it a mandatory HUB client.
7. **Website A9–A21:** keep public/private boundaries; complete only through separately reviewed connector, Preview, D1 backup/restore and release gates.
8. **X1–X23:** prioritize contracts, identity, data governance, tracing, quota and compatibility before optional federation or multi-tenant services.
9. **I/ML programs:** start with reproducible small experiments, data/license governance and benchmarks. Foundation pretraining is a distant gated milestone, not an assumed near-term implementation.

## 11. Current evidence boundary

This crosswalk is a planning and audit index. It does not claim that all expanded phases are implemented, merged, deployed or production-ready. It intentionally records missing acceptance as PARTIAL or PLANNED rather than promoting phases from source-code presence alone.

For the merged H23 shared execution-budget slice, see [H23 shared execution budget](../operations/h23-shared-execution-budget.md). The core per-run budget is merged; H23 remains PARTIAL until provider quotas, resource/cost accounting and load/fairness gates are accepted.
