# ADR-0008: Review-only specialist agent proposals

- Status: Accepted for the proposal-validation foundation
- Date: 2026-11-09

## Context

The agent runtime currently uses server-defined specialist profiles. The longer-term product direction includes discovering and creating specialist agents, but model-generated definitions must never become executable capabilities merely because they were proposed.

## Decision

Introduce a strict, bounded proposal schema and a pure validation function.

A proposal may describe:
- a stable agent name;
- a short purpose and bounded instruction set;
- a list of already-registered tool identifiers;
- a small maximum-turn limit;
- a human-readable rationale.

Validation reuses the canonical `AgentRegistry` constraints and verifies every requested tool against the current `ToolRegistry`. It does not persist, register, activate, or execute the candidate.

## Security properties

- Unknown proposal fields are rejected.
- Name, description, instruction, tool-count, and turn-count limits are enforced.
- Duplicate agent names and duplicate tool requests are rejected.
- Unknown tools are rejected; proposals cannot introduce tool implementations.
- Candidate validation does not mutate the active agent registry.
- Tool names in a proposal are only a requested scope. The existing tool policy remains authoritative at invocation time.
- No proposal can grant permissions, approve high-risk actions, or bypass owner approval.

## Consequences

This creates a safe validation boundary for a future owner-reviewed agent creation workflow. It is not yet a dynamic agent marketplace, persistent agent-management API, automatic activation system, or self-modifying runtime.

## Follow-up gates

The owner-scoped proposal API, durable records, authenticated review, fingerprint binding, and regression tests are implemented in the next delivery stage (ADR-0009). Before any separate activation API or UI is introduced:
1. Revalidate tool availability and policy at activation time.
2. Keep agent execution budgets and delegation depth bounded.
3. Add explicit activation/revocation semantics and tests; proposal approval alone must never activate an agent.
4. Run the complete CI and security checks on the exact release candidate.
