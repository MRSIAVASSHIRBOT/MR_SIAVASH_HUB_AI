# Render deployment: isolated Hub and EL_AI services

This Blueprint defines two separate paid services in Frankfurt:

Both services explicitly set `autoDeployTrigger: off`. Git pushes therefore do not deploy either service automatically; use a reviewed manual deploy only after the Blueprint, dependency pin, CI, and service configuration have been checked.

1. **Hub web service** — runs the Hub API and its SQLite-backed worker. These two processes share the Hub service's persistent disk because the current database is SQLite.
2. **EL_AI background worker** — runs the Cloudflare Telegram bridge consumer in a separate Render service, with its own environment, process identity, and persistent disk. It has no Hub database mount and receives neither Hub master secret nor the one-time owner-setup token.

Render background workers can send requests over the private network but do not expose a public URL. Persistent disks are private to the service instance that owns them. See [Render private networking](https://render.com/docs/private-network) and [persistent disks](https://render.com/docs/disks).

## Service boundary and network policy

The EL_AI worker receives the Hub API's private `host:port` through Blueprint `fromService.property: hostport`. It passes this value as a bare host:port in `HUB_API_BASE_URL`. EL_AI accepts that form only when `HUB_ALLOW_RENDER_PRIVATE_NETWORK=true`, and only when it is a single-label internal hostname with an explicit port. It rejects public DNS names, IP addresses, malformed hostnames, and ordinary HTTP URLs under this setting. Public Hub URLs still require HTTPS and `HUB_ALLOW_REMOTE=true`.

The Hub service remains a web service so existing authenticated Hub API clients can continue to reach it. The EL_AI worker uses Render's private hostname instead of the public URL. Hub authorization remains application-level: owner-initiated pairing issues scoped credentials, and EL_AI calls only the dedicated Telegram integration routes. The worker must never receive the Hub database file, `MRH_WORKFLOW_PAYLOAD_KEY`, or `MRH_OWNER_SETUP_TOKEN`.

## Resource and cost review

The Blueprint currently declares:
- Hub web service: Starter plan, Frankfurt, 10 GB persistent disk.
- EL_AI background worker: Starter plan, Frankfurt, separate 1 GB persistent disk.

This is a two-compute-service design and therefore costs more than the previous single-service layout. Exact current compute and disk charges, taxes, bandwidth, and workspace-specific pricing must be reviewed by the account owner/guardian in the Render Dashboard before any Blueprint approval. No Render service or disk is created by changing this repository, and this work does not authorize provisioning. Keep Blueprint auto-sync disabled until the first sync plan and its complete cost are reviewed and explicitly approved.

Starter resources remain unverified for production workload. The Hub and EL_AI worker need runtime memory/CPU measurements; FFmpeg processing should remain disabled or separately provisioned until capacity is validated. Keep one Hub instance while using SQLite.

## Required secrets

Enter secret values only in the Render service's Environment page. Never place them in Git, chat, URLs, or logs.

**Hub service only**
- `MRH_WORKFLOW_PAYLOAD_KEY`: URL-safe Base64 encoding of exactly 32 random bytes. Keep stable and back it up securely; losing it makes queued encrypted workflow payloads unreadable.
- `MRH_OWNER_SETUP_TOKEN`: separate, high-entropy one-time bootstrap credential. Do not reuse another secret.

**EL_AI worker only**
- `EL_AI_CREDENTIAL_ENCRYPTION_KEY`: base64-encoded 32 random bytes for AES-256-GCM encrypted credential storage. Keep stable and back it up securely.
- `TELEGRAM_BRIDGE_SHARED_SECRET`: must exactly match the Cloudflare Worker `BRIDGE_SHARED_SECRET`.
- `TELEGRAM_OWNER_IDS`: numeric Telegram owner ID(s). For the current single-owner Worker, this must match `ALLOWED_TELEGRAM_USER_ID` exactly.

The Cloudflare Worker retains its own secret bindings. No Worker secret value should be read back or copied into Git.

## Initialize the Hub owner

After the Hub web service is deployed, send one HTTPS request to `POST /auth/setup` with a unique password of at least 14 characters and header `X-MRH-Owner-Setup-Token`. Do not put either value in source control, chat, URL parameters, or logs.

The endpoint compares the supplied credential in constant time, ignores forwarded-IP headers, and rejects a second initialization. Immediately after receiving `owner_initialized`:

1. Remove `MRH_OWNER_SETUP_TOKEN` from the Hub service's Render environment and redeploy.
2. Log in through `POST /auth/login` over HTTPS.
3. Store the returned session token only in the intended trusted client/secret store.
4. Confirm `/ready` reports both the database and Hub worker ready.

The local loopback-only setup path remains supported for local development. A remote setup request without the one-time deployment credential is rejected.

## Operational boundaries

- Keep exactly one Hub service instance while using SQLite. Do not horizontally scale it or add a second Hub worker against the same database.
- Hub API and Hub worker remain supervised together; signals are forwarded to both, and an unexpected exit stops the service.
- EL_AI runs independently as a background worker. Its state and encrypted paired credentials live only on its own disk.
- The EL_AI package is pinned to the reviewed credential-store commit in the worker build command. Update this pin only after the corresponding EL_AI change has been merged and reviewed.
- The EL_AI worker uses Cloudflare bridge mode and must never start Telegram `getUpdates`; local polling and an active webhook must not run simultaneously.
- The local Ollama, local code engine, and loopback-only MCP integrations are unavailable in this cloud deployment unless separately redesigned and secured.
- Successful deployment does not prove Telegram ingress, queue consumption, Hub pairing, or message replies. Run the complete end-to-end acceptance checklist before declaring the bot online.
- Never store real Telegram/Cloudflare secrets, owner passwords, or session tokens in Git.
