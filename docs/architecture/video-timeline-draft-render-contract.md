# Video Timeline Draft → Render Contract

**Status:** Core snapshot persistence and Worker integration merged via PR #273. A post-merge current-draft race fence is proposed in PR #276 and is not yet merged.  
**Main baseline:** `8f190eeac4b4627692b60ac27e6dd5c12e4557bc` (2026-11-04 UTC)  
**Scope:** Bind a saved, renderer-compatible timeline revision to a durable MP4 render job without changing analysis-only render semantics.

## 1. Three distinct timeline representations

1. `VideoTimelineDraftRepository` stores owner-scoped, versioned storyboard drafts. A draft contains bounded `TimelineBeat` instructions and, when saved for rendering, an optional renderer-compatible `VideoTimeline` plus its canonical SHA-256.
2. `VideoTimeline` is the renderer input: a validated contiguous `video_track` of `TimelineClip` records with source asset IDs and source/timeline intervals.
3. `VideoRenderTimelineSnapshot` is an immutable value object that binds canonical `VideoTimeline` JSON to owner, analysis, draft ID and exact draft version. It validates canonical JSON and content hash.

A beat-only storyboard is not a renderer edit-decision list. Its natural-language instructions and transitions must never be passed directly to FFmpeg. The renderer-compatible timeline retains the source identities and intervals required to render the intended media.

## 2. Persisted draft and snapshot contract

Migration 28 adds `renderer_timeline_json` and `renderer_timeline_sha256` to `video_timeline_drafts`, with a paired-value constraint enforced for both INSERT and UPDATE. It creates `video_render_timeline_snapshots` with:

- a unique snapshot ID and unique `(draft_id, draft_version)`;
- owner, analysis, draft and exact draft-version identity;
- snapshot schema version, canonical timeline JSON, SHA-256 and creation timestamp;
- `RESTRICT` foreign keys to the owner-scoped analysis and draft so parent deletion cannot silently invalidate an accepted render;
- an UPDATE trigger that rejects mutation of a persisted snapshot.

Migration 29 adds nullable `snapshot_id` to `video_render_runs` with a restrictive foreign key and lookup index. Nullable linkage preserves the existing analysis-only render path.

The snapshot repository verifies that the draft still belongs to the authenticated owner, references the same analysis and source asset, has the exact expected database version, and contains the same canonical timeline/hash. It rechecks source asset membership and measured per-asset media duration before persistence. Missing or invalid duration metadata fails closed.

## 3. Atomic render submission

The draft-aware endpoint is:

`POST /video-intelligence/timeline-drafts/{draft_id}/renders`

It requires an authenticated owner and an `Idempotency-Key` header. The API reads the owner's draft and completed analysis, validates the saved renderer timeline, and creates a snapshot value object. It does not accept arbitrary timeline JSON, filesystem paths, FFmpeg arguments, filter strings or remote URLs.

The render repository then uses one `BEGIN IMMEDIATE` transaction to:

1. revalidate the exact owner-scoped draft revision and its canonical renderer timeline;
2. insert or resolve the immutable snapshot for that draft revision;
3. create the durable task and render row bound to that snapshot;
4. create the idempotency record.

A stale draft, snapshot conflict, or idempotency conflict aborts the transaction; no partial snapshot/task/render/idempotency state is committed. A replay with the same immutable input resolves to the original snapshot and render record. The response includes the exact draft ID/version and snapshot ID. An already accepted request may be replayed with its original idempotency key after the editable draft advances; that is a replay of the same accepted operation, not a new render. A new render submission must prove that the snapshot still matches the current owner-scoped draft revision inside the transaction, even if a snapshot row for that old revision already exists. PR #276 adds this additional fence and its stale-snapshot regression test; until merged, this edge-case correction is not part of main.

The endpoint renders the currently persisted draft revision observed by the server and fenced in the transaction. It does not currently accept a caller-supplied historical draft version. The legacy `POST /video-intelligence/analyses/{analysis_id}/renders` route remains available and retains analysis-timeline behavior.

## 4. Worker contract

