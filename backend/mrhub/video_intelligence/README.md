# MR SIAVASH Video Intelligence

A modular, owner-scoped foundation for video analysis and prompt generation.

## Approved product modes

- `faithful_style_reconstruction`: analyze high-level visual techniques and pacing, then create a new prompt without copying protected expression.
- `creative_style_fusion`: combine selected high-level techniques from multiple references into an original visual direction.

## Available foundation

- Bounded Pydantic contracts for analysis requests, beat timelines, and brand identity.
- Local-file FFprobe metadata probing with a timeout and a fixed output-size check.
- Deterministic, provider-neutral prompt composition.
- Authenticated brand-profile CRUD with per-user ownership, unique names per owner, and image-asset ownership validation.

## API surface

All endpoints require an authenticated owner session:

- `POST /video-intelligence/prompts/compose` — returns a composed prompt; it does not invoke a model or render a video.
- `GET /video-intelligence/brands` — list the current owner's brand profiles.
- `POST /video-intelligence/brands` — create an owner-scoped brand profile.
- `GET /video-intelligence/brands/{profile_id}` — retrieve an owned profile.
- `PUT /video-intelligence/brands/{profile_id}` — update an owned profile.
- `DELETE /video-intelligence/brands/{profile_id}` — delete an owned profile.

## Not implemented yet

- Persisted video-analysis jobs and queue-backed analysis execution.
- Secure asset-ID resolution for source video inputs.
- Frame extraction, scene detection, visual understanding, motion analysis, OCR, and audio transcription.
- Operator UI, model-provider adapters, and end-to-end video rendering.

## Security boundaries

The current API does not accept arbitrary filesystem paths or remote URLs as media inputs. Future analysis handlers must resolve asset IDs through the authenticated media repository, enforce per-user ownership, and submit expensive work to the shared job engine. Provider credentials must remain server-side. Reference media must be user-provided or otherwise authorized.
