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
- `VideoAssetAnalyzer` composes owner-scoped asset resolution, technical metadata validation, a shared bounded duration, keyframe extraction, scene-cut detection, and source content-hash provenance. The analysis Worker uses this internal service while holding the existing fenced media-use lock; frames remain transient.
- Optional local Ollama vision analysis over the transient keyframes, with a strict image-byte budget, finite timeout, structured output validation, and observations bound to actual extracted timestamps. It is disabled by default and never falls back to a remote model.

## API surface

All endpoints require an authenticated owner session:

- `POST /video-intelligence/prompts/compose` — returns a composed prompt; it does not invoke a model or render a video.
- `GET /video-intelligence/generation/providers` — lists explicitly registered generation adapters without probing or starting work. It currently returns `provider_unavailable`; no generation provider is configured.
- `POST /video-intelligence/analyses/{analysis_id}/generations` — create an owner-scoped generation request only for an explicitly registered provider/model. The durable task starts in `waiting_approval`; the owner must approve the exact task through `POST /tasks/{task_id}/approval` before the pull worker can claim it.
- `GET /video-intelligence/generations/{generation_id}` — return the current owner's durable generation status, progress, output asset metadata and stable error code; provider job identifiers are not exposed.
- `POST /video-intelligence/generations/{generation_id}/reconcile` — explicitly queue a read-only provider lookup for an `unknown_outcome` or `running` job. The Worker uses the original generation idempotency key to find an earlier submission and then polls its known provider job id; it never calls `submit` from the reconciliation path. A lookup miss or provider timeout leaves the job ambiguous and retains the encrypted request. Repeated requests reuse the original task while it is active and reset it only after a completed/failed reconciliation attempt.
- `GET /video-intelligence/brands` — list the current owner's brand profiles.
- `POST /video-intelligence/brands` — create an owner-scoped brand profile.
- `GET /video-intelligence/brands/{profile_id}` — retrieve an owned profile.
- `PUT /video-intelligence/brands/{profile_id}` — update an owned profile.
- `DELETE /video-intelligence/brands/{profile_id}` — delete an owned profile.
- `GET /video-intelligence/assets/{asset_id}/metadata` — inspect technical metadata for an owned video asset.
- `POST /video-intelligence/analyses` — queue analysis for 1–5 owned video assets. Requires an `Idempotency-Key` header; the encrypted request is processed by the shared Worker.
- `GET /video-intelligence/analyses/{analysis_id}` — retrieve status and bounded results for an analysis owned by the current user.
- `POST /video-intelligence/analyses/{analysis_id}/prompts/compose` — compose one prompt per source asset from a completed, validated semantic analysis. The optional pair `timeline_draft_id` + `timeline_draft_version` applies that exact owner-scoped storyboard revision to its matching asset; a stale version returns `409`. Composition never starts video generation.
- `POST /video-intelligence/timeline-drafts` — persist an editable storyboard for an asset in the current owner's completed analysis.
- `GET /video-intelligence/analyses/{analysis_id}/timeline-drafts` — list the current owner's bounded storyboard drafts for one completed analysis.
- `GET /video-intelligence/timeline-drafts/{draft_id}` — retrieve an owned storyboard draft.
- `PUT /video-intelligence/timeline-drafts/{draft_id}` — update an owned draft using `expected_version` optimistic concurrency; stale writes return `409`.
- `POST /video-intelligence/timeline-drafts/{draft_id}/renders` — freeze the saved renderer-compatible draft revision into an immutable owner-scoped snapshot, then queue a cut-only MP4 render bound to that snapshot; requires an `Idempotency-Key` header. A draft without a saved renderer timeline returns `409`.
- `POST /video-intelligence/analyses/{analysis_id}/renders` — legacy-compatible path that queues a silent cut-only MP4 render from the completed analysis timeline; requires an `Idempotency-Key` header.
- `GET /video-intelligence/renders/{render_id}` — retrieve owner-scoped render status and output asset metadata.
- `DELETE /video-intelligence/renders/{render_id}` — cancel queued work immediately or request cooperative cancellation of a running render; the worker owns the final terminal transition after it observes the request.
- `GET /content/assets/{asset_id}/file` — download a completed private render through the existing owner-scoped media route.

## Analysis scope and remaining work

