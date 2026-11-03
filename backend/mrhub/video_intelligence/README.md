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
- Deterministic, provider-neutral prompt composition.
- Validated renderer-neutral cut-only timelines with bounded scene allocation and contiguous clip validation.
- Bounded FFmpeg MP4 rendering for silent video tracks, with fixed aspect-ratio presets, finite execution limits, bounded FFprobe verification, and temporary-output cleanup.
- Durable owner-scoped render jobs with idempotent submission, lease-fenced worker execution, atomic output-asset registration, and stale-job recovery.
- Authenticated brand-profile CRUD with per-user ownership, unique names per owner, and image-asset ownership validation.
- Authenticated video metadata inspection for owned MP4/QuickTime assets.
- Durable owner-scoped analysis submission with mandatory idempotency keys, AES-GCM encrypted request payloads, lease-fenced results, and worker recovery cleanup.
- Worker-side bounded metadata probing, up to 12 transient keyframes, and up to 24 scene-cut timestamps per source asset; extracted JPEG bytes are not persisted.
- Optional local Ollama vision analysis over the transient keyframes, with a strict image-byte budget, finite timeout, structured output validation, and observations bound to actual extracted timestamps. It is disabled by default and never falls back to a remote model.

## API surface

All endpoints require an authenticated owner session:

- `POST /video-intelligence/prompts/compose` — returns a composed prompt; it does not invoke a model or render a video.
- `GET /video-intelligence/brands` — list the current owner's brand profiles.
- `POST /video-intelligence/brands` — create an owner-scoped brand profile.
- `GET /video-intelligence/brands/{profile_id}` — retrieve an owned profile.
- `PUT /video-intelligence/brands/{profile_id}` — update an owned profile.
- `DELETE /video-intelligence/brands/{profile_id}` — delete an owned profile.
- `GET /video-intelligence/assets/{asset_id}/metadata` — inspect technical metadata for an owned video asset.
- `POST /video-intelligence/analyses` — queue analysis for 1–5 owned video assets. Requires an `Idempotency-Key` header; the encrypted request is processed by the shared Worker.
- `GET /video-intelligence/analyses/{analysis_id}` — retrieve status and bounded results for an analysis owned by the current user.
- `POST /video-intelligence/analyses/{analysis_id}/renders` — queue a silent cut-only MP4 render from a completed owned analysis. Requires an `Idempotency-Key` header.
- `GET /video-intelligence/renders/{render_id}` — retrieve owner-scoped render status and the generated media asset ID when complete.
- `GET /content/assets/{asset_id}/file` — download the generated MP4 using the existing owner-scoped media endpoint.

## Analysis scope and remaining work

The durable Worker always reports technical metadata, sampled keyframe timestamps, and heuristic scene-cut timestamps. If local vision is explicitly enabled and an installed vision-capable Ollama model is configured, it also returns evidence-linked visual observations tied to actual sampled timestamps.

Configure `MRH_LOCAL_VISION_ENABLED=true`, `MRH_LOCAL_VISION_MODEL=<installed-model>`, and optionally `MRH_LOCAL_VISION_TIMEOUT_SECONDS=120`. Ollama must be running on the configured loopback-only `MRH_LOCAL_INFERENCE_BASE_URL`. No model is downloaded automatically, and there is no remote fallback. If vision is disabled or unavailable, the job completes with an explicit semantic-analysis status rather than fabricated descriptions.

The separate pull-worker process must be running (`python -m mrhub.worker_service`) for queued analyses to execute; the API does not start background execution implicitly.

Audio transcription, OCR, dedicated motion analysis, prompt synthesis from semantic results, operator UI, production generation handoff, and audio/text/graphics timeline tracks remain unimplemented. The current renderer produces a silent cut-only MP4; transitions beyond hard cuts and creative motion effects are not yet rendered. Windows/Ollama execution and real-media end-to-end acceptance still require validation on the target machine.

## Security boundaries

The API does not accept arbitrary filesystem paths or remote URLs as media inputs. Analysis requests are owner-scoped and encrypted at rest with the existing authenticated payload envelope. Analysis and render workers revalidate source ownership before accessing media. Render output metadata and terminal job state are committed atomically only while the current lease fencing token is valid. Frame extraction and scene-boundary detection remain internal-only: callers must resolve a user-owned asset through the authenticated media repository. FFmpeg is invoked without a shell, with a restricted local protocol whitelist, finite timeout, fixed environment, duration/frame/dimension limits, and bounded outputs. Expensive analysis must be submitted to the shared job engine rather than run inside an HTTP request. The local vision adapter accepts only loopback Ollama endpoints and never falls back to a remote provider. Provider credentials must remain server-side. Reference media must be user-provided or otherwise authorized.
