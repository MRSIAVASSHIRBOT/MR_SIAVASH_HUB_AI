# Zero-cost runtime architecture

- **Status:** Accepted as the deployment constraint
- **Date:** 2026-11-23
- **Monthly infrastructure budget:** USD 0
- **Scope:** MR_SIAVASH_HUB_AI, MR_SIAVASH_EL_AI, MR_SIAVASH_EL_AGENT, and MR_SIAVASH_AI

## Decision

The ecosystem is local-first. No production dependency may require a paid host, paid database, paid model API, paid tunnel, paid media service, or a credit card that can incur usage charges. Free-tier services are optional edge components, not the source of truth for user data.

The existing paid Render blueprint is **not** a zero-cost deployment target. Do not create or activate it while the budget is zero. It intentionally depends on a paid Starter instance and persistent disk. A free Render instance is not an acceptable drop-in replacement because the current Hub stores state in SQLite and requires durable storage shared by the API and worker.

## Runtime placement

| Component | Zero-cost placement | Responsibilities |
|---|---|---|
| HUB_AI | User-owned Windows PC; SQLite on local disk | Source of truth, API, scheduler, workflow engine, durable queue, audit log |
| Local inference | Ollama on the PC | Local LLM inference; no paid model API by default |
| EL_AGENT | Windows desktop first; Android as a separately tested client | Local tools, permissioned actions, device status |
| EL_AI | Local bot bridge/client plus a lightweight Cloudflare Worker ingress if needed | Telegram update validation, bounded queue handoff, bot orchestration through Hub |
| MR_SIAVASH_AI | Existing GitHub Pages deployment | Static public website and documentation |
| Cloudflare Workers | Free plan only, optional | Small stateless ingress/gateway tasks; never run the Hub's Python API or video rendering |
| Cloudflare D1 | Free plan only, optional and isolated | Small webhook inbox/outbox metadata only after schema, quotas, retention, and recovery tests pass |

## Data and availability rules

1. Local SQLite remains authoritative for tasks, workflow state, credentials references, audit history, and durable user data.
2. Cloudflare edge storage is a transport buffer, not the canonical database. Do not mirror the full Hub database to D1.
3. Do not bind, query, migrate, or otherwise modify the existing `gshop-db` database or Gshop routes/Workers.
4. The `mr-siavash-el-ir-bot-state` D1 binding was verified against the live Worker. A read-only schema query confirmed four application tables (`bridge_nonces`, `telegram_jobs`, `telegram_processed_updates`, and `telegram_sessions`) plus four named indexes. Row counts and message contents were not queried. Keep this database limited to the edge transport queue; it is not the Hub's canonical store. Do not alter its schema or data until ownership, retention, quota, and recovery procedures are reviewed.
5. A local PC being offline means local tasks and model inference are unavailable. The public website can remain available; inbound bot updates may only be buffered within an explicitly tested edge queue and its retention limits.
6. No free-tier service is assumed to provide an always-on Python process, durable local filesystem, guaranteed uptime, or unlimited execution.
7. Video/image generation and editing remain local/manual or use already available non-billed capabilities. No cloud render worker is included in the zero-cost baseline.
8. Backups must be created locally, integrity-checked, encrypted where appropriate, and copied by the owner to a separate location. Git is not a database backup.

## Cost and quota guardrails

- Cloudflare Workers Free currently documents 100,000 requests/day and 10 ms CPU per request. Keep handlers short, bounded, and fail closed.
- Cloudflare D1 Free currently documents 5 million rows read/day, 100,000 rows written/day, 500 MB per database, and 5 GB total account storage. Daily row limits are enforced; queries fail until the UTC reset after a limit is reached.
- Cloudflare Pages Free currently documents up to 500 builds/month, one concurrent build, 20,000 files per site, and 25 MiB per asset.
- GitHub Actions standard hosted runners are free for public repositories. Private-repository included minutes depend on the account plan and may become billable if exceeded; do not enable paid overages.
- These are provider-published quotas, not an uptime or permanent-free guarantee. Review current plan limits before relying on them.

## Deployment gates

Before enabling any edge integration:
- Verify the account is on a free plan and paid usage/overages are disabled or blocked where the provider supports it.
- Set the strictest available spending limit and usage alerts.
- Use separate credentials for each component; never commit secrets.
- Apply request, payload, retention, concurrency, and retry limits.
- Add idempotency keys and dead-letter handling for webhook delivery.
- Test offline recovery, duplicate delivery, queue expiry, and local database restore.
- Do not provision paid infrastructure or change billing settings without explicit owner approval.

## Acceptance criteria for the zero-cost baseline

- Hub API and worker start together on the local PC and share the same local SQLite database.
- Local Ollama connectivity is optional and health-checked; the system remains usable without it.
- A restart preserves task and audit state.
- Backup and restore tests pass on a separate copy of the database.
- The website remains independently deployable as static content.
- Telegram ingress either delivers idempotently to the local Hub or reports a bounded, recoverable unavailable state; it must not silently lose updates.
- No production path depends on Render, paid API keys, or paid cloud storage.
- Monthly infrastructure charges remain USD 0.

## Explicitly out of scope

A continuously available cloud-hosted Python Hub, always-on video rendering, guaranteed 24/7 bot processing while the PC is offline, and managed production database hosting cannot be promised under a USD 0 budget. They require a separately approved infrastructure budget or a change in availability requirements.
