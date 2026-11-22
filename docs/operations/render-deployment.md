# Render deployment (single-instance, persistent runtime)

This deployment target is deliberately a **single paid web service**. The Hub API, Hub pull worker, and EL_AI Cloudflare-bridge consumer run as three supervised processes in one instance. The Hub API and worker share one durable SQLite file; EL_AI uses a separate state directory on the same persistent disk. Do not scale this service horizontally or create a second Hub worker service with the same SQLite file.

## Required host configuration

The repository includes `render.yaml`. Before creating the service, review Render's current Starter plan and 10 GB persistent-disk pricing in the Render dashboard. At the currently published rates, Starter compute is about $7/month and a 10 GB persistent disk is about $2.50/month, for a base estimate of $9.50/month before bandwidth overages, taxes, or other account charges. Starter has 0.5 CPU and 512 MB RAM; this is a constrained size for three Python processes and FFmpeg workloads, so production suitability is not yet established. A Standard service is currently listed at about $25/month (1 CPU, 2 GB RAM), making the same disk configuration about $27.50/month before extras. The blueprint remains on Starter pending explicit budget review; do not deploy until the account owner/guardian has reviewed the exact dashboard charges and approved them. Disk capacity is finite; production media retention still needs monitoring and a cleanup/quota policy before high-volume use.

The following values are intentionally not synchronized from the repository and must be entered through Render's secret environment UI. Never put their values in Git or chat:

- `MRH_WORKFLOW_PAYLOAD_KEY`: generate a URL-safe Base64 encoding of exactly 32 cryptographically random bytes. Keep it stable and back it up securely; losing it makes queued encrypted workflow payloads unreadable.
- `MRH_OWNER_SETUP_TOKEN`: a separate, high-entropy one-time bootstrap credential. Do not reuse the workflow key or any Telegram/Cloudflare secret.
- `EL_AI_CREDENTIAL_ENCRYPTION_KEY`: base64-encoded 32 random bytes used by the AES-256-GCM file store. Keep it stable and back it up securely; losing it makes the paired Hub credentials unreadable.
- `TELEGRAM_BRIDGE_SHARED_SECRET`: must exactly match the Cloudflare Worker `BRIDGE_SHARED_SECRET` value. Do not read it back or expose it in logs.
- `TELEGRAM_OWNER_IDS`: numeric Telegram owner ID(s); these must match the Cloudflare Worker allowlist.

The service sets `MRH_REQUIRE_WORKER_FOR_READINESS=true`. The `/ready` endpoint therefore remains unhealthy until the database migrations and the Hub worker heartbeat are both healthy. EL_AI starts the Cloudflare bridge consumer and stores only AES-GCM encrypted Hub credentials under `/var/data/el-ai`; its 32-byte encryption key is supplied through Render's secret environment UI. The persistent disk is mounted at `/var/data`.

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
- The API, Hub worker, and EL_AI bridge consumer are supervised by one startup script and share the same service environment. Shutdown signals are forwarded to all three processes, and an unexpected exit of any process terminates the service. The EL_AI package is pinned to a reviewed Git commit in the build command.
- The local Ollama, local code engine, and loopback-only MCP integrations remain disabled/unavailable in this cloud deployment unless separately redesigned and secured.
- A successful Render deployment is not proof that Telegram webhook ingress, bridge consumption, Hub authentication, or message replies work. Run the full end-to-end acceptance checklist before declaring the bot online.
- Never store real Telegram bot tokens, Cloudflare bridge secrets, owner passwords, or session tokens in Git.
