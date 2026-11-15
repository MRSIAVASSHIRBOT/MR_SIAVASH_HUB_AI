# Hybrid Integration Contract v1 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a machine-readable, test-verified source of truth for the existing Hybrid integration boundaries and Hub Telegram API.

**Architecture:** Keep Hub, EL_AI, and the public website Gateway independently owned. Store the canonical v1 contract in HUB_AI and verify it against the Hub's generated OpenAPI schema and existing Python constants. This first vertical slice is additive and does not change runtime behavior.

**Tech Stack:** Python 3.11, pytest, FastAPI OpenAPI, JSON.

**Spec:** `docs/superpowers/specs/2026-11-15-hybrid-integration-contract-v1-design.md`

## Global Constraints

- Preserve the local-first modular monolith and existing Telegram pairing implementation.
- No new runtime dependencies.
- Do not add shared database access or public-to-private Hub access.
- Do not change secrets, production settings, deployments, or bot activation.
- Contract statements must reflect current implementation, not roadmap assumptions.

## Review Focus

- Endpoint removed or renamed: OpenAPI contract test must fail.
- Scope added or removed: scope parity test must fail.
- Token lifetime changed: TTL parity test must fail.
- Website Gateway gains private Hub access: trust-boundary test must fail.
- Pagination or result bounds drift: manifest and test assertions must be updated together.

---

### Task 1: Add contract regression tests

**Files:**
- Create: `tests/test_hybrid_integration_contract.py`
- Create later: `contracts/hybrid/v1/manifest.json`

**Interfaces:**
- Consumes: `create_app().openapi()`, `TelegramScope`, `DEFAULT_SCOPES`, and `TelegramPairingRepository` constants.
- Produces: regression checks for endpoint, scope, lifetime, and trust-boundary parity.

- [ ] Write tests that load the manifest and compare it to the live OpenAPI schema and implementation constants.
- [ ] Run the focused test and confirm the expected failure because the manifest does not yet exist.
- [ ] Keep assertions limited to behavior explicitly present in the approved design.

### Task 2: Add the canonical manifest and human-readable contract

**Files:**
- Create: `contracts/hybrid/v1/manifest.json`
- Create: `docs/integrations/hybrid-integration-contract-v1.md`

**Interfaces:**
- Consumes: current Hub Telegram route definitions and EL_AI's scoped Hub client.
- Produces: versioned machine-readable endpoint and trust-boundary contract.

- [ ] Record all current Telegram routes with method, path, auth mode, and scope.
- [ ] Record actual TTLs, pagination bounds, result cap, and idempotency header.
- [ ] Explicitly mark request-ID propagation as not yet standardized.
- [ ] Document consumer responsibilities and public/private data boundaries.
- [ ] Run focused and full backend tests, lint, and dependency audit.

### Task 3: Review and publish a draft PR

**Files:**
- Update: none outside the feature branch.

- [ ] Inspect the complete diff and verify no existing user changes were overwritten.
- [ ] Run repository CI and review the exact results.
- [ ] Open a draft PR against `main`; do not merge automatically.
