# Hybrid Integration Contract v1 — Design

**Date:** 2026-11-15  
**Status:** Approved for implementation  
**Architecture:** Hybrid, independently deployable repositories

## Intent

Establish one machine-readable, test-verified source of truth for the existing private Telegram-to-Hub API and the ecosystem trust boundaries. The contract must describe implemented behavior, not aspirational behavior, so consumers can detect drift without granting new privileges.

## Goals

- Record the current Hub Telegram API methods, paths, authentication modes, scopes, token lifetimes, and bounded request behavior.
- Verify that every declared endpoint exists in the Hub's generated OpenAPI document.
- Verify that the declared scopes, defaults, and token lifetimes match the implementation.
- Explicitly preserve ownership boundaries: Hub owns private state and policy; EL_AI owns Telegram transport and bot identity; the website Gateway serves public knowledge only.
- Make the contract version explicit and keep the test dependency-free.

## Non-goals

- No new API endpoints, database schema, authentication scheme, or token format.
- No shared database, public access to private Hub APIs, browser-held Hub credentials, or implicit service trust.
- No production deployment, Cloudflare setting changes, bot activation, or secret rotation.
- No claim that a live Telegram bot or live cross-service pairing is operational.

## Approaches considered

1. **Rebuild the integration layer:** rejected because the Hub pairing API and EL_AI client already exist and are tested.
2. **Documentation-only contract:** rejected because prose can drift silently from the API.
3. **Machine-readable manifest plus runtime/OpenAPI regression tests:** selected because it is low-risk, dependency-free, reviewable, and verifies documented endpoints against the actual Hub application.

## Design decisions

- Canonical source: `contracts/hybrid/v1/manifest.json` in MR_SIAVASH_HUB_AI.
- Contract version: `1.0.0`; additive changes may remain within v1 only when they do not change existing semantics. Breaking changes require a new major contract directory.
- Hub Telegram endpoints are listed with their current method, path, auth mode, and required scope where applicable.
- The website public Gateway is explicitly classified as public-only and not authorized to call private Hub endpoints.
- Request correlation is documented as a future compatibility requirement, not as an implemented guarantee in v1.
- Existing HTTP error behavior is recorded as FastAPI's `detail` response; a normalized error envelope is deferred until all consumers can migrate together.

## Acceptance criteria

- JSON parses and has the required contract metadata.
- Contract endpoint methods and paths are present in the generated Hub OpenAPI schema.
- Contract scopes and defaults exactly match the Python implementation.
- Token/challenge lifetimes match the pairing repository constants.
- Trust-boundary invariants are asserted by automated tests.
- Existing repository CI passes on the feature branch.

## Rollout and rollback

The contract is additive and has no runtime effect. Consumers can adopt it in separate reviewable changes. Rollback consists of reverting the contract and its tests; no data migration or production change is required.
