# Canonical Project Goals — MR_SIAVASH Ecosystem

**Document role:** Canonical product-intent reference for the four connected MR_SIAVASH projects.  
**Last reviewed:** 2026-11-22  
**Status:** Living goals and architecture direction; goals are not claims of implementation or production readiness.

This document records the long-term goals, responsibilities, boundaries, integration direction, priorities, and delivery principles. Repository code, CI, release records, and runtime evidence remain the sources of truth for what is actually implemented. If implementation status conflicts with this document, report the gap instead of changing the goal silently.

## 1. Ecosystem vision

Build a coherent personal AI ecosystem that combines a central intelligence/workflow platform, a public digital workspace and knowledge gateway, a private conversational interface, and an independent local desktop/mobile agent.

The four repositories are separate products with clear ownership. They should cooperate through versioned, authenticated, least-privilege interfaces—not shared databases, implicit trust, duplicated control planes, or uncontrolled forwarding of private context.

The ecosystem should progressively deliver:
- AI intelligence, planning, task decomposition, decision support, tool use, execution, evaluation, and correction—within deterministic policies and explicit safety limits.
- Local-first and hybrid capabilities; configurable providers and transparent data-routing/privacy controls.
- Shared, selectively accessible memory and knowledge, with distinct private, public, device-local, episodic, semantic, and task-state scopes.
- Reliable workflows: observable task state, idempotency, checkpoints, bounded retries/timeouts, cancellation, recovery, and verified outcomes.
- Learning, software engineering, network/Linux education, research, content production, and legitimate defensive security.
- Consistent integration contracts, monitoring, security posture, documentation, tests, and staged release evidence.

## 2. Project ownership and goals

### 2.1 MR_SIAVASH_HUB_AI — Central intelligence and orchestration hub

**Primary role:** Core platform, owner/private control plane, shared intelligence, and controlled orchestration.

Product goals:
- Maintain a local-first, hybrid-capable AI workspace for a primary owner, while preserving explicit boundaries for future multi-user support.
- Provide shared core services for model/provider registry and routing, agent orchestration, planning/task management, memory/knowledge retrieval, durable workflows/jobs, checkpoints/recovery/cancellation, tool/plugin/MCP registration, operator surfaces, and audit/policy.
- Coordinate specialist domains such as developer assistance, discovery/research, content and media workflows, social/Telegram automation, and defensive/authorized security tools through contracts and shared infrastructure.
- Provide controlled device-task and integration APIs where implemented, using paired identity, scopes, grants, policy checks, bounded actions, and verifiable outcomes.
- Support local execution where feasible; external/remote providers must be explicitly configured and routed. Never silently fall back from local to cloud.
- Be authoritative for private owner memory, private tasks, approvals, tool policy, audit, and Hub-controlled integration grants.

Engineering principles:
- Prefer a modular monolith and explicit internal module contracts until distributed architecture is justified.
- Secure by default: least privilege, secret isolation, scoped tool grants, auditability, fail-closed decisions, and approvals for sensitive or high-impact actions.
- Keep infrastructure shared rather than implementing competing backend systems per capability.
- Keep workloads observable, recoverable, testable, and cost-aware; prefer free/open-source options when suitable, while paid services remain explicitly opt-in.
- Prohibit arbitrary/unbounded execution, credential theft, malware, unauthorized access, covert tracking, evasion, and unsafe security features.

### 2.2 MR_SIAVASH_AI — Public website, digital identity, learning workspace, and public gateway

**Primary role:** Public-facing digital identity and safe public services—not a private Hub mirror.

Product goals:
- Present the user's digital identity, portfolio, projects, tools, research/learning, evidence-backed work, and achievements clearly.
- Be a Persian-first educational and practical workspace for AI, software engineering, Python/web technologies, networking, Linux, and legitimate defensive cybersecurity.
- Offer accessible, polished modules, courses, references, tools, project case studies, and useful content.
- Provide a public assistant/Gateway only for explicitly public knowledge and approved services; make data disclosure consent clear.
- Integrate public GitHub/Telegram and other explicitly exposed services when contracts exist.
- Evolve toward a safe administrator experience and operational tools (e.g. dashboard/CRM/support management) without exposing private Hub data or credentials.
- Preserve a deliberate visual identity and usability, including Persian RTL, accessibility, responsive behavior, and clear implemented-vs-planned status.

