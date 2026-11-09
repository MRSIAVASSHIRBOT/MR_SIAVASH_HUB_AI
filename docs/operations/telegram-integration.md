# Telegram Integration Operations

## Local topology and trust boundary

Keep MR_SIAVASH_HUB_AI bound to loopback (default 127.0.0.1). A Telegram client, if intentionally enabled, must use an outbound connection to the local Hub. Do not expose the Hub port publicly, create a public tunnel, or route private Hub credentials through the public MR_SIAVASH_AI Gateway.

## Configuration and opt-in

- Keep HUB_INTEGRATION_ENABLED=false until the local Hub and a trusted OS credential-store backend are ready.
- Keep TELEGRAM_PUBLIC_ENABLED=false until public access is intentionally enabled.
- Keep HUB_API_BASE_URL=http://127.0.0.1:8000 for local operation.
- Keep HUB_ALLOW_REMOTE=false. Remote Hub hosting is a separate security decision and requires HTTPS plus explicit opt-in.
- Supply TELEGRAM_BOT_TOKEN and TELEGRAM_OWNER_IDS only through the local runtime environment or an approved secret manager. Never commit them or paste tokens into chat.
- The initial bot accepts private Telegram chats only; group and supergroup messages are rejected.
- EL_AI stores access and refresh credentials through the OS Keyring backend. If a trusted backend is unavailable, integration fails closed; do not replace it with plaintext files.

## Owner pairing and least privilege

1. Start the Hub locally and authenticate to its owner UI.
2. Start EL_AI with its local runtime configuration.
3. In the bot's private chat, run /pairinfo to obtain the Telegram numeric ID and stable EL_AI client UUID.
4. In the authenticated Hub UI, create a pairing challenge for those exact values.
5. Keep the default status:read scope unless another capability is needed.
6. Grant tasks:read, tasks:create or memory:search only after considering the data/action each scope exposes.
7. Transfer the one-time code only to the intended private client channel. The code expires after five minutes and can be used once.
8. Review the paired-client list and revoke any client that is lost, replaced or no longer trusted.

The Hub API defaults to status-only access when the scopes field is omitted. Client-provided claims do not override Hub-side scope checks.

## Credential lifecycle

- Access tokens expire after 15 minutes.
- Refresh tokens expire after 30 days and are bound to the paired client and Telegram numeric ID.
- The Hub stores only SHA-256 token hashes.
- Owner revocation invalidates the paired client's access and refresh credentials.
- Raw tokens and pairing codes must never be logged, pasted into public channels or committed.

## API capabilities

- status:read: read minimal authenticated client status.
- tasks:read: list only tasks attributed to the exact paired client; cross-client task history is not returned.
- tasks:create: submit bounded task requests through the Hub PolicyEngine. High-risk or unregistered task types remain waiting for owner approval.
- memory:search: search owner memory only when the owner explicitly grants this scope.

No Agent execution, approval decisions, content publishing, destructive actions or arbitrary tools are exposed through this initial integration.

## Public website Gateway

EL_AI calls only the public MR_SIAVASH_AI assistant route. It sends the current public message only; it never forwards private Hub context, memory, task details, Telegram identifiers or Hub credentials. Public mode is disabled by default. The production Gateway currently has no Workers AI binding, so its assistant returns verified knowledge fallback rather than live model inference.

## Current verification status — 2026-11-09

- Hub pairing API, owner-facing pairing/revocation controls, scoped authentication, task/memory routes and per-client task isolation are implemented on Hub main.
- Hub CI, Windows launcher validation, video integration and defensive scan passed on the commits associated with the pairing and task-isolation changes.
- EL_AI main contains the client-side Keyring credential store and explicit integration opt-in; its public Gateway client is implemented and CI-tested.
- No live Telegram pairing, client-side credential-store verification on the owner's machine, production bot deployment or end-to-end Telegram smoke test has been verified.

Remote Hub hosting remains out of scope until its threat model, transport, access controls and deployment are separately reviewed.