For a snapshot-backed task, the Worker:

1. verifies its task lease and fencing token;
2. loads the snapshot using both owner ID and snapshot ID;
3. validates canonical JSON, snapshot identity and SHA-256 through the strict snapshot model;
4. validates the timeline and source asset membership against the completed owner-scoped analysis;
5. checks each source interval against measured media duration;
6. resolves source assets through the authenticated owner's media repository and acquires task/fencing-token-bound media-use leases;
7. renders only the validated snapshot timeline.

A missing, corrupt, owner-mismatched or invalid snapshot fails closed. The Worker never falls back to the mutable draft or analysis timeline for a snapshot-backed job. Existing analysis-only jobs continue to use the validated analysis timeline. Cancellation, lease loss, output cleanup, FFprobe verification and atomic output registration retain their existing fences.

## 5. Security and integrity invariants

- Draft and snapshot reads are owner-scoped; IDs are untrusted until owner and analysis membership are checked.
- Source assets must belong to the completed analysis and have valid measured duration metadata.
- Client-controlled timeline data is validated by the strict Pydantic timeline schema before it can reach the renderer.
- No client-supplied paths, storage keys, FFmpeg command fragments or remote URLs are accepted.
- SHA-256 detects content mismatch; it is not an authorization mechanism and does not replace owner checks or worker lease fencing.
- A render remains bound to its immutable snapshot even if the mutable draft is subsequently edited.
- Idempotency is bound to the exact draft revision and canonical renderer timeline, not only the analysis ID.
- Snapshot retention uses restrictive parent references; cleanup must be explicit and must not remove a snapshot referenced by a render.
- Existing cancellation, recovery, quarantine, media-use locking and output-publication fences remain mandatory.

## 6. Automated test coverage on the PR branch

- Snapshot canonicalization, SHA-256 validation, owner/analysis/draft identity and revision-sensitive idempotency.
- Draft revision fencing and rejection of changed/stale revisions.
- Source asset membership and measured source-duration bounds, including revalidation at persistence.
- Immutable snapshot update rejection and parent-deletion restriction.
- Renderer timeline/hash pair enforcement on INSERT and UPDATE.
- Snapshot-backed Worker execution using the frozen source interval rather than the analysis timeline.
- Atomic snapshot + render submission and rollback when the idempotency key conflicts.
- Existing analysis-only render behavior and Linux/Windows real FFmpeg integration remain part of the broader CI gate.

Exact-head CI must pass before merge. No local test execution or target-device acceptance is claimed.

## 7. Remaining acceptance work

- Route-level tests now cover authenticated snapshot handoff, owner-scoped missing/foreign drafts, rejection when no renderer timeline is saved, and malformed saved timeline input. Keep the tests aligned with any future API response or status changes.
- Add a dashboard action for submitting a render from the selected saved renderer timeline; do not expose a control before the complete API/Worker path is available.
- Verify the user-facing workflow on the target Windows device with representative media, cancellation, stale draft edits and output download.
- Keep the renderer explicitly silent and cut-only. Audio, captions, graphics, motion effects, transitions beyond hard cuts and AI-generated footage require separate validated contracts and are not implemented here.
- Reconcile this document, the project status ledger, dependency map and whole-project audit whenever the main baseline changes.

## 8. Explicit non-goals

- No video-generation provider submission is triggered by timeline rendering.
- No automatic retry is introduced for ambiguous external provider outcomes.
- No arbitrary FFmpeg filters or user-supplied commands are accepted.
- No claim of a full nonlinear video editor or production readiness is made.


## 9. Post-merge stale-revision correction

PR #273 merged the immutable snapshot render path. A follow-up review identified that the repository's existing-snapshot branch could return a previously created snapshot before checking whether the editable draft had advanced. The new-render path must reject this stale snapshot even when the immutable row already exists. PR #276 moves the current-draft check ahead of existing-snapshot reuse for transactional render submission, while preserving repository-level historical snapshot replay and already accepted idempotency replays. This follow-up remains unmerged until exact-head CI and review pass.
