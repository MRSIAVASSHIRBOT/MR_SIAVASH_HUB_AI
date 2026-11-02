# Scheduled content dispatch (v2)

The dispatcher is pull-driven. Construct `ContentScheduleDispatcher(database_path, adapters={...})` and pass it to `WorkerEngine(..., content_schedule_dispatcher=dispatcher)`. Each explicit `WorkerEngine.run_once()` call processes at most one normal task and at most one due content schedule. Application startup does not start a background publishing loop.

## Provider adapter contract

An adapter is registered by platform name (`telegram` or `instagram`) and implements `publish(draft, idempotency_key=...)`, returning `PublishReceipt(provider_post_id=...)` only after provider-confirmed success.

- Raise `TransientPublishError` only when the provider definitively rejected the request and confirms no post was created. The dispatcher retries at most three attempts with bounded backoff.
- Raise `UnknownPublishOutcome` if the request may have reached the provider but confirmation was lost. The schedule is moved to `unknown_outcome` and is not automatically retried.
- Unexpected adapter errors are treated as ambiguous, not safe-to-retry.
- Without a registered adapter, the schedule is marked `failed` with `provider_not_configured`. No external publishing is attempted.

## Safety and recovery

Before calling an adapter, the dispatcher atomically claims one due schedule and rechecks that its owner-scoped draft remains approved and its version and content hash match the approved snapshot. A stale approval fails closed. A `publishing` record left behind for over five minutes is moved to `unknown_outcome` rather than replayed: a process may have stopped after the provider accepted the post.

The schedule's idempotency key is passed to the adapter, but it only prevents remote duplicates if the provider supports and honors that key. The dispatcher cannot promise exactly-once delivery for providers without idempotency support.

## Current integration boundary

This is a dispatcher and worker-injection contract, not a configured social integration. No production Telegram or Instagram adapter is registered by default, and the application does not start a background worker automatically. Actual publishing requires platform-specific adapter implementations, secure credentials, and an explicit worker runner configured with those adapters.

## Telegram adapter

A Telegram Bot API adapter is now available. Configure `MRH_TELEGRAM_BOT_TOKEN` and `MRH_TELEGRAM_CHAT_ID` in the runtime environment (never commit real values). When both settings are present, `WorkerEngine` creates the adapter automatically; it still performs scheduled work only when its explicit `run_once()` method is called. No background loop starts during application startup.

The adapter publishes text and hashtags using `sendMessage`. Telegram does not support a provider idempotency key for this operation, so a transport timeout is treated as `unknown_outcome`, not automatically retried. HTTP 429 responses are retryable; definitive non-retryable 4xx rejection is recorded as failure. Unit tests use mocked HTTP responses and do not contact Telegram.

Instagram is not enabled by this adapter. Its publishing flow requires an Instagram professional account, Graph API credentials, and an externally reachable media URL; the current local-only asset endpoint is not a valid public media URL. Do not configure Instagram publishing until that media/credential path is implemented and tested.
