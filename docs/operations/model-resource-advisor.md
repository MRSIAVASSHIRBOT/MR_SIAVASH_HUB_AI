# Model Resource Advisor

The advisor provides a conservative, deterministic RAM-fit estimate for a
caller-supplied model profile. It is deliberately separate from model routing
and inference: it never downloads models, contacts a model registry, starts
Ollama, or generates text.

## Inputs

- A hardware report from `mrhub.diagnostics.hardware.collect_hardware_report()`.
- A model profile with `name`, `minimum_ram_gib`, `recommended_ram_gib`,
  and `requires_gpu`.
- An optional system RAM reserve, defaulting to 2 GiB.

The minimum and recommended RAM values must be supplied from a trusted,
model-specific source or an operator estimate. The advisor does not invent
model requirements or certify their accuracy.

## Results

- `likely_fit`: available RAM minus the safety reserve meets the recommended
  profile estimate.
- `likely_tight`: it meets only the minimum estimate.
- `not_recommended`: it is below the minimum estimate.
- `insufficient_data`: available RAM is missing, or the profile requires GPU
  data that the current diagnostic does not measure.
- `invalid_profile`: required profile fields are absent or invalid.

Every result includes `starts_inference: false`. The advisor does not predict
tokens per second or guarantee compatibility. Context length, quantization,
runtime overhead, CPU throughput, thermal limits, and concurrent applications
can materially change real-world behavior.

## Safety boundary

This is a planning function only. It does not select a provider, authorize a
task, start a model, change system configuration, or make network requests.
