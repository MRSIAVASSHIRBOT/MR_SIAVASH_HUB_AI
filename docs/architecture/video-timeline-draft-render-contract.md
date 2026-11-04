# Video Timeline Draft → Render Contract

**Status:** Proposed implementation contract  
**Baseline:** `main` at `cbc12c0adf3994f28c49ca3ac4ff447ec029bade` (2026-11-04 UTC)  
**Scope:** Connect owner-scoped editable timeline drafts to durable MP4 render jobs without changing existing render semantics for callers that do not supply a draft.

## 1. Verified current boundary

The current implementation has three distinct representations:

1. `VideoTimelineDraftRepository` persists an owner-scoped, versioned draft containing duration, aspect ratio, and ordered `TimelineBeat` values. A beat contains timing, a generation instruction, transition text, and optional source timestamp/confidence.
2. `VideoTimeline` is the renderer input. It contains a contiguous `video_track` of `TimelineClip` values, each with source asset identity and source/timeline intervals. The renderer validates this structure before FFmpeg execution.
3. `VideoRenderJobRepository.submit(owner_user_id, analysis_id, idempotency_key)` currently loads the completed analysis timeline, computes its digest, and creates a durable task. `VideoRenderWorkerHandler` independently reloads that analysis timeline and renders it.

The draft beat schema does **not** contain the source asset identity and source in/out intervals required by `TimelineClip`. Consequently, a draft cannot safely be converted into a renderable `VideoTimeline` by merely replacing duration or aspect-ratio fields. A guessed mapping could render the wrong source segment or silently discard user edits.

## 2. Required design decision

Do not treat free-form `TimelineBeat` instructions as a renderer timeline.

Introduce a renderer-compatible, versioned draft representation that preserves the complete validated `VideoTimeline` structure. The editing contract may expose user-friendly beat controls, but the server-side canonical draft must retain:

- source asset ID for every clip;
- source start/end timestamps;
- timeline start/end timestamps;
- clip order and contiguous-track invariants;
- output aspect ratio and requested duration;
- schema version and optimistic draft version.

Existing beat-only drafts remain readable and editable through their existing API. They must not be silently promoted to renderable snapshots. A compatibility adapter may be introduced only when it can derive every source mapping unambiguously from the original analysis and validate the result against the canonical timeline schema.

## 3. Immutable render snapshot

Add a new append-only snapshot record associated with each render task. Recommended migration (next available schema version; verify migration sequence immediately before implementation):

```sql
CREATE TABLE video_render_timeline_snapshots (
    render_id TEXT PRIMARY KEY
        REFERENCES video_render_runs(render_id) ON DELETE CASCADE,
    owner_user_id TEXT NOT NULL
        REFERENCES auth_users(user_id) ON DELETE CASCADE,
    draft_id TEXT,
    draft_version INTEGER,
    timeline_schema_version TEXT NOT NULL,
    timeline_json TEXT NOT NULL CHECK (length(timeline_json) <= 60000),
    timeline_sha256 TEXT NOT NULL CHECK (length(timeline_sha256) = 64),
    created_at TEXT NOT NULL,
    CHECK (
      (draft_id IS NULL AND draft_version IS NULL)
      OR (draft_id IS NOT NULL AND draft_version IS NOT NULL AND draft_version > 0)
    )
);
```

The snapshot is immutable after task acceptance. The worker must never reload the mutable draft or the analysis timeline as a fallback for a render that has a snapshot. The snapshot row and task/render rows must be committed atomically.

The table intentionally retains a JSON snapshot instead of relying on a foreign key to the mutable draft version. This allows later draft edits and retention policies to coexist with the exact input used by an already accepted render.

## 4. API and repository contract

Add a draft-aware submission path while preserving the existing analysis-only route:

- Existing: `POST /analyses/{analysis_id}/renders` keeps its current behavior when no draft is supplied.
- Draft-aware: accept an explicit `draft_id` (prefer a dedicated route or a strict request model; do not overload an ambiguous optional field).
- Resolve the draft by both authenticated owner and draft ID. Return not-found for a draft owned by another user.
- Verify that the draft belongs to the supplied analysis and an asset included in that analysis.
- Read and validate the current draft version once, then construct the immutable renderer-compatible snapshot.
- Require the caller's expected draft version for submission. Reject stale versions with HTTP 409; do not silently render the latest version.
- Compute the idempotency digest from analysis ID, draft ID, draft version, canonical timeline schema version, and canonical serialized timeline hash.
- Reusing an idempotency key for a different draft version or timeline hash must return conflict. Replaying the same request returns the original render record.

