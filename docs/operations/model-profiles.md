# Model Profile Registry

This first registry is intentionally small and transparent. It contains two
illustrative planning profiles, not verified claims about specific model
releases. Both entries are marked `verified: false` and
`source_kind: operator_estimate`.

## Contract

Each profile has a stable ID, display name, minimum and recommended RAM
estimates, whether GPU resources are required, source classification,
verification flag, and notes. The registry is local static data: it makes no
network calls and downloads no model artifacts.

Authenticated API routes expose the catalog at `GET /models/profiles` and
one profile at `GET /models/profiles/{profile_id}`. The
`POST /models/compare` endpoint accepts a hardware report, up to 20 profile
IDs, and an optional system RAM reserve. It compares only registry entries,
rejects unknown IDs, de-duplicates repeated IDs, and returns each assessment
with its uncertainty labels. It never starts inference or downloads a model.

## Important limitation

Do not use these illustrative profiles to claim that a specific model will
run well on a device. Exact model architecture, quantization, context length,
runtime, CPU throughput, and GPU VRAM affect resource use. Replace the sample
estimates with values reviewed for the exact model/version before making a
real recommendation. The advisor must keep GPU-required entries in
`insufficient_data` while the required GPU data is unavailable.


## Advisory recommendation endpoint

`POST /models/recommend` ranks a bounded list of registered profile IDs (by
default, the two sample profiles) using the same resource assessment. The
response is explicitly `advisory_only`: it never selects a provider, starts
inference, or downloads a model. Unknown IDs are rejected. A profile is marked as a candidate only when it is explicitly
verified and its resource assessment is `likely_fit` or `likely_tight`.
Unverified profiles are returned as `unverified_estimate`, even when their RAM
estimate appears to fit; they never populate `best_candidate_profile_id`.
Profiles blocked by missing required measurements are labeled
`insufficient_data`. GPU-required profiles remain non-candidates until GPU
VRAM and compute data are measured. Because the current registry entries are
unverified examples, the default response intentionally has no best candidate.
This is a software-level demonstration, not a recommendation for a specific
real model.


## Provider inventory

The authenticated `GET /models/providers` endpoint lists adapters registered
in the current application configuration, including each model's declared
capabilities, local/remote classification, selection priority, and declared
availability. The inventory is deterministic and read-only. It does not call
provider health endpoints, start inference, download models, or expose provider
configuration such as base URLs and credentials. `health_status` is reported
as `not_checked`; it must not be interpreted as live availability. Live
provider health monitoring is a separate operation with explicit timeouts and
failure handling.


## Provider health monitoring

The authenticated `POST /models/providers/health-check` endpoint performs an
explicit health probe against each registered adapter. Its request accepts a
per-provider timeout from 0.1 to 5 seconds (default 2 seconds). Results include
a stable status/reason code and measured duration; provider exception details
are not returned. A health probe does not run model inference or download
artifacts. This endpoint can contact the explicitly configured loopback Ollama
service, so it should be called only when an operator intends to check that
local service. The passive `GET /models/providers` inventory never performs
these probes.