The durable Worker always reports technical metadata, sampled keyframe timestamps, and heuristic scene-cut timestamps. If local vision is explicitly enabled and an installed vision-capable Ollama model is configured, it also returns evidence-linked visual observations tied to actual sampled timestamps.

Configure `MRH_LOCAL_VISION_ENABLED=true`, `MRH_LOCAL_VISION_MODEL=<installed-model>`, and optionally `MRH_LOCAL_VISION_TIMEOUT_SECONDS=120`. Ollama must be running on the configured loopback-only `MRH_LOCAL_INFERENCE_BASE_URL`. No model is downloaded automatically, and there is no remote fallback. If vision is disabled or unavailable, the job completes with an explicit semantic-analysis status rather than fabricated descriptions.

Editable storyboards are owner-scoped per source asset, bounded to 20 ordered non-overlapping beats, and protected by optimistic version checks. The prompt composer can consume a selected draft as the beat/timing override for that asset while retaining the validated semantic style summary. The response records the exact draft ID and version. The dashboard can list, create, edit, save, and compose from these drafts. Draft operations only compose text: they do not call a generation provider, enqueue a generation task, or trigger the separate cut-only FFmpeg renderer.

The local renderer continues to consume the validated `VideoTimeline` stored with the analysis; storyboard beat instructions and natural-language transitions are not passed directly to FFmpeg. A future rendered-edit-decision-list feature must define and validate that separate conversion contract explicitly.

The `render_snapshot` module defines a strict immutable snapshot contract for renderer-compatible timelines: canonical validated timeline JSON, SHA-256 content verification, owner/analysis/draft revision binding, and an idempotency digest that changes when the draft revision changes. The snapshot contract has a dedicated owner-scoped SQLite repository and schema migration. A renderer-compatible `VideoTimeline` and its SHA-256 digest are stored on the same optimistic draft revision; the draft repository verifies completed-analysis ownership, source membership, per-asset source interval bounds against measured media duration, requested duration, aspect ratio, and the draft's primary asset. A snapshot can be created only when its canonical timeline and hash exactly match that persisted draft revision. Repeated identical creation is idempotent, including after the editable draft advances; conflicting content is rejected, snapshot rows cannot be updated in place, and parent draft/analysis deletion is restricted while a snapshot exists.

The new draft-render endpoint freezes the saved renderer timeline and queues a render linked to that immutable snapshot. Snapshot persistence, render-task creation, and idempotency-record creation share one SQLite transaction, so a failed submission cannot leave an orphan snapshot or a task without its snapshot link. Render-job idempotency is bound to the snapshot's owner, analysis, draft ID/version, schema version, and timeline hash. The render job stores the snapshot ID, and the Worker loads that exact owner-scoped snapshot, revalidates its canonical JSON/hash, analysis binding, source membership, and measured source-duration bounds before opening media. A missing or invalid snapshot fails closed; the Worker never falls back to the mutable analysis timeline for snapshot-backed tasks. The older analysis-render endpoint remains available for compatibility and continues to use the analysis timeline.

The dashboard provides an authenticated workflow to select owned video assets, submit an idempotent analysis job, manually refresh its status, inspect technical/semantic results, compose/copy one prompt per source asset, and edit a versioned storyboard. The separate pull-worker process must be running (`python -m mrhub.worker_service`) for queued analyses to execute; the API does not start background execution implicitly.

Audio transcription, OCR, dedicated motion analysis, automatic brand-profile application, and audio/text/graphics timeline tracks remain unimplemented. A bounded FFmpeg renderer now produces silent cut-only MP4 files from completed, validated timelines. It uses fixed output presets, a finite timeout, bounded output size, independent FFprobe verification, and temporary-file cleanup. Durable render jobs are owner-scoped, idempotent, pull-worker driven, and lease-fenced; each request reserves its generated output key before execution so stale recovery can safely remove an unregistered orphan. Source media-use locks are held for the complete render and publication window and released in a `finally` path. The renderer does not add transitions beyond hard cuts, audio, captions, graphics, or generated AI footage. A strict provider-neutral `VideoGenerationProvider` contract and explicit registry are present, but no provider adapter is registered. Generation requests remain unavailable until an adapter has passed review and is explicitly configured. Prompt composition never invokes a generator. Windows/FFmpeg execution and real-media end-to-end acceptance still require validation on the target machine.

## Security boundaries

