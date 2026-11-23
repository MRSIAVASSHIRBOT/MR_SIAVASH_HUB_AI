# H8 — API and Backend Acceptance Matrix

Status: review/acceptance proposal; not test evidence.
Baseline source inspected: API router mounting in `backend/mrhub/main.py`, task/job routes, and current CI workflow.

## Verified foundation
- FastAPI app factory and lifespan initialize the persistent task repository.
- Routers are modular and mounted for auth, approvals, capabilities, tasks/jobs, policy, tools, memory, knowledge, media/video, agent planning/runs, integrations, projects, and related domains.
- HTTP middleware accepts only canonical UUID request IDs, otherwise generates a UUID; it logs request ID, method, route template, and status and returns `X-Request-ID`.
- Middleware also applies no-store and common security headers; UI receives a restrictive CSP.
- Task submission is authenticated, server-classified for risk, and supports idempotency-key reservation.
- CI includes Python 3.11/3.12, test+coverage, Ruff, JavaScript syntax/contract tests, wheel asset verification, and clean wheel health/UI smoke. Backend CI includes pip-audit.

## Request-ID vs. trace-ID boundary
`X-Request-ID` identifies an HTTP request only. It is not a persistent task, agent-run, workflow, or cross-request trace ID. Do not reuse request IDs as execution trace IDs; H9 proposes a separate immutable trace ID propagated through asynchronous execution.

## Contract acceptance matrix
| Surface | Required review/test evidence | Release blocker if |
|---|---|---|
| Authentication | Unauthenticated requests rejected; login throttling behavior and token/session expiry tested | Protected route accessible without auth or throttling bypass |
| Authorization | Owner scoping and server-side permission checks verified for every protected router | Cross-owner access or client-controlled grant |
| Request IDs | Canonical supplied UUID accepted; malformed/missing IDs replaced; response header present; log excludes sensitive request content | Request ID malformed/unsafe, sensitive logs, or missing correlation on errors |
| Request validation | Pydantic boundaries, size/range limits, unknown fields policy, malformed JSON handling | Unbounded input or inconsistent unsafe parsing |
| Idempotency | Same key/same request behavior; same key/different request conflict; owner scope and expiry | Duplicate side effect or cross-owner key reuse |
| Error contract | Stable status code and sanitized response; internal exception/secret not leaked | Stack trace, secret, or sensitive data exposed |
| Rate/session | Configuration and runtime limits verified, especially auth and expensive endpoints | No effective limits for high-cost/abuse-prone paths |
| Health/readiness | Liveness is independent; readiness verifies database/schema; worker heartbeat accurately reported | Healthy signal despite required dependency or worker unavailable |
| Migrations | Clean install, upgrade from supported prior schema, checksum/version validation, backup/restore and rollback limits documented | Migration corruption, unsupported upgrade, restore unverified |
| Background work | Task lifecycle, worker stop/resume, queue state, bounded retries and stale recovery verified | Unsafe retry, stale worker claim, uncontrolled dispatch |
| Packaging | Clean wheel installation, UI assets present, health and UI endpoints respond | Missing runtime/package assets or smoke failures |

## Existing CI map
- `.github/workflows/ci.yml`: Python 3.11/3.12, JS syntax and gateway contract tests, pytest coverage, wheel asset check/clean install smoke, Ruff, Windows wheel smoke.
- `.github/workflows/backend-ci.yml`: Python 3.11, pip-audit, Ruff, pytest with coverage.
- These workflows overlap; actual trigger coverage, duplicate runtime, and exact candidate checks should be reviewed before release.

## Proposed implementation order
1. Inventory every mounted router and its auth/authorization dependencies.
2. Add contract tests for missing auth, owner boundaries, consistent error schemas, request validation, and rate-limit behavior.
3. Add migration upgrade/restore acceptance tests.
4. Verify request IDs are present on exception responses and logs, including unexpected failures, without logging request bodies.
5. Align API error schemas and versioning policy without breaking current clients.
6. Record exact CI run URLs and candidate SHA in the H10 release evidence record.

## Explicit gaps / cautions
- Middleware source review alone does not prove every route is protected correctly.
- `X-Request-ID` is not authentication, authorization, or a trace token.
- CI run success does not prove deployment configuration, restore procedures, or operational readiness.
- No local tests were run for this document.
