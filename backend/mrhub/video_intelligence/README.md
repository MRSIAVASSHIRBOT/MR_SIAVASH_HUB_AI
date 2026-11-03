# MR SIAVASH Video Intelligence

A modular, owner-scoped foundation for video analysis and original video-production workflows.

## Approved product modes

- `faithful_style_reconstruction`: analyze high-level visual techniques and pacing, then create a new prompt without copying protected expression.
- `creative_style_fusion`: combine selected high-level techniques from multiple references into an original visual direction.

## Available foundation

- Bounded Pydantic contracts for analysis requests, beat timelines, and brand identity.
- Local-file FFprobe metadata probing with bounded output, a 12-second timeout, and stream-count limits.
- Bounded local FFmpeg uniform frame sampling: up to 12 JPEG frames, up to 60 seconds of source duration, 1280-pixel maximum width, a 30-second process timeout, and bounded frame output.
- Bounded FFmpeg scene-cut timestamp detection: up to 24 cut boundaries over 60 seconds, validated thresholds, bounded framehash output, and a 30-second timeout. These are heuristic boundaries, not semantic scene descriptions.
- Durable owner-scoped analysis submission using the shared Worker, mandatory idempotency keys, AES-GCM encrypted request payloads, lease-fenced results, and recovery cleanup.
- Worker-side revalidation of asset ownership, bounded metadata probing, transient keyframe extraction, and scene-boundary detection. Extracted JPEG bytes are not persisted.
- Deterministic, provider-neutral prompt composition.
- Authenticated brand-profile CRUD with per-user ownership, unique names per owner, and image-asset ownership validation.
- Authenticated video metadata inspection for owned MP4/QuickTime assets.
- Opt-in multimodal image contracts for Ollama and OpenRouter. Image input is inline base64 only, limited to JPEG/PNG/WebP, at most four images, with per-image and aggregate size bounds. Local and remote Vision processing have separate disabled-by-default settings.

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
- `POST /models/generate` — invoke explicitly enabled local inference; image input additionally requires `MRH_LOCAL_INFERENCE_VISION_ENABLED=true`.
- `POST /models/generate-remote` — invoke explicitly enabled remote inference; image input additionally requires `MRH_REMOTE_INFERENCE_VISION_ENABLED=true`.

## Not implemented yet

- Semantic visual understanding of extracted video frames through a Vision model.
- Motion/camera-movement classification, OCR, and audio transcription.
- Applying a saved brand profile and custom changes during worker analysis.
- Operator UI for analysis progress and review.
- End-to-end timeline editing, compositing, and MP4 rendering/export.

The current video-analysis Worker reports technical and temporal facts only. It explicitly marks semantic visual analysis, audio analysis, and brand application as not performed; enabling a Vision provider does not by itself connect it to the video-analysis pipeline.

## Security and privacy boundaries

- API callers cannot supply arbitrary filesystem paths or remote media URLs. Source assets must belong to the authenticated user.
- Analysis requests are owner-scoped and encrypted at rest. The worker revalidates ownership before accessing each asset, and result writes require the current lease fencing token.
- FFmpeg/FFprobe run without a shell, with finite timeouts, restricted local protocol access, fixed environments, duration/frame/dimension limits, and bounded outputs.
- Inline Vision inputs do not accept filesystem paths or remote URLs. Image processing is disabled by default and must be enabled separately for local and remote inference.
- Remote image processing can send image content to the configured external provider. Do not enable it without an explicit privacy decision and verification that the configured model supports image input.
- Provider credentials remain server-side. Reference media must be user-provided or otherwise authorized.
- Analysis jobs run through the shared Worker; expensive media processing must not execute inside an HTTP request.
