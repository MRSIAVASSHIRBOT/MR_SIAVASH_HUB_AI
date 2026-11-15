# Hybrid Request Correlation v1 — Design

**Date:** 2026-11-15  
**Status:** Approved implementation direction; additive v1 behavior  
**Canonical contract:** `contracts/hybrid/v1/manifest.json`

## Intent

Standardize privacy-safe request correlation for private EL_AI ↔ Hub calls. Every logical Hub API request initiated by EL_AI carries a canonical UUID in `X-Request-ID`. Hub validates the value, places it on request state, emits a structured completion log containing only the ID, HTTP method, route template, and status, and echoes the canonical ID in its response header.

## Goals

- Generate request IDs in EL_AI; do not accept Telegram/user-supplied values as correlation IDs.
- Reuse the same ID when an authorized request is retried after a 401.
- Generate a fresh ID for independent pairing and refresh requests.
- Hub accepts only UUID-form IDs; missing or malformed values are replaced with a new UUID.
- Hub returns `X-Request-ID` on successful and failed HTTP responses handled by middleware.
- Hub logs route templates, not raw paths, query strings, request bodies, credentials, Telegram IDs, or task/client identifiers.
- Keep request correlation independent of authentication and authorization; it grants no permission.
- Keep MR_SIAVASH_AI's public Gateway outside the private Hub request path.

## Non-goals

- Distributed tracing vendors, traceparent/W3C tracing, metrics backends, durable audit-table schema changes, or browser-visible Hub credentials.
- Propagating request IDs from public website Gateway to private Hub.
- Treating request IDs as idempotency keys or authorization tokens.

## Approaches

1. **Per-call generated UUID (selected):** EL_AI creates one UUID per logical Hub operation, includes it on the wire, and reuses it on an auth retry. This has a small surface area and does not require Telegram handler signatures or shared mutable state to change.
2. **Telegram-update context propagation:** Thread one ID through every handler and nested call. This gives update-level correlation but changes many command/test interfaces and couples transport context to the API client.
3. **W3C trace context:** Adopt traceparent/tracestate and a tracing stack. This is excessive for the current two-service integration and would introduce unnecessary dependencies.

## Architecture

EL_AI's scoped `HubClient` owns ID generation and header propagation. Hub middleware validates/canonicalizes the inbound UUID, attaches it to request state, logs a privacy-safe completion event, and echoes it. The ID is opaque metadata only; existing bearer scopes, Telegram identity binding, owner pairing, and idempotency behavior remain unchanged.

## Constraints and security

- Python 3.11+; retain FastAPI/httpx and existing dependency bounds.
- Header name is exactly `X-Request-ID`; value is a canonical lowercase UUID string.
- Never log raw request paths, query parameters, bodies, tokens, pairing codes, Telegram identities, or task identifiers.
- Invalid or oversized inbound values must not be reflected or logged.
- Existing public Gateway trust boundaries and no-shared-database rule remain unchanged.
- Additive header behavior stays within Hybrid Contract v1.

## Acceptance

- Tests prove EL_AI sends a valid ID on pairing and authenticated calls, and uses one ID across 401 retry.
- Tests prove Hub echoes valid IDs, replaces invalid/missing values, and logs only safe route-template metadata.
- Full repository CI, lint, security workflows pass on the exact branch heads.
- Contract manifest and human-readable documentation describe the implemented behavior accurately.