The API does not accept arbitrary filesystem paths or remote URLs as media inputs. Analysis requests are owner-scoped and encrypted at rest with the existing authenticated payload envelope. The worker revalidates ownership before accessing each asset, and result writes require the current lease fencing token. During probing, frame extraction, scene detection, and optional local vision, the worker holds a per-asset use record bound to its task, owner, and execution fencing token. Deletion of an asset or its derivatives and the start of transcoding are blocked while any use record remains. The worker releases its exact record in a `finally` path; stale-worker recovery removes orphaned records only after the task exceeds the recovery age and its execution lease has expired. Lease expiry alone does not trigger file deletion because an FFmpeg child process may still be reading the source. Frame extraction and scene-boundary detection remain internal-only: callers must resolve a user-owned asset through the authenticated media repository. FFmpeg is invoked without a shell, with a restricted local protocol whitelist, finite timeout, fixed environment, duration/frame/dimension limits, and bounded outputs. Expensive analysis must be submitted to the shared job engine rather than run inside an HTTP request. The local vision adapter accepts only loopback Ollama endpoints and never falls back to a remote provider. Provider credentials must remain server-side. Reference media must be user-provided or otherwise authorized.


## Durable generation job persistence

The generation-job repository stores owner-scoped job metadata and AES-GCM encrypted
request payloads, with authenticated binding to the generation ID and owner. Its
idempotency key is scoped to the owner and the canonical digest includes the source
analysis, provider, model, and request options. Reusing a key with a different request
is rejected.

Generation submission verifies the exact provider/model and its declared capability
before persisting the request. The repository stores the prompt in an AES-GCM envelope,
then atomically links the job to a high-risk `video.generation` task in
`waiting_approval`. The existing owner-authenticated approval API binds the decision
to the task's action fingerprint, including the generation identifier and selected
provider/model. Only an approved task moves to `queued` and becomes eligible for the
pull worker; missing, stale, or rejected approvals cannot dispatch a provider.
Rejection marks the generation failed and removes its encrypted request payload.
Idempotent replay returns the linked task and its current lifecycle state.

The worker verifies the approved task under its lease, checks the exact registered
provider/model again, and records the transition to `submitting` before invoking the
provider. Once provider submission begins, an ambiguous result becomes
`unknown_outcome`; it is never blindly retried. The encrypted payload is retained for
explicit provider-specific reconciliation. An adapter must implement
`find_by_idempotency_key` so a lost submit response can be reconciled to an existing
provider job without creating another job. A lookup miss, timeout, or provider error
never authorizes a resubmission; the local job remains ambiguous until an authoritative
provider result is available. No provider adapter is registered by default, so the
endpoint remains unavailable until an adapter is separately reviewed and configured.


## Generated output asset finalization

A successful provider result is not proof that a valid video file exists. Before finalization, the output must match an internal media storage key, remain within the 100 MB budget, and pass an independent local FFprobe check. Measured duration and dimensions must agree with provider metadata. The selected provider, model, and provider job ID are checked.

The MP4 is registered as a new private media asset, while the job success state, asset reference, and measured metadata are committed in one SQLite transaction. Repeated finalization for the same successful job and asset is idempotent. This is a finalization primitive only; no provider adapter, download worker, or public generation endpoint is enabled.


## Bounded provider-output sink

The media repository can create a private output sink for an internally generated MP4 storage key. It writes into a unique mode-0600 temporary file, enforces the configured byte ceiling on every write, and publishes the completed file atomically without replacing an existing target. Leaving the context without commit, or exceeding the byte ceiling, removes the partial file. The caller must compare the provider-reported byte count with the sink's byte count before committing and then call the independent output-finalization routine.

## Validated edit specification and cut-only timeline

Completed analysis results now include a versioned, validated `edit_specification` and a `timeline` built from measured source metadata and detected scene-start timestamps. The specification preserves source references, optional evidence-backed visual summaries, owner-provided brand guidance, and bounded custom directives as data; it does not claim that brand assets or custom changes have been applied to pixels. The timeline allocates the requested duration across available sources, preserves usable scene boundaries, trims only the final allocated scene where necessary, and reports any duration shortfall. Its video track is contiguous and cut-only. Audio processing, graphics, transitions beyond hard cuts, and rendering remain explicitly unimplemented. These contracts are renderer-neutral and contain no executable FFmpeg command fragments.

## Owner-scoped analysis cancellation

