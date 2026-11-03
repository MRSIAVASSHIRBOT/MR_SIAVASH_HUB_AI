# MR SIAVASH Video Intelligence

A modular, owner-scoped foundation for video analysis and prompt generation.

## Approved product modes

- `faithful_style_reconstruction`: analyze high-level visual techniques and pacing, then create a new prompt without copying protected expression.
- `creative_style_fusion`: combine selected high-level techniques from multiple references into an original visual direction.

## Available foundation

- Bounded Pydantic contracts for analysis requests, beat timelines, and brand identity.
- Local-file FFprobe metadata probing with a timeout and a fixed output-size check.
- Bounded local FFmpeg uniform frame sampling: up to 12 JPEG frames, up to 60 seconds of source duration, 1280-pixel maximum width, 30-second process timeout, and bounded frame output.
- Bounded FFmpeg scene-cut timestamp detection: up to 24 cut boundaries over 60 seconds, threshold validation, 640-pixel post-selection hash frames, bounded framehash output, and a 30-second timeout. Results are heuristic cut boundaries, not semantic scene descriptions.
- Deterministic, provider-neutral prompt composition that validates detected scene-cut timestamps and carries them into per-beat timing cues without treating heuristic cuts as semantic descriptions.
- Authenticated brand-profile CRUD with per-user ownership, unique names per owner, and image-asset ownership validation.
- Authenticated video metadata inspection for owned MP4/QuickTime assets.
- Durable owner-scoped analysis submission with mandatory idempotency keys, AES-GCM encrypted request payloads, lease-fenced results, and worker recovery cleanup.
- Bounded admission of up to two active analyses per owner and 25 globally; idempotent retries are resolved before capacity enforcement.
- Admission accepts only assets in `stored` or `processed` state and the Worker rechecks readiness before analysis to close a concurrent-transcode race.
- Inline brand logos must resolve to owner-scoped image assets; missing, foreign-owner, or non-image references are rejected.
- Worker-side bounded metadata probing, up to 12 transient keyframes, and up to 24 scene-cut timestamps per source asset; extracted JPEG bytes are not persisted.
- Optional local Ollama vision analysis over the transient keyframes, with a strict image-byte budget, finite timeout, structured output validation, and observations bound to actual extracted timestamps. It is disabled by default and never falls back to a remote model.

## API surface

All endpoints require an authenticated owner session:

- `POST /video-intelligence/prompts/compose` — returns a composed prompt; it does not invoke a model or render a video.
- `GET /video-intelligence/generation/providers` — lists explicitly registered generation adapters without probing or starting work. It currently returns `provider_unavailable`; no generation provider is configured.
- `GET /video-intelligence/brands` — list the current owner's brand profiles.
- `POST /video-intelligence/brands` — create an owner-scoped brand profile.
- `GET /video-intelligence/brands/{profile_id}` — retrieve an owned profile.
- `PUT /video-intelligence/brands/{profile_id}` — update an owned profile.
- `DELETE /video-intelligence/brands/{profile_id}` — delete an owned profile.
- `GET /video-intelligence/assets/{asset_id}/metadata` — inspect technical metadata for an owned video asset.
- `POST /video-intelligence/analyses` — queue analysis for 1–5 owned video assets. Requires an `Idempotency-Key` header; the encrypted request is processed by the shared Worker.
- `GET /video-intelligence/analyses/{analysis_id}` — retrieve status and bounded results for an analysis owned by the current user.
- `POST /video-intelligence/analyses/{analysis_id}/prompts/compose` — compose one prompt per source asset from a completed, validated semantic analysis. Requires an owned analysis and does not start video generation.

## Analysis scope and remaining work

The durable Worker always reports technical metadata, sampled keyframe timestamps, and heuristic scene-cut timestamps. If local vision is explicitly enabled and an installed vision-capable Ollama model is configured, it also returns evidence-linked visual observations tied to actual sampled timestamps.

Configure `MRH_LOCAL_VISION_ENABLED=true`, `MRH_LOCAL_VISION_MODEL=<installed-model>`, and optionally `MRH_LOCAL_VISION_TIMEOUT_SECONDS=120`. Ollama must be running on the configured loopback-only `MRH_LOCAL_INFERENCE_BASE_URL`. No model is downloaded automatically, and there is no remote fallback. If vision is disabled or unavailable, the job completes with an explicit semantic-analysis status rather than fabricated descriptions.

