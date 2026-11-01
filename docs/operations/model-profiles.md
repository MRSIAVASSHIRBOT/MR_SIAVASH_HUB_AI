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
