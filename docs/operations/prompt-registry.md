# H14 — Versioned Prompt Registry and Provenance

## Status

An initial H14 implementation slice is available on the H14 review branch. It covers the GPI WorkOrder generator, AWI plan generator, and Agent Orchestrator protocol. It does not yet migrate every prompt-like string in the repository.

## Registry contract

The source-controlled registry provides exact-version resolution and immutable registration:

- A prompt is identified by a stable name and positive integer version.
- Each registration is validated and receives a SHA-256 digest of its exact source.
- Duplicate name/version pairs are rejected.
- The application default registry is frozen after composition; runtime requests cannot register or discover arbitrary prompt sources.
- Rendering requires exactly the declared string variables, rejects unknown/missing keys and oversized values, and enforces a per-template output budget.
- There is no silent fallback to another version. An unavailable version fails closed.

## Integrated templates

| Template | Consumer | Version |
| --- | --- | --- |
| `gpi.work_order` | `generate_work_order` | 1 |
| `awi.execution_plan` | `generate_execution_plan` | 1 |
| `agent.orchestrator` | `AgentOrchestrator` | 1 |

GPI and AWI accept an optional observer callback for rendered-template provenance. The Agent Orchestrator includes the active template metadata in its run result. The authenticated `GET /agent/prompts` route exposes a metadata-only registry manifest.

## Privacy and trust boundaries

The registry manifest and render metadata do not expose template source, rendered prompt text, variable values, or the digest of the rendered prompt. The template source digest identifies the reviewed template revision only. Prompt contents and variable values remain within the provider request path and are not copied into the audit metadata by this change.

Template contents are application-owned instructions; variables such as user goals and WorkOrders remain untrusted data. Prompt versioning does not grant tool permissions, bypass server-side policy, or make model output authoritative.

## Acceptance coverage

The added tests cover frozen/default registration, duplicate and invalid versions, missing/extra/oversized variables, deterministic rendering, template digest stability, GPI/AWI exact-version consumption, Agent Orchestrator provenance, and API metadata exposure without source disclosure.

## Remaining H14 scope

- Inventory and migrate remaining prompt templates in specialist delegation, multimodal/video analysis, research, content generation, and any provider-specific adapters where central versioning is beneficial.
- Add owner-scoped prompt evaluation datasets and release-to-release regression metrics.
- Add lifecycle/retention policy for prompt evaluation artifacts without storing user prompts or sensitive provider payloads.
- Validate prompt-version compatibility across queued work and persisted plan records during release acceptance.
- Verify all supported Python versions and full GitHub Actions checks on the exact PR head.
