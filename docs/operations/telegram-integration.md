# Telegram Integration Operations

## Local topology

Run MR_SIAVASH_HUB_AI and MR_SIAVASH_EL_AI on the same trusted machine. The Hub should remain bound to loopback (default 127.0.0.1). EL_AI uses outbound Telegram long polling and calls the Hub over loopback. Do not expose the Hub port publicly or use a public tunnel.

## Pairing procedure

1. Start Hub locally and authenticate to its owner API/UI.
2. In the Telegram bot's private chat, use the bot's pairing flow to obtain the Telegram numeric user ID and EL_AI client UUID.
3. Create a Hub pairing challenge for that exact numeric ID and client UUID. Select only the scopes needed.
4. Enter the one-time code into the same private chat within five minutes.
5. EL_AI exchanges it and stores the access/refresh credentials in a protected local secret store.
6. Confirm the bot can read /integrations/telegram/status.
7. Revoke the client from the Hub when the device is lost, replaced or no longer trusted.

## Credential lifetime

Access tokens expire after 15 minutes. Refresh tokens expire after 30 days and can be revoked with the client. The Hub stores only SHA-256 token hashes. Never log or paste the raw tokens.

## Current release limitations

The Hub API pairing and scoped task/memory routes are introduced by ADR-0007. EL_AI still needs its secure credential store and /pair command before this flow is usable end-to-end. No production bot has been deployed.