Repository-level transaction must fence the draft version and create the render, task, idempotency record, and snapshot atomically. If the draft changes between read and commit, abort the transaction and report a version conflict.

## 5. Worker contract

Change worker loading to return the immutable snapshot reference/data in addition to owner, render ID, analysis ID, and reserved output key.

Before any source-media access:

1. Verify the task lease and fencing token using existing lease checks.
2. Load the snapshot using render ID **and** owner ID.
3. Verify the SHA-256 of the exact stored UTF-8 canonical JSON bytes.
4. Parse with the current strict `VideoTimeline` schema; reject unknown fields and invalid intervals.
5. Derive source IDs only from the validated snapshot.
6. Resolve every source asset through the authenticated owner's media repository and retain existing media-use lease protections.
7. Render the validated snapshot; do not substitute analysis results if snapshot loading, hashing, or validation fails.

Any failure must produce a bounded internal error code, leave no published output, and follow existing lease-fenced terminal transitions. Cancellation and lease-loss behavior must remain unchanged.

## 6. Security and integrity invariants

- Owner isolation applies to draft reads, snapshot creation, render status, and output retrieval.
- Draft IDs and asset IDs are untrusted references until checked against owner and analysis scope.
- Client-supplied timeline JSON is never passed directly to FFmpeg; it must pass the strict Pydantic timeline schema.
- No client-supplied file paths, FFmpeg arguments, filter strings, or storage keys are accepted.
- The worker uses only the reserved output storage key and owner-scoped source media.
- Snapshot hash is an integrity check, not an authenticity or authorization mechanism; database ownership and task lease checks remain mandatory.
- An accepted render is reproducible against its snapshot even after the draft is edited.
- Idempotency is based on the immutable render input, not merely the analysis ID.
- Existing cancellation, recovery, quarantine, and output-publication fences must remain in force.

## 7. Test matrix

### Schema and draft repository
- Valid renderer-compatible draft round-trips without loss of source IDs or timestamps.
- Reject unknown fields, non-finite numbers, negative intervals, gaps, overlaps, out-of-range duration, and unsupported aspect ratio.
- Owner A cannot read or submit Owner B's draft.
- Stale expected version fails without creating a task, render, idempotency record, or snapshot.
- Draft update after render acceptance does not mutate the stored snapshot.

### Render submission and idempotency
- Same key + same draft ID/version/hash returns the original render.
- Same key + changed draft version or hash returns conflict.
- Different keys create distinct render tasks with independently immutable snapshots.
- Transaction rollback leaves no partial task/render/snapshot/idempotency rows.
- Concurrent draft update versus submission is resolved by optimistic version fencing.

### Worker and recovery
- Worker renders the snapshot even when the live draft has subsequently changed.
- Worker never falls back to analysis timeline if snapshot is missing, corrupt, owner-mismatched, or schema-invalid.
- Hash mismatch fails closed before source media acquisition.
- Lease loss and cancellation prevent publication and release acquired media locks.
- Recovery handles interrupted renders without deleting unrelated output or snapshot records.
- Existing analysis-only render tests remain unchanged and pass.

### API and integration
- Draft-aware route returns accepted render metadata and exact draft version/hash reference.
- Stale version maps to 409; foreign/missing draft maps to 404.
- Status and download remain owner-scoped.
- Real FFmpeg integration renders the accepted snapshot on Linux and Windows.

## 8. Delivery sequence

1. Add renderer-compatible draft schema and validation tests without changing existing beat-only behavior.
2. Add the immutable snapshot migration and repository transaction tests.
3. Add draft-aware render submission and idempotency conflict tests.
4. Update worker snapshot loading, hash verification, and no-fallback behavior.
5. Extend API contract tests and operator UI to display draft version, render status, and output.
6. Add Linux/Windows FFmpeg integration coverage and recovery tests.
7. Update OpenAPI, operator documentation, dependency map, readiness audit, and changelog together.

Each step must be a separate reviewable commit or PR. Do not activate a UI control before the complete API/worker path is available.

## 9. Explicit non-goals

- No provider generation submission is triggered by timeline rendering.
- No automatic retry is introduced for ambiguous external provider outcomes.
- No change to FFmpeg execution policy or arbitrary filter support.
- No claim of full nonlinear video-editor functionality; this is a bounded, validated cut-only render pipeline.
- No production-readiness claim based solely on green CI.
