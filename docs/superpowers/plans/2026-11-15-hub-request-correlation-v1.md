# Hub Request Correlation Implementation Plan

> **For agentic workers:** Use the native inline execution approach; follow the test-driven-development cycle task-by-task.

**Goal:** Validate, echo, and safely log `X-Request-ID` for Hub HTTP requests.

**Architecture:** Add request correlation to the existing FastAPI security middleware. The middleware accepts only UUID values, generates replacements when absent or malformed, stores the canonical value on request state, emits a route-template-only structured log, and echoes the ID.

**Tech Stack:** Python 3.11+, FastAPI, Starlette TestClient, pytest.

**Spec:** `docs/superpowers/specs/2026-11-15-hybrid-request-correlation-v1-design.md`

## Global Constraints

- Request ID is opaque metadata and never an authorization or idempotency credential.
- Header is exactly `X-Request-ID`; value is canonical lowercase UUID.
- Never log raw paths, query strings, request bodies, tokens, pairing codes, Telegram IDs, task IDs, or client IDs.
- No database, public Gateway, credential, or deployment changes.

## Review Focus

- Malformed and oversized header values are replaced rather than reflected.
- IDs remain available on HTTP error responses produced inside the application.
- Route templates are logged instead of raw paths containing identifiers.
- Existing security headers and CSP behavior remain unchanged.
- Requests without an incoming ID remain operational and receive a generated ID.

---

### Task 1: Hub middleware and contract

**Files:**
- Modify: `backend/mrhub/main.py`
- Modify: `contracts/hybrid/v1/manifest.json`
- Modify: `docs/integrations/hybrid-integration-contract-v1.md`
- Test: `tests/test_request_correlation.py`
- Modify: `tests/test_hybrid_integration_contract.py`

**Interfaces:**
- Produces: response header `X-Request-ID`, canonical UUID in `request.state.request_id`, and safe `http_request_completed` log event.
- Consumes: incoming `X-Request-ID` only when parseable as UUID.

- [ ] Add tests for valid ID echo, missing/invalid replacement, and safe route-template logging.
- [ ] Run targeted tests and confirm expected failure before implementation.
- [ ] Implement validation/generation and middleware response header/log behavior.
- [ ] Update manifest and docs to status `standardized`, documenting UUID format, generation, response echo, and log redaction.
- [ ] Run targeted tests, full pytest, Ruff, and security checks.
- [ ] Commit and open a reviewable PR; do not merge automatically.

### Task 2: Hub final verification

- [ ] Confirm the manifest contract test matches middleware behavior.
- [ ] Confirm exact branch SHA has green Backend CI, Python matrix, Ruff, dependency audit, and security workflows.
- [ ] Review diff for accidental request data or secret logging.
