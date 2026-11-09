# ADR-0007: Owner-initiated Telegram client pairing

- Status: Accepted; Hub API and owner controls are on main; EL_AI client is on main; live pairing remains unverified
- Date: 2026-11-09

## Context

A Telegram transport may act as a narrow client of the local Hub, but it must not receive the Hub owner's password or an unrestricted Hub web session. Telegram usernames are mutable and are not an authorization mechanism.

## Decision

The Hub owns Telegram client registration, explicit scopes, credential issuance, expiry, revocation and audit. The Hub API remains bound to the local trust boundary; this ADR does not authorize public exposure or remote hosting.

### Pairing

1. The client obtains the sender's numeric Telegram user ID and a stable client UUID.
2. The owner authenticates to the local Hub and creates a pairing challenge bound to that Telegram ID, client UUID, label and selected scopes.
3. The Hub returns a cryptographically random one-time code. Only its SHA-256 hash is stored; it expires after five minutes.
4. The owner transfers the code only through the intended private client channel.
5. The client exchanges the code, Telegram numeric ID and client UUID. The Hub atomically consumes the challenge and issues scoped credentials.
6. The one-time code cannot be reused or exchanged for a different Telegram ID/client UUID.

### Least-privilege scopes

The default scope is status:read only. The owner must explicitly opt in to any additional permission:

- tasks:read
- tasks:create
- memory:search

Agent execution, approval decisions, publishing, destructive actions and arbitrary tools are not available through this integration. Task creation still passes through the Hub PolicyEngine; high-risk task types remain waiting for owner approval.

### Credentials

- Access token: 15 minutes.
- Refresh token: 30 days, bound to the same client and Telegram numeric ID.
- Only token hashes are stored by the Hub.
- Owner can list and revoke paired clients; revocation invalidates access and refresh credentials.
- Clients must store returned credentials in an OS-backed or equivalently protected secret store, never in source control, browser storage or chat logs.
- Refresh tokens are bearer secrets and must be treated as credentials.

### API boundary

Paired client requests use a dedicated /integrations/telegram/* route family and must include the access token plus the bound X-Telegram-User-Id. Each endpoint enforces its required scope. The task-list endpoint returns only tasks attributed to the exact paired client. These credentials do not authorize general Hub routes; owner routes continue to require the owner's normal session.

## Security properties

- Owner-initiated consent and five-minute, single-use pairing code.
- Numeric Telegram ID and client UUID binding.
- Least-privilege default: status-only until the owner explicitly grants more.
- Server-side scope enforcement on each client endpoint.
- Short-lived access tokens and revocable refresh credentials.
- Hashed token storage, bounded inputs, idempotent task submission and audit metadata allowlisting.
- Per-client task listing prevents one paired client from reading another client's task history.
- No public tunnel or external exposure of the local Hub API.
- Public MR_SIAVASH_AI Gateway is not used as a private Hub proxy.

## Verification status and limitations

- Hub pairing API, owner-facing pairing/revocation controls, scoped authentication, task/memory routes, idempotent task submission, revocation and per-client task isolation are present on Hub main.
- EL_AI main contains the scoped Hub client, stable installation identity, OS-backed Keyring credential storage, explicit Hub opt-in and the public-only MR_SIAVASH_AI Gateway client.
- Automated Hub tests cover pairing identity binding, one-time expiry, scopes, revocation, idempotency and cross-client task isolation.
- No live Telegram pairing, client-side credential-store verification, production bot deployment or end-to-end smoke test has been verified.
- Agent execution and Telegram approvals require separate ADRs and explicit scopes.
- Production remote hosting remains a separate threat-model and deployment decision.
