# Hybrid Integration Contract v1

**Contract ID:** `mr-siavash-hybrid-integration`  
**Version:** `1.0.0`  
**Canonical manifest:** [`contracts/hybrid/v1/manifest.json`](../../contracts/hybrid/v1/manifest.json)  
**Status:** Approved baseline; describes implemented interfaces only.

## 1. Service ownership

| Component | Owns | Must not own |
|---|---|---|
| MR_SIAVASH_HUB_AI | Private memory, tasks, agents, approvals, policy decisions, audit events, scoped integration API | Telegram transport identity or public website sessions |
| MR_SIAVASH_EL_AI | Telegram transport, Telegram identity, command routing, local credential storage, Hub API client | Hub database, policy engine, private memory store |
| MR_SIAVASH_AI public Gateway | Public website knowledge and public support workflows | Private Hub credentials, private Hub memory, owner-only operations |

The services remain independently deployable. No shared database is permitted by this contract.

## 2. Private Hub ↔ EL_AI contract

The Hub API is rooted at `/integrations/telegram`. The exact methods, paths, authentication modes, and required scopes are defined in the JSON manifest and regression-tested against the generated Hub OpenAPI schema.

### Authentication

- Owner-initiated pairing creates a five-minute challenge bound to the Telegram user ID and EL_AI client ID.
- The exchange operation consumes the one-time pairing code and issues a 15-minute access token and a 30-day refresh token.
- Authenticated client calls send `Authorization: Bearer <scoped_access_token>` and `X-Telegram-User-Id`.
- Default pairing scope is `status:read`; additional scopes must be explicitly granted.
- The authenticated owner can replace scopes on an active paired client through `PUT /integrations/telegram/clients/{client_id}/scopes`; the update is audited and applies to the next request. Revoked or foreign clients cannot be updated.\n- The Hub remains authoritative for client ownership, scope enforcement, task ownership, policy evaluation, and revocation.
- EL_AI stores credentials in the operating-system credential store and must not place credentials in URLs, logs, source control, or browser storage.

### Scope map

| Scope | Permitted capability |
|---|---|
| `status:read` | Read paired client status |
| `tasks:read` | Read own tasks and bounded task event history |
| `tasks:result` | Read own bounded terminal task result |
| `tasks:create` | Submit tasks subject to Hub policy and idempotency |
| `tasks:cancel` | Cancel own queued or approval-waiting task |
| `memory:search` | Search owner-scoped memory |\n| `video:read` | Read the non-secret provider catalog, own bounded video-generation history, and individual generation status |\n| `video:cancel` | Cancel only own prepared or queued video generation before provider submission |

### Bounded operations

- Task listing: 1–50 records per page; cursor maximum 512 characters.
- Task history: 1–50 events per page.
- Terminal task result: maximum 32 KiB encoded response.
- Task creation requires the `Idempotency-Key` header.
- A task result is unavailable until the task reaches a terminal state.
- Task cancellation is limited to tasks that remain queued or waiting for owner approval.\n- Video-generation history is limited to 1–20 records per page; its cursor is limited to 512 characters. Responses omit provider job IDs and private asset IDs.\n- Video-generation cancellation is a separate scope and cannot cancel active or ambiguous provider work; those states return HTTP 409. The provider catalog is read-only and does not probe providers or start jobs.

## 3. Public website Gateway boundary

The MR_SIAVASH_AI Cloudflare Gateway is a public surface. It may serve public knowledge and public support workflows. It must not call private Hub endpoints, receive Hub bearer credentials, or expose private Hub context to browser clients.

A future authenticated owner console would require a separately designed server-side trust path; it must not reuse the public assistant route as a shortcut.

## 4. Error handling and observability

The Hub currently uses FastAPI's `detail` error envelope for HTTP exceptions. Consumers should map status codes to safe user-facing messages and must not expose internal exception text or credential material.

The private EL_AI ↔ Hub request-correlation contract uses `X-Request-ID` as opaque diagnostic metadata:

- EL_AI generates a canonical lowercase UUIDv4 for each logical Hub operation. If an authorized operation receives HTTP 401, EL_AI performs one bounded recovery: it refreshes credentials through a separate request with its own request ID, then replays the original operation at most once with the original request ID. A second 401 is surfaced to the caller; no generic retries or backoff are performed.
- Hub accepts canonical lowercase UUID versions 1–8. Missing, malformed, noncanonical, or unsupported values are replaced with a server-generated UUIDv4.
- Hub stores the canonical value at `request.state.request_id` and returns it in the response `X-Request-ID` header for handled HTTP responses.
- Hub completion logs contain only `request_id`, HTTP `method`, route template, and `status_code`.
- EL_AI emits `hub_request_completed` with the same `request_id`, HTTP `method`, route template, `status_code`, and an `outcome` label. Dynamic task IDs are replaced by a route placeholder.
- Neither side logs raw paths, query strings, request bodies, Telegram identities, task/client identifiers, or credentials.
- Request IDs do not grant permissions and are not idempotency keys.

The public website Gateway remains a separate public-only path. Its outbound requests may carry an independently generated request ID, but this does not create a route to the private Hub or imply shared request context.

## 5. Compatibility and versioning

- Additive fields or endpoints may be added within v1 only if existing semantics remain unchanged.
- Changes to authentication, ownership, scope meaning, token lifetimes, or existing request/response semantics are breaking and require a new major contract version.
- The manifest is the machine-readable source of truth; this document explains the security and operational intent.
- Consumer repositories should pin their compatibility tests to the published v1 manifest; this approved v1 baseline is now merged to the Hub default branch.

## 6. Operational status

This contract does not assert that a Telegram bot is deployed or connected. Pairing code, scoped Hub routes, and the EL_AI Hub client exist in source; live bot activation and production pairing remain separate operational tasks.

## 7. Verification

The Hub regression test checks:
1. Every manifest endpoint method/path exists in the generated OpenAPI schema.
2. Manifest scopes and default scopes match the Python implementation.
3. Token and pairing challenge lifetimes match the repository constants.
4. The public/private trust boundaries remain explicit.
