# ADR-0007: Owner-initiated Telegram client pairing

- Status: Accepted; Hub API implementation and EL_AI explicit opt-in hardening are on their respective main branches. Live pairing remains unverified.
- Date: 2026-11-09

## Context

MR_SIAVASH_EL_AI is a Telegram transport and conversation interface. It must not receive the Hub owner's password or an unrestricted Hub web session. Telegram usernames are mutable and are not an authorization mechanism.

## Decision

The Hub owns Telegram client registration, scopes, credential issuance, expiry, revocation and audit.

### Pairing

1. The bot obtains the sender's numeric Telegram user ID and generates a unique client UUID.
2. The owner authenticates to the local Hub and creates a pairing challenge bound to that Telegram ID, client UUID, label and explicit scopes.
3. The Hub returns a cryptographically random one-time code. Only its SHA-256 hash is stored; it expires after five minutes.
4. The owner enters the code in the intended private Telegram chat.
5. EL_AI exchanges the code, Telegram numeric ID and client UUID. The Hub atomically consumes the challenge and issues scoped credentials.
6. The one-time code cannot be reused or exchanged for a different Telegram ID/client UUID.

### Credentials

- Access token: 15 minutes.
- Refresh token: 30 days, bound to the same client and Telegram numeric ID.
- Only token hashes are stored by the Hub.
- Owner can list and revoke paired clients; revocation invalidates access and refresh credentials.
- EL_AI must store returned credentials in an OS-backed or equivalently protected secret store, never in source control, browser storage or Telegram chat logs.
- Refresh tokens are bearer secrets and must be treated as credentials.

### Initial scopes

- status:read
- tasks:read
- tasks:create
- memory:search

No Agent execution, approval decision, publishing, destructive or arbitrary tool scope is granted by default. Task creation still passes through the Hub PolicyEngine; high-risk task types remain waiting for owner approval.

### API boundary

Paired bot requests use a dedicated /integrations/telegram/* route family and must include the access token plus the bound X-Telegram-User-Id. This does not make the token valid for general Hub routes. Existing owner routes continue to require the owner's normal session.

## Security properties

- Owner-initiated consent and five-minute, single-use pairing code.
- Numeric Telegram ID and client UUID binding.
- Server-side scope enforcement on each bot endpoint.
- Short-lived access tokens and revocable refresh credentials.
- Hashed token storage, bounded inputs, idempotent task submission and audit metadata allowlisting.
- No public tunnel or external exposure of the local Hub API.
- Public MR_SIAVASH_AI Gateway is not used as a private Hub proxy.

## Limitations and follow-up

- The initial scope set is intentionally narrow; Agent execution and Telegram approvals require separate ADRs and explicit scopes.
- EL_AI uses an OS-backed Keyring credential store for access/refresh credentials. Explicit opt-in enforcement is merged in EL_AI PR #6; Hub client initialization and `/pair` remain disabled unless `HUB_INTEGRATION_ENABLED=true`.
- No live Telegram pairing or production bot deployment has been verified.
- Production remote hosting remains a separate threat-model and deployment decision.
