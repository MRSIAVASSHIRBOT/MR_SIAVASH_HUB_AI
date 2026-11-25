# ADR-0045: Product boundary between EL_AGENT and EL_IR_BOT

- **Status:** Proposed — owner decision required
- **Date:** 2026-11-25
- **Decision owner:** Repository/product owner
- **Scope:** Ecosystem product taxonomy, roadmap ownership and cross-project contracts

## Context

The canonical ecosystem document `docs/PROJECT_GOALS_ECOSYSTEM.md` describes two distinct roles:

- `MR_SIAVASH_EL_AI`: conversational/Telegram-facing interface, identity mapping, command routing and user-facing delivery.
- `MR_SIAVASH_EL_AGENT`: independent Windows/Android personal agent with standalone/offline capability, local runtime, memory and policy.

The four-repository 73-phase execution baseline currently assigns its fourth phase family (`B0`–`B11`) to `MR_SIAVASH_EL_IR_BOT`, whose source is a Telegram transport Bridge with a durable Cloudflare queue, delivery recovery, owner/private-chat controls and scoped integration to EL_AI/Hub.

These roles are not interchangeable. A conversational Telegram interface, a transport Bridge, and a local desktop/mobile agent have different trust boundaries, runtime ownership, deployment surfaces and acceptance criteria. Treating the repository names as aliases would create an unclear owner for device execution, Telegram delivery and local state.

## Options

### Option A — Keep EL_IR_BOT as the fourth repository in the current 73-phase execution set; track EL_AGENT separately

- Keep `B0`–`B11` owned by `MR_SIAVASH_EL_IR_BOT` as the Telegram Bridge phase family.
- Keep `MR_SIAVASH_EL_AI` responsible for conversation, Telegram identity/commands and user-facing experience.
- Keep `MR_SIAVASH_EL_AGENT` as a separate Windows/Android product with its own phase inventory and acceptance evidence.
- Do not count EL_AGENT capabilities toward the existing 73 IDs until a separate roadmap update is approved.

**Consequences:** Preserves the current four-repository baseline and the existing Bridge implementation. Adds an adjacent product track and requires a later explicit decision on whether to expand the ecosystem phase count.

### Option B — Make EL_AGENT the canonical fourth product and move EL_IR_BOT to a separate transport project

- Reassign the fourth product role to EL_AGENT.
- Move `B0`–`B11` out of the canonical four-product inventory and track them as a separate Bridge project.
- Rebuild the dependency and phase count for the remaining canonical ecosystem.

**Consequences:** Better matches the original canonical product taxonomy, but materially changes the 73-phase inventory and ownership map. It must not be performed as a silent repository rename or phase reassignment.

### Option C — Merge the product identities and responsibilities

Treat EL_AI, EL_AGENT and EL_IR_BOT as one product with shared release and execution ownership.

**Consequences:** Not recommended. It would blur local-device execution, Telegram transport and user-facing conversation boundaries, increasing authority and failure coupling.

## Provisional recommendation

Prefer **Option A for the active four-repository 73-phase implementation campaign**, while keeping EL_AGENT explicitly visible as an adjacent, separately tracked product. This is a planning recommendation only; it does not close the product decision. The owner must accept or replace this recommendation before contracts or roadmap accounting are changed to include EL_AGENT.

Until an owner decision is recorded:

1. Keep the existing 73 IDs and their current repository mapping unchanged.
2. Do not identify EL_IR_BOT as the Windows/Android agent.
3. Do not place local device execution, filesystem/browser control or device memory inside the Telegram Bridge.
4. Keep EL_AI's Telegram UX, EL_IR_BOT's transport/delivery, and EL_AGENT's local runtime as distinct responsibilities.
5. Do not share device or conversation authority implicitly. Cross-project calls must use versioned contracts, owner-scoped identity, least privilege and explicit revocation.
6. Report EL_AGENT acceptance separately; do not count it toward B0–B11 or the 19 already verified phase IDs.

## Acceptance criteria for resolving this ADR

The owner decision must explicitly state:

- Which repositories are considered the canonical products in the four-project set.
- Whether EL_AGENT is a fifth product, a renamed replacement, or outside the present scope.
- Which repository owns Windows/Android runtime, local memory, OS permissions and device action policy.
- Which repository owns Telegram transport, webhook and delivery queue.
- How the 73-phase count and dependencies change, if at all.
- Which test, release and operational acceptance gates apply to each product.

No source, deployment or permission change is authorized by this proposed ADR.
