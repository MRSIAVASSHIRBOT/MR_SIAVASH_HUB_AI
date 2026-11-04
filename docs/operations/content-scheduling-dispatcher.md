# Scheduled content dispatch (v2)

The dispatcher is pull-driven. Construct `ContentScheduleDispatcher(database_path, adapters={...})` and pass it to `WorkerEngine(..., content_schedule_dispatcher=dispatcher)`. Each explicit `WorkerEngine.run_once()` call processes at most one normal task and at most one due content schedule. Application startup does not start a background publishing loop.

## Provider adapter contract

An adapter is registered by platform name (`telegram` or `instagram`) and implements `publish(draft, idempotency_key=...)`, returning `PublishReceipt(provider_post_id=...)` only after provider-confirmed success.

- Raise `TransientPublishError` only when the provider definitively rejected the request and confirms no post was created. The dispatcher retries at most three attempts with bounded backoff.
- Raise `UnknownPublishOutcome` if the request may have reached the provider but confirmation was lost. The schedule is moved to `unknown_outcome` and is not automatically retried.
- Unexpected adapter errors are treated as ambiguous, not safe-to-retry.
- Without a registered adapter, the schedule is marked `failed` with `provider_not_configured`. No external publishing is attempted.

## Safety and recovery

The final provider-confirmation write is conditional on the schedule still being in `publishing`. If stale-worker recovery or another quarantine transition wins while a provider call is in flight, a late receipt cannot overwrite that state or emit a `content.schedule_published` success audit event; the dispatcher returns the durable state with `schedule_state_changed_before_confirmation_commit`.

Before calling an adapter, the dispatcher atomically claims one due schedule and rechecks that its owner-scoped draft remains approved and its version and content hash match the approved snapshot. A stale approval fails closed. A `publishing` record left behind for over five minutes is moved to `unknown_outcome` rather than replayed: a process may have stopped after the provider accepted the post.

The schedule's idempotency key is passed to the adapter, but it only prevents remote duplicates if the provider supports and honors that key. The dispatcher cannot promise exactly-once delivery for providers without idempotency support.

## Current integration boundary

The dispatcher is integrated into `WorkerEngine` through its optional content-schedule hook. When a worker is explicitly constructed, it loads only the provider adapters whose complete credentials are configured. It processes at most one due content schedule per explicit `run_once()` call; application startup does not start a background publishing loop. Without complete provider configuration, no adapter is registered and schedules fail closed with `provider_not_configured` when dispatched.

## Telegram adapter

A Telegram Bot API adapter is available. Configure `MRH_TELEGRAM_BOT_TOKEN` and `MRH_TELEGRAM_CHAT_ID` in the runtime environment (never commit real values). When both settings are present, `WorkerEngine` creates the adapter automatically; it still performs scheduled work only when its explicit `run_once()` method is called. No background loop starts during application startup.

The adapter publishes text and hashtags using `sendMessage`, and approved JPEG/PNG/MP4 assets using `sendPhoto` or `sendVideo`. Telegram does not support a provider idempotency key for these operations, so a transport timeout is treated as `unknown_outcome`, not automatically retried. HTTP 429 responses are retryable; definitive non-retryable 4xx rejection is recorded as failure. Unit tests use mocked HTTP responses and do not contact Telegram.

## Instagram image adapter

An Instagram Graph API image adapter is available and is constructed by the same explicit adapter factory when all of `MRH_INSTAGRAM_ACCESS_TOKEN`, `MRH_INSTAGRAM_USER_ID`, and `MRH_INSTAGRAM_GRAPH_API_VERSION` are configured. The dispatcher supports approved JPEG/PNG assets by creating a short-lived signed HTTPS media URL using `MRH_PUBLIC_MEDIA_BASE_URL` and `MRH_PUBLIC_MEDIA_SIGNING_KEY`. The public-media origin must route to the application's signed public-media endpoint and must be reachable by Meta's servers; a local path or loopback URL is never passed to the Graph API.

This is an opt-in image-publishing path, not a guarantee of account eligibility or public-host reachability. It does not support Reels/video publishing. Perform the controlled professional-account test in `instagram-publishing.md` before enabling real schedules. The two-step Graph API flow has no general exactly-once guarantee; ambiguous outcomes are quarantined and must be reconciled before retry.


## Approved media attachments for Telegram

A Telegram draft may reference an owner-owned media asset using `media_asset_id`. The draft and each revision retain that ID, and the media ID participates in the content hash so changing or detaching the attachment resets approval. Currently accepted attachments are JPEG, PNG, and MP4 up to 25 MB. Other platforms/media types are rejected until their provider path is implemented.

At dispatch time, the worker resolves the asset again under the draft owner, verifies the generated storage path, file size, and media type, then passes only that server-resolved local file to the Telegram adapter. The adapter uses `sendPhoto` or `sendVideo` with multipart upload and enforces Telegram's 1024-character caption limit. Media is never fetched from a user-provided URL. A missing or inconsistent asset fails the schedule closed before any provider request.

The media upload and adapter tests use synthetic bytes and mocked HTTP; they do not contact Telegram. A real post still requires explicit approval, configured Telegram credentials, and an explicit worker cycle. Ambiguous outcomes are not retried blindly.
