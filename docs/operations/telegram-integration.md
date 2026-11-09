# Telegram Integration Operations

## Local topology

Run MR_SIAVASH_HUB_AI and MR_SIAVASH_EL_AI on the same trusted machine. Keep the Hub API bound to loopback (default `127.0.0.1`). EL_AI uses outbound Telegram long polling and calls the Hub over loopback. Do not expose the Hub port publicly or use a public tunnel.

## Prerequisites and opt-in

- Configure `HUB_API_BASE_URL=http://127.0.0.1:8000` in the local EL_AI environment.
- Keep `HUB_INTEGRATION_ENABLED=false` until the local Hub and a trusted OS credential-store backend are ready. Set it to `true` only when intentionally enabling the integration.
- Keep `HUB_ALLOW_REMOTE=false`. Remote Hub hosting is a separate security decision and requires HTTPS plus explicit opt-in.
- EL_AI stores access and refresh credentials through the OS Keyring backend. If a trusted backend is unavailable, the integration must fail closed; do not replace it with plaintext files.
- Supply `TELEGRAM_BOT_TOKEN` and `TELEGRAM_OWNER_IDS` only through the local runtime environment or an approved secret manager. Never commit them.
- The first release accepts private Telegram chats only. Group and supergroup messages are rejected.

The explicit opt-in is also enforced by EL_AI PR #4: client initialization and `/pair` are disabled unless `HUB_INTEGRATION_ENABLED=true`. Until that PR is merged and verified, treat the flag as a mandatory operational prerequisite and do not use pairing with it disabled.

## Pairing procedure

1. Start the Hub locally and authenticate to its owner API/UI.
2. Start EL_AI with the required local configuration.
3. In the bot's private chat, use `/pairinfo` to obtain the Telegram numeric ID and stable EL_AI client UUID.
4. In the authenticated local Hub, create a pairing challenge bound to those exact values. Select only the scopes required by the intended workflow.
5. Enter `/pair CODE` in the same private chat within five minutes.
6. Verify `/hub` and only the approved commands: `/tasks`, `/memory QUERY`, and `/task TYPE | DESCRIPTION`.
7. Revoke the paired client from the Hub if the device is lost, replaced, or no longer trusted.

## Credential lifecycle

- Pairing codes are single-use and expire after five minutes; the Hub stores only their SHA-256 hashes.
- Access tokens expire after 15 minutes.
- Refresh tokens expire after 30 days and are bound to the paired client and Telegram numeric ID.
- The Hub stores only token hashes. Raw access and refresh tokens must never be logged, pasted into chat, or committed.
- Owner revocation invalidates all tokens for the paired client.

## Implementation and verification status — 2026-11-09

- The Hub pairing API, scoped authentication, task/memory routes, idempotent task submission, and owner revocation are present on Hub `main`.
- EL_AI `main` contains the scoped Hub client, stable local identity, OS Keyring credential storage, and owner command flow.
- EL_AI CI run [42611029358](https://github.com/MRSIAVASSHIRBOT/MR_SIAVASH_EL_AI/actions/runs/42611029358) completed successfully on Python 3.11 and 3.12 for commit `902972ecdef38420b3f59f41f07bb367f5c4af59`.
- EL_AI PR #4 adds explicit opt-in enforcement and regression tests; it is still a Draft PR.
- No live Telegram connection, real pairing, production bot deployment, or end-to-end Hub/Telegram smoke test has been verified.

## Remaining limitations

- The initial scopes remain limited to status, task read/create, and memory search. Agent execution, approval decisions, publishing, destructive operations, and arbitrary tools require separate reviewed scopes and ADRs.
- Remote Hub hosting remains out of scope until its threat model, transport, access controls, and deployment are separately reviewed.