Authenticated owners can cancel an accepted analysis before the worker claims it, or request cooperative cancellation after execution begins. Queued cancellation atomically marks the task and analysis terminal, removes the encrypted request payload, and closes the idempotency record. Running cancellation marks the task as cancelled immediately; the worker checks that state at bounded processing boundaries and cannot overwrite it with a late success. The worker finalizes the analysis row only while holding the current lease/fencing token. Cancellation is idempotent for the owner, hides analyses belonging to other users, and returns a conflict for terminal states that cannot be cancelled.


## Bounded cut-only renderer contract

The renderer consumes only a validated `VideoTimeline` and source paths resolved from the authenticated owner's media repository. It does not accept user-supplied FFmpeg arguments, filter fragments, filesystem paths, or remote URLs. The worker acquires the existing task/fencing-token-bound media-use lease for every unique source before FFmpeg starts, retains all leases through FFprobe verification and output registration, and releases them in `finally`. Deletion/transcoding therefore cannot race the render. Stale recovery releases orphaned source-use locks only after the worker lease has expired and the task has exceeded the recovery threshold.

The current renderer is deliberately silent and cut-only. Output is limited to 125 clips, 60 seconds, fixed aspect-ratio presets, 1920-pixel maximum dimension, a 180-second FFmpeg timeout, and the repository's 100 MB output ceiling. A separate FFprobe process must confirm MP4 format, one video stream, expected dimensions, and duration before publication. Failed or cancelled jobs do not publish an asset. This does not constitute Windows or real-media runtime acceptance.

## Immutable storyboard render snapshots

A saved `VideoTimelineDraft` and the cut-only renderer's `VideoTimeline` are different contracts. Storyboard beats contain editorial/generation intent; they are not executable renderer instructions. A draft may be submitted for local rendering only after the application has produced and persisted its renderer-compatible timeline representation.

The authenticated route `POST /video-intelligence/timeline-drafts/{draft_id}/renders` accepts an idempotency key and resolves the draft under the authenticated owner. Submission validates the saved renderer timeline and its integrity digest, draft revision, analysis association, source asset membership and measured source-duration bounds. It then persists an immutable owner-scoped `VideoRenderTimelineSnapshot` and links the render job to that snapshot.

The snapshot is canonicalized and SHA-256 verified. Its identity binds the owner, analysis, draft and exact draft revision. Snapshot persistence, task creation, render record creation and idempotency binding occur in one database transaction: a failed or conflicting submission must not leave a partially accepted snapshot or task.

The render Worker loads the snapshot referenced by the render job, verifies its ownership and integrity, and validates the contained renderer timeline before resolving source media. It must not fall back to a mutable analysis timeline or a newer draft revision if the snapshot is missing, malformed or inconsistent. A failed validation is a fail-closed render failure, not a reason to reconstruct the request from mutable state.

Migrations 28 and 29 add renderer-timeline/hash persistence and bind render jobs to immutable snapshot records. Regression coverage includes owner isolation, exact revision binding, source bounds, immutable snapshot storage, route-level handoff, rejection of missing/foreign or malformed drafts, atomic rollback, and stale-snapshot submission fencing. Already accepted idempotent retries remain valid after the draft advances; a new render using the stale snapshot is rejected.

This integration does not make the local renderer a full video editor. Rendering remains silent and hard-cut-only. Audio mixing, captions, graphics, motion effects, non-cut transitions and AI-generated footage remain separate capabilities. The dashboard currently has storyboard editing and prompt composition, but an operator-facing action to submit a render from the saved renderer-compatible draft remains a follow-up. Snapshot retention/cleanup policy and target-device workflow acceptance are also outstanding. No external video-generation provider is registered by this change.


## Generation outcome reconciliation

The provider submission path is intentionally single-shot. If a Worker interruption or adapter exception occurs after entering `submit`, the generation becomes `unknown_outcome` and its encrypted request is retained. An owner can explicitly request reconciliation; the original approval-bound task is requeued, and the Worker calls only `find_by_idempotency_key(generation_id)`. A missing lookup result is not proof that the provider did not accept the request, so the local state remains `unknown_outcome` and automatic resubmission is prohibited. When a provider job is found, the Worker records its opaque job id, polls `get_status`, and streams successful output through the bounded private media sink. Output registration is independently probed and lease-fenced. The provider catalog remains empty by default; this flow is exercised with test adapters until a provider is explicitly configured and reviewed.
