# MR SIAVASH Video Intelligence

A modular, owner-scoped video analysis and prompt-generation capability.

## Approved product modes

- `faithful_style_reconstruction`: analyze visual techniques and pacing, then create a new prompt without copying protected expression.
- `creative_style_fusion`: combine selected high-level techniques from multiple references into an original visual direction.

## Current foundation slice

- Pydantic request contracts with bounded input sizes.
- A local-file-only FFprobe metadata probe with a timeout and output cap.
- A deterministic prompt composer that accepts structured analysis facts.\n- Authenticated brand-profile CRUD with per-user ownership, uniqueness, and image-asset ownership validation.

## Not implemented yet

- Persistence and queue-backed processing for video analysis jobs.
- Frame extraction, scene detection, visual understanding, motion analysis, OCR, and audio transcription.
- Queue-backed analysis execution, UI, model-provider adapters, and end-to-end rendering.

## Security boundaries

The service does not accept arbitrary filesystem paths or remote URLs as media inputs. Future API handlers must resolve asset IDs through the existing authenticated media repository, enforce per-user ownership, and submit expensive work to the shared job engine. Provider credentials must remain server-side. Reference media must be user-provided or otherwise authorized.
