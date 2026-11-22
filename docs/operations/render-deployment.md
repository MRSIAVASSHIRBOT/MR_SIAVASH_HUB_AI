# Render deployment (single-instance, persistent runtime)

This deployment target is deliberately a **single paid web service**. The current Hub uses SQLite and a separate pull-driven worker. Both processes must share one durable database file, so the Render service mounts one persistent disk and starts the API and worker in the same instance. Do not scale this service horizontally or create a second worker service with the same SQLite file.

## Required host configuration

The repository includes `render.yaml`. Before creating the service, review Render's current plan and persistent-disk pricing in the Render dashboard. The blueprint selects the Starter plan in Frankfurt and a 1 GB persistent disk. Do not deploy until the account owner has reviewed and accepted the displayed charges.

Two environment variables are intentionally not synchronized from the repository and must be entered as secrets in Render:

- `MRH_WORKFLOW_PAYLOAD_KEY`: generate a URL-safe Base64 encoding of exactly 32 cryptographically random bytes. Keep it stable and back it up securely; losing it makes queued encrypted workflow payloads unreadable.
- `MRH_OWNER_SETUP_TOKEN`: a separate, high-entropy one-time bootstrap credential. Do not reuse the workflow key or any Telegram/Cloudflare secret.

The service sets `MRH_REQUIRE_WORKER_FOR_READINESS=true`. The `/ready` endpoint therefore remains unhealthy until the database migrations and the worker heartbeat are both healthy. The persistent disk is mounted at `/var/data`.

## Initialize the owner account

After deployment, send one HTTPS request to `POST /auth/setup` with a JSON body containing a unique password of at least 14 characters and the header `X-MRH-Owner-Setup-Token` containing the one-time bootstrap credential. Do not put either value in source control, chat messages, URL parameters, or logs.

The endpoint compares the supplied credential in constant time, ignores forwarded-IP headers, and still rejects a second initialization. Immediately after receiving `owner_initialized`:

1. Remove `MRH_OWNER_SETUP_TOKEN` from the Render environment and redeploy.
2. Log in through `POST /auth/login` over HTTPS.
3. Store the returned session token only in the intended trusted client/secret store.
4. Confirm `/ready` reports both the database and worker ready.

The local loopback-only setup path remains supported for local development. A remote setup request without the one-time deployment credential is rejected.

## Operational boundaries

- Keep exactly one service instance while using SQLite.
- Do not enable horizontal scaling; SQLite is not a distributed database.
- The worker and API are supervised by one startup script and share the same mounted disk and environment.
- The local Ollama, local code engine, and loopback-only MCP integrations remain disabled/unavailable in this cloud deployment unless separately redesigned and secured.
- A successful Render deployment is not proof that Telegram webhook ingress, bridge consumption, Hub authentication, or message replies work. Run the full end-to-end acceptance checklist before declaring the bot online.
- Never store real Telegram bot tokens, Cloudflare bridge secrets, owner passwords, or session tokens in Git.
