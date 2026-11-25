# ADR-0046 — Four-repository scope and Agent/Bridge boundary

- Status: Accepted
- Date: 2026-11-25
- Scope: X1, X2, X4, X7, E10, E11, B0–B11

## Context

The requested 73-phase execution plan names four repositories: Hub, EL_AI, public Website, and EL_IR_BOT. The canonical ecosystem goals document also names a separate product, MR_SIAVASH_EL_AGENT, for Windows/Android device companionship. Older portfolio notes alternately treated EL_IR_BOT as discovery-only or omitted it from the canonical active-product table. These names represent distinct responsibilities and must not be collapsed.

The current source repositories establish the following boundaries:

- EL_AI owns conversational behavior, Telegram-facing command routing, owner identity mapping, and the scoped Hub client.
- EL_IR_BOT owns the Telegram edge transport, webhook ingress, durable delivery queue, retries, delivery outcome reconciliation, and signed Bridge protocol consumed by EL_AI.
- Hub remains authoritative for private tasks, workflows, permissions, approvals, memory, tools, and audit.
- Website owns public content and the public Gateway; it does not inherit private Hub state.
- EL_AGENT is a separate Windows/Android companion with its own local runtime and device policy boundary.

## Decision

1. The current 73-phase execution baseline covers the four explicitly requested repositories. EL_IR_BOT is the owner of B0–B11; it is not a replacement name for EL_AGENT.
2. EL_AGENT remains a separate, fifth ecosystem product and is outside the current four-repository phase count. It is not silently dropped, merged into EL_IR_BOT, or included in B0–B11.
3. E10 describes EL_AI's Telegram-facing experience and its consumption of the EL_IR_BOT Bridge. EL_AI owns conversation, command interpretation, and user-visible responses; EL_IR_BOT owns Telegram webhook transport and durable delivery.
4. E11 in this roadmap describes the bounded desktop/local-agent capability assigned to EL_AI. Any implementation delegated to the separate EL_AGENT repository requires an explicit versioned contract, identity/pairing model, owner grants, audit, rollback, and a separately revised phase inventory. EL_AGENT features do not count as E11 completion by implication.
5. B7 connects EL_IR_BOT to EL_AI through the signed Bridge contract. B8 connects EL_AI to Hub through scoped Hub APIs. EL_IR_BOT never becomes a policy authority, tool executor, or holder of Hub master credentials.
6. X1/X2/X4/X7 contracts must preserve distinct service identities and trust zones. No shared database, ambient trust, implicit permission inheritance, or cross-project secret reuse is introduced.

## Consequences

- The requested four-repository scope is unambiguous while the separate EL_AGENT product remains visible in the canonical ecosystem.
- Telegram transport, conversation logic, Hub policy, and device execution have separate owners and can be tested independently.
- E10/B7/B8 integration tests must exercise the actual boundaries rather than mock one project as another.
- E11 cannot be marked done until its own sandbox, policy, cancellation, audit, and integration acceptance are verified.
- Any later decision to include EL_AGENT in the 73-phase count requires a new baseline revision and explicit dependency/ownership changes.

## Non-goals

- This ADR does not authorize live Telegram traffic, device commands, Worker deployment, D1 migration, secret changes, or paid infrastructure.
- It does not claim any of E10, E11, B7, B8, X1, X2, X4, or X7 is complete.