Boundaries:
- Static/public site metadata is not a live view of private Hub runtime.
- No private Hub memory, owner context, credentials, or private task data is forwarded to the public Gateway.
- Public assistant calls must be limited to the current disclosed query/context and permitted public sources.

### 2.3 MR_SIAVASH_EL_AI — Conversational/Telegram interface and personal assistant access

**Primary role:** User-facing conversation, Telegram transport, and carefully scoped access to Hub capabilities.

Product goals:
- Provide a Persian-capable assistant interface with public and owner/private experiences kept separate.
- Own Telegram transport, Telegram identity mapping, command routing, user-facing message delivery, and user experience.
- Support task planning and dependency-aware task plans where available; communicate state accurately and recover safely from ambiguous requests/results.
- Connect to private Hub services only through owner-initiated, identity-bound pairing and scoped authenticated API routes.
- Use public MR_SIAVASH_AI Gateway only for public queries, with explicit opt-in and no private-context forwarding.
- Preserve clear privacy, identity, permission, audit, and graceful-failure behavior.

Boundaries:
- Hub remains authoritative for private memory, tasks, agents, approvals, tool policy, and audit.
- No shared database, browser-held Hub credential, public tunnel, implicit trust, or unrestricted Hub session.
- Secrets stay in OS-backed credential storage or trusted backend; logs must not contain tokens, pairing secrets, user identifiers, message bodies, or raw provider payloads.
- Live Telegram activation, webhook registration, and production deployment are separately controlled, verified operations.

### 2.4 MR_SIAVASH_EL_AGENT — Independent Windows/Android personal agent

**Primary role:** Standalone device-side agent, local tools, local memory and scheduler, optional secure integrations.

Product goals:
- Build a useful, independent personal agent for Windows and Android that remains functional when Hub, internet, cloud, or other ecosystem services are unavailable.
- Provide local runtime, settings, planning, memory, policy, scheduler, and bounded platform tools; local autonomy must not depend on Hub credentials.
- Support local-only, online-preferred, hybrid/automatic, and per-request local override modes through replaceable provider interfaces.
- Add voice interaction progressively (local/offline first where practical, optional cloud with clear consent).
- Support safe, typed actions such as approved app aliases, user-initiated screen capture with confirmation, bounded scheduling, reminders, device status, and approved browser destinations.
- Keep local memory canonical for standalone operation; optional encrypted sync must be consent-based and include conflict resolution, export, and controls.
- Provide a secure optional Agent Gateway topology for cross-device or cloud inference without embedding long-lived provider keys in clients.

Boundaries:
- Hub is an optional adapter for pairing, device registry, policy, task relay, and controlled synchronization—not the agent's mandatory runtime.
- Model output is untrusted proposal data. Deterministic policy authorizes actions.
- Every action is typed, schema-validated, capability/scoped, bounded by time/resources, and auditable; sensitive or externally visible actions require explicit confirmation.
- No arbitrary shell/scripts, arbitrary executable paths, unrestricted filesystem/network, hidden monitoring, automatic calls/messages, purchases, account changes, or unreviewed remote control.
- Local capabilities must degrade gracefully if remote services are unavailable.

## 3. Integration map and contract boundaries

| Producer / consumer | Intended relationship | Authority and boundary |
|---|---|---|
| Hub ↔ EL_AGENT | Optional pairing, device registry, scoped task relay, heartbeat/status, approved sync | Hub policies/grants authorize Hub-originated tasks; local agent keeps its own runtime, memory and policy |
| Hub ↔ EL_AI | EL_AI asks for authorized private services via authenticated scoped APIs | Hub owns private state, task/policy/approval decisions and audit; EL_AI is transport/UI |
| MR_SIAVASH_AI ↔ EL_AI | Public Gateway client for public queries | Only explicitly disclosed current request and permitted public context; never private Hub memory |
| MR_SIAVASH_AI ↔ Hub | Future/optional public-to-Hub integration only through explicitly designed safe contracts | No direct database sharing or private runtime visibility; public site cannot become a private Hub proxy |
| Hub ↔ shared ecosystem | Versioned API/event/task contracts and reusable services | Explicit auth, scopes, version compatibility, bounded payloads, audit, error handling and revocation |