The dashboard provides an authenticated workflow to select owned video assets, submit an idempotent analysis job, manually refresh its status, inspect technical/semantic results, and compose/copy one prompt per source asset. The separate pull-worker process must be running (`python -m mrhub.worker_service`) for queued analyses to execute; the API does not start background execution implicitly.

Audio transcription, OCR, dedicated motion analysis, automatic brand-profile application, advanced operator controls, durable generation jobs, production generation handoff, and end-to-end rendering remain unimplemented. A strict provider-neutral `VideoGenerationProvider` contract and explicit registry are now present, including a bounded streaming interface for generated bytes (no arbitrary output URL fetch). No provider adapter is registered. Generation requests must remain unavailable until an adapter has passed review and is explicitly configured. Prompt composition returns text and timeline metadata only; it never invokes a generator. Windows/Ollama execution still requires validation on the target machine.

## Security boundaries

The API does not accept arbitrary filesystem paths or remote URLs as media inputs. Analysis requests are owner-scoped and encrypted at rest with the existing authenticated payload envelope. The worker revalidates ownership before accessing each asset, and result writes require the current lease fencing token. During probing, frame extraction, scene detection, and optional local vision, the worker holds a per-asset use record bound to its task, owner, and execution fencing token. Deletion of an asset or its derivatives and the start of transcoding are blocked while any use record remains. The worker releases its exact record in a `finally` path; stale-worker recovery removes orphaned records only after the task exceeds the recovery age and its execution lease has expired. Lease expiry alone does not trigger file deletion because an FFmpeg child process may still be reading the source. Frame extraction and scene-boundary detection remain internal-only: callers must resolve a user-owned asset through the authenticated media repository. FFmpeg is invoked without a shell, with a restricted local protocol whitelist, finite timeout, fixed environment, duration/frame/dimension limits, and bounded outputs. Expensive analysis must be submitted to the shared job engine rather than run inside an HTTP request. The local vision adapter accepts only loopback Ollama endpoints and never falls back to a remote provider. Provider credentials must remain server-side. Reference media must be user-provided or otherwise authorized.


## Durable generation job persistence

The generation-job repository stores owner-scoped job metadata and AES-GCM encrypted
request payloads, with authenticated binding to the generation ID and owner. Its
idempotency key is scoped to the owner and the canonical digest includes the source
analysis, provider, model, and request options. Reusing a key with a different request
is rejected.

New records remain in the `prepared` state. This is intentional: the repository does
not enqueue a task, contact a provider, or claim that generation has started. A future
worker handoff must verify an explicitly registered provider before moving a job to
`queued`. The `unknown_outcome` state retains its encrypted payload for reconciliation;
it must never trigger a blind second submission. The API and worker dispatch are not
yet wired to this repository.


## Generated output asset finalization

A successful provider result is not proof that a valid video file exists. Before finalization, the output must match an internal media storage key, remain within the 100 MB budget, and pass an independent local FFprobe check. Measured duration and dimensions must agree with provider metadata. The selected provider, model, and provider job ID are checked.

The MP4 is registered as a new private media asset, while the job success state, asset reference, and measured metadata are committed in one SQLite transaction. Repeated finalization for the same successful job and asset is idempotent. This is a finalization primitive only; no provider adapter, download worker, or public generation endpoint is enabled.


## Bounded provider-output sink

The media repository can create a private output sink for an internally generated MP4 storage key. It writes into a unique mode-0600 temporary file, enforces the configured byte ceiling on every write, and publishes the completed file atomically without replacing an existing target. Leaving the context without commit, or exceeding the byte ceiling, removes the partial file. The caller must compare the provider-reported byte count with the sink's byte count before committing and then call the independent output-finalization routine.

## Validated edit specification and cut-only timeline

Completed analysis results now include a versioned, validated `edit_specification` and a `timeline` built from measured source metadata and detected scene-start timestamps. The specification preserves source references, optional evidence-backed visual summaries, owner-provided brand guidance, and bounded custom directives as data; it does not claim that brand assets or custom changes have been applied to pixels. The timeline allocates the requested duration across available sources, preserves usable scene boundaries, trims only the final allocated scene where necessary, and reports any duration shortfall. Its video track is contiguous and cut-only. Audio processing, graphics, transitions beyond hard cuts, and rendering remain explicitly unimplemented. These contracts are renderer-neutral and contain no executable FFmpeg command fragments.
