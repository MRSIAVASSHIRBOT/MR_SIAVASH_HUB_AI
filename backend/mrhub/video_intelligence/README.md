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
- Authenticated brand-profile CRUD with per-user ownership, unique names per owner, and image-asset ownership validation.
- Authenticated video metadata inspection for owned MP4/QuickTime assets.
- Owner-scoped asynchronous scene-analysis jobs executed by the shared pull-driven worker, with per-owner/global queue caps and sanitized timestamp-only results.

## API surface

All endpoints require an authenticated owner session:

- `POST /video-intelligence/prompts/compose` — returns a composed prompt; it does not invoke a model or render a video.
- `GET /video-intelligence/brands` — list the current owner's brand profiles.
- `POST /video-intelligence/brands` — create an owner-scoped brand profile.
- `GET /video-intelligence/brands/{profile_id}` — retrieve an owned profile.
- `PUT /video-intelligence/brands/{profile_id}` — update an owned profile.
- `DELETE /video-intelligence/brands/{profile_id}` — delete an owned profile.
- `GET /video-intelligence/assets/{asset_id}/metadata` — inspect technical metadata for an owned video asset.
- `POST /video-intelligence/assets/{asset_id}/scene-jobs` — queue bounded scene-cut detection for an owned video asset (HTTP 202).
- `GET /video-intelligence/scene-jobs/{job_id}` — read an owned job's state and sanitized results.
- `POST /video-intelligence/scene-jobs/{job_id}/cancel` — cancel an owned queued/running job.

## Not implemented yet

- Semantic scene understanding and motion analysis.
- OCR and audio transcription.
- Model-provider adapters, operator UI, and end-to-end video rendering.

## Security boundaries

The API does not accept arbitrary filesystem paths or remote URLs as media inputs. Frame extraction and scene-boundary detection are internal-only: callers must resolve a user-owned asset through the authenticated media repository. FFmpeg is invoked without a shell, with a restricted local protocol whitelist, finite timeout, fixed environment, duration/frame/dimension limits, and bounded outputs. Scene detection is submitted to the shared job engine and runs only when a worker explicitly calls `run_once()`; application startup does not execute queued work implicitly. Per-owner and global active-job limits bound queue growth. Provider credentials must remain server-side. Reference media must be user-provided or otherwise authorized.