**Integration invariants:** No direct cross-project database access. No implicit trust based on network location or project identity. Prefer versioned contracts and adapters. Make connection state and data-sharing scopes visible. Disable/revoke integrations cleanly. Minimize transmitted data. Test failure, timeout, expiry, revocation, malformed responses, duplicate requests, and recovery paths.

## 4. Shared quality, security, and collaboration standards

- **Evidence over assertion:** distinguish code implemented, unit/CI-tested, integration-tested, device-tested, deployed, and independently/runtime verified. Never claim a stronger level than evidence supports.
- **Security:** threat-model interfaces, minimize privileges and data, validate inputs and outputs, protect secrets, avoid sensitive logging, use fail-closed authorization, audit consequential actions, and include rollback/revocation.
- **Reliability:** contracts, timeouts, bounded retries, idempotency, correlation IDs, cancellation, checkpoints/recovery where needed, health/readiness checks, and graceful degradation.
- **Quality:** inspect current repository and related integration states before editing; preserve existing work; make focused changes; add regression tests; review the exact changed head; inspect CI; and verify post-merge state when merging.
- **Documentation:** maintain product goals, architecture, roadmap, decisions, operating instructions, and release evidence. Keep this canonical ecosystem goal document linked from project entry points and update it when goals or ownership change.
- **Learning collaboration:** implementation should be accompanied by concise, practical explanations and verification evidence when the task warrants it, helping the owner gain independent engineering skill.
- **Resource strategy:** favor low-cost/free and open-source components where suitable; do not enable paid services or production-impacting changes without explicit permission.

## 5. Priority and staged roadmap

Priorities may be reordered by fresh repository evidence, blockers, risk, and dependencies. Do not treat roadmap items as completed.

1. **Hub stability and foundations:** close correctness/security/recovery gaps; strengthen contracts, workflows, tests, diagnostics, and developer/operator experience. Hub is the primary active development focus.
2. **Agent standalone acceptance:** advance Windows and Android functionality, local/offline resilience, policy and action boundaries; resolve CI/base drift and complete device acceptance only on available real devices.
3. **Secure Hub–Agent integration:** pairing, device identity, scoped grants, short-lived credentials/leases, task relay, expiry/revocation, bounded retries/idempotency, and verified result reporting; stage tests before any real device task.
4. **EL_AI operational completion:** Telegram configuration/activation and end-to-end message acceptance, while keeping public/private access separate and live activation controlled.
5. **Website and public Gateway:** improve digital identity, educational experience, accessibility, public service reliability, and evidence-backed integration status; keep public/private data boundaries explicit.
6. **Ecosystem integration and lifecycle:** shared versioned contracts, observability, security checks, backups/recovery, integration testing, staged release, rollback, and ongoing maintenance across all four projects.

## 6. Operating rules for project maintenance

- Re-read this document as the canonical product-goal source before cross-project planning; use repository state and fresh evidence for execution details.
- Maintain one primary active development focus while keeping the other projects aligned, audited, debugged, and incrementally improved.
- Prefer small, reviewable, reversible changes on branches with PRs, exact-head CI, and post-merge verification.
- Merge only when the diff is understood, required checks are green, current-head review has no unresolved critical issues, and external/device/production gates are satisfied. Leave gated work open and document its blocker.
- Do not work on Gshop. It is explicitly out of scope.
- Never imply background work continues between scheduled runs; each maintenance run must inspect current state and act on evidence.

## 7. Links to the repositories

- [MR_SIAVASH_HUB_AI](https://github.com/MRSIAVASSHIRBOT/MR_SIAVASH_HUB_AI)
- [MR_SIAVASH_AI](https://github.com/MRSIAVASSHIRBOT/MR_SIAVASH_AI)
- [MR_SIAVASH_EL_AI](https://github.com/MRSIAVASSHIRBOT/MR_SIAVASH_EL_AI)
- [MR_SIAVASH_EL_AGENT](https://github.com/MRSIAVASSHIRBOT/MR_SIAVASH_EL_AGENT)

This file is the canonical **goal/ownership/integration reference**. Each repository's README, architecture, roadmap, status, security, and release documents remain responsible for local implementation detail and evidence.
