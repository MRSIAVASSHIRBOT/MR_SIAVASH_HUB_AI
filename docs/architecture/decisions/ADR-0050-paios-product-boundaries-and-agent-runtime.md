# ADR-0050 — PAIOS product boundaries and replaceable agent runtime

- Status: Proposed
- Date: 2026-11-26
- Supersedes: none yet
- Related: `PAIOS_TARGET_ARCHITECTURE_2027.md`, `PAIOS_EXECUTION_ROADMAP_2026_2030.md`

## Context

The ecosystem already contains several partially overlapping AI, planning, provider, tool, memory, Telegram and device implementations. A wholesale rewrite would duplicate working HUB modules and risk losing custom legacy features. At the same time, a fixed monolithic bot structure would make future model, channel, memory and runtime upgrades expensive.

The canonical product goals define four active products: HUB, EL_AI, EL_AGENT and the public Website. The legacy EL_IR_BOT repository contains useful Telegram and custom account capabilities but should not become a fifth competing AI product.

Current evidence shows:
- HUB owns the durable task/workflow, shared model/tool, private memory, policy/approval and audit foundations.
- EL_AI owns Telegram-facing identity, conversation routing and delivery, and consumes the signed Telegram Bridge.
- EL_AGENT owns standalone device execution.
- Website owns public experience and public Gateway.
- Legacy EL_IR_BOT contains `MR_SIAVASH_EL_IR_BOT.py`, `self_core.py`, `ai_router.py`, and the transitional Telegram edge/queue implementation.

## Decision

1. Keep four canonical products; treat EL_IR_BOT as a legacy migration source and transitional transport component.
2. Keep HUB as the authoritative owner of durable cross-product tasks, workflows, private shared memory, tool registry/grants, approvals and evidence.
3. Keep EL_AI as the owner of Telegram/Business interaction, conversation UX, channel identity, message normalization and user-facing response delivery.
4. Keep EL_AGENT independently usable for Windows/Android local execution and local state.
5. Keep Website public-first and isolated from private HUB state unless a separately versioned, opt-in connector is implemented and accepted.
6. Separate Agent Session, Harness, Context Builder, Model Gateway, Tool Dispatcher and execution environment behind stable interfaces. The implementations may change independently.
7. Preserve the behavior of `MR_SIAVASH_EL_IR_BOT.py`, `self_core.py` and `ai_router.py` during migration. No non-bug feature is deleted without explicit owner authorization.
8. Business messages may enter the same command interpretation/orchestration pipeline as owner conversations, but they must resolve to a Business-customer actor context and only the explicitly exposed Business capability set. The pipeline is shared; authority is not inherited.
9. Keep MCP as an external tools interoperability adapter and A2A as an optional independent-agent protocol. Neither replaces the canonical internal Tool Registry or normal in-process calls.
10. Extend existing HUB runtime capabilities before adding new brokers, databases, orchestration products or microservices.
11. Select runtime/library versions through compatibility and acceptance testing. Newest stable release is a candidate, not an automatic mandate.
12. Use measured evaluations to decide when to add multi-agent orchestration, vector retrieval, new storage systems or autonomous evolution features.

## Consequences

- Product ownership is clearer and cross-project duplication is discouraged.
- Telegram Business can be delivered early without rewriting all legacy features first.
- Model, harness, channel and storage upgrades can be isolated behind interfaces.
- Existing architecture and tests can be reused rather than rebuilt.
- The legacy migration is measurable through feature-parity tests.
- Some existing roadmaps and documents may need reconciliation in later isolated documentation changes; historical evidence should be retained rather than silently overwritten.

## Rejected alternatives

### Rewrite all projects from scratch
Rejected: high regression risk and discards existing functioning systems.

### Make EL_AI and HUB separate competing agent brains
Rejected: duplicates workflow, memory, permissions and task state. EL_AI owns conversational turns; HUB owns durable cross-product execution and authoritative shared state.

### Convert everything to microservices now
Rejected: increases deployment, network, tracing and recovery complexity without demonstrated scale need.

### Adopt every latest framework/protocol immediately
Rejected: latest versions can be incompatible or unnecessary; interfaces and compatibility tests provide more durable value.

### Give Business customers the owner's full command permissions
Rejected: one shared command pipeline does not require identical actor authority. Business-facing capabilities are extensible without inheriting owner privileges.

## Review triggers

Revisit this ADR when:
- HUB and EL_AI ownership boundaries materially change;
- a new independent agent product is added;
- cross-product traffic/scale justifies service decomposition;
- model or protocol changes invalidate current interfaces;
- Business requirements need an additional operator role/capability model.
