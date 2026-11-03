# Open-source integration catalog

MR_SIAVASH_HUB_AI is independent from the owner's previous repositories. Third-party projects are evaluated behind Hub-owned interfaces.

## Candidates

- Headroom: https://github.com/headroomlabs-ai/headroom — Apache-2.0; reviewed release v0.42.0 (2026-10-26); Python >=3.10; deferred from the core runtime after dependency and compatibility review (see decision below).
- PixelRAG: https://github.com/StarTrail-org/PixelRAG — Apache-2.0; Python >=3.12; visual retrieval with substantial optional ML dependencies; keep separate from the Python >=3.11 core.
- Cloudflare Security Audit Skill: https://github.com/cloudflare/security-audit-skill — MIT; agent skill rather than a Python library; selected principles are documented below; no upstream scripts or automatic command execution are adopted.
- MCP Python SDK: https://github.com/modelcontextprotocol/python-sdk — MIT; Python >=3.11; selected for an optional, loopback-only server bridge over the existing Hub ToolRegistry. Reviewed SDK pin: `mcp==2.3.0`.
- E2B: https://github.com/e2b-dev/e2b — open-source sandbox platform; Python SDK supports Python >=3.11; deferred pending licensing-metadata reconciliation, deployment-cost review, and isolation acceptance (see decision below).
- Z.ai GLM: https://docs.z.ai/ — hosted model API; compatible with the existing OpenRouter adapter through OpenRouter model IDs; no separate SDK or direct-provider dependency adopted (see decision below).

## Implemented integration

- MCP Tool Bridge: optional `mcp==2.3.0` extra; separate `mrhub-mcp` process; Streamable HTTP on loopback only; disabled by default. Exposes `hub.list_tools` and `hub.invoke_tool` through the canonical ToolRegistry. The Hub PolicyEngine remains authoritative; the bridge supplies no grants or approval state. See `docs/integrations/mcp-tool-bridge.md`. This is an interoperability bridge for Hub-owned tools, not an MCP client or arbitrary third-party server runtime.

## GLM evaluation — reuse OpenRouter, no new SDK

Z.ai's official API documentation publishes an OpenAI-compatible Chat Completions endpoint at `https://api.z.ai/api/paas/v4`, and documents both its own Python SDK and the OpenAI Python SDK. OpenRouter currently lists Z.ai models, including `z-ai/glm-5.3-flash` and `z-ai/glm-5.3`.

The Hub already has an explicit `OpenRouterProvider` that accepts a configured model identifier and uses the existing `MRH_REMOTE_INFERENCE_API_KEY`, `MRH_REMOTE_INFERENCE_MODEL`, and `MRH_REMOTE_INFERENCE_BASE_URL` settings. Therefore GLM can be selected through the existing OpenRouter route without adding another provider, SDK, credential type, or runtime dependency. Keep `MRH_REMOTE_INFERENCE_ENABLED=false` unless the owner explicitly enables remote inference.

Important capability boundary: the current Hub OpenRouter adapter sends a bounded, non-streaming text chat request and declares text capability only. It does not yet expose GLM-specific reasoning controls, streaming, vision, or function/tool calling. The model's advertised upstream capabilities must not be represented as Hub capabilities until the adapter and its tests implement them.

Decision: do not add `zai-sdk` or a direct Z.ai adapter at this stage. Prefer the already-reviewed OpenRouter path if the owner chooses a GLM model. Before any live request, verify the current model ID, price/quota, provider routing, and data-handling terms; model availability and prices can change, and no free usage is assumed. No live GLM request or billing validation was performed as part of this review.

References:
- Z.ai API introduction: https://docs.z.ai/api-reference/introduction
- Z.ai OpenAI Python SDK compatibility: https://docs.z.ai/guides/develop/openai/python
- OpenRouter Z.ai model catalog: https://openrouter.ai/provider/z-ai

## E2B sandbox evaluation — deferred

Reviewed the E2B repository and its Python SDK metadata on 2026-11-03. The project documents an isolated sandbox service and a self-hosting/Embed path; the Python SDK declares Python >=3.11, which matches the Hub's minimum Python version. The SDK has a non-trivial dependency set, including HTTP/2, protobuf, Connect RPC, and additional runtime packages. The hosted quick-start requires an E2B API key; self-hosting still requires separately operated infrastructure and does not make sandbox execution a zero-cost or Windows-native capability.

A licensing metadata discrepancy also needs upstream clarification before adoption: the Python SDK's current `pyproject.toml` declares `MIT`, while the repository root `LICENSE` file is Apache-2.0 and the public project materials describe the stack as Apache-2.0. Do not infer the package's distribution license from one file while this discrepancy remains unresolved.

Decision: do not add E2B to the Hub core or enable hosted execution. Reconsider only after the exact package license is confirmed, total hosted/self-hosted costs are understood, and a Hub-owned sandbox contract is designed and tested. Required controls include an OS-enforced isolation boundary, bounded CPU/memory/disk/time, explicit network egress policy, ephemeral per-run storage, no inherited host credentials, sanitized outputs, lifecycle cleanup, and owner approval for any external side effects. A container by itself is not accepted as a sufficient security boundary. Windows support must be validated on a real Windows host rather than inferred from Linux CI.

References:
- E2B repository: https://github.com/e2b-dev/e2b
- E2B Python SDK metadata: https://github.com/e2b-dev/e2b/tree/main/packages/python-sdk
- E2B self-hosting and deployment overview: https://e2b.dev/open-source

## Headroom evaluation — deferred

Reviewed upstream `headroom-ai==0.42.0` at tag `v0.42.0` and its published `pyproject.toml`. The project is Apache-2.0 and supports Python >=3.10, but its base dependency set is not a small compression-only addition: it includes `tiktoken`, `litellm`, `ast-grep-cli`, `click`, `rich`, OpenTelemetry, and additional configuration/runtime packages. It is built with Maturin and includes native components. The optional proxy extra adds an ASGI/network stack, and the MCP extra constrains `mcp>=1.30.0,<2.0.0`, which conflicts with this repository's reviewed `mcp==2.3.0` pin if both extras are installed in the same environment.

Decision: do not add Headroom to the Hub core or its current Python environment. The dependency footprint overlaps existing provider-routing and context infrastructure, introduces native-package and supply-chain review obligations, and its proxy/MCP extras are not compatible with the current MCP SDK pin. Reconsider only as an isolated optional worker or a narrowly scoped compression library after a reproducible benchmark on representative Hub prompts/tool outputs, output-equivalence checks, latency measurements, dependency audit, and a documented rollback path. Upstream-reported savings are not treated as Hub benchmark results.

## Cloudflare audit methodology — adapted, not embedded

Upstream: https://github.com/cloudflare/security-audit-skill

The upstream skill describes a six-stage, source-first audit process with separate discovery and verification roles, structured findings, and severity based on demonstrated impact. The Hub adopts only these review principles; it does not install the skill, copy its scripts, delegate untrusted code execution, or claim to have completed a full audit.

For future integration reviews and focused security reviews:

1. **Map the boundary:** identify the untrusted input, trusted decision point, affected principal/resource, and the control intended to protect it.
2. **Trace the source path:** follow the input through validation, authorization, data access, external calls, and output handling. Treat model output, fetched pages, uploaded files, and plugin responses as data, never as permission.
3. **Record candidates, not assumptions:** each candidate must name a concrete boundary and plausible observable consequence. Missing deployment facts are recorded as 'needs_validation', not promoted to confirmed vulnerabilities.
4. **Try to disprove:** a reviewer who did not propose the candidate checks the relevant source and tests for existing controls, unreachable paths, and incorrect impact assumptions. Where independent review tooling is unavailable, explicitly record that limitation.
5. **Validate safely:** prefer static inspection and existing unit tests. Run target-controlled code only in an OS-enforced sandbox with no external network, explicit environment allowlist, read-only source, bounded resources, and isolated scratch storage. If these controls are unavailable, do not execute the target; record the exact validation gap.
6. **Report evidence and minimal fixes:** distinguish confirmed behavior, rejected candidates, and facts needing validation. Severity must not exceed demonstrated impact. Recommend the smallest source-level fix and a regression test.

This is a review checklist, not an automated vulnerability scanner or a claim that every audit has completed all six stages. A complete repository audit requires a separately scoped request, an isolated execution environment, independent verification, and a report tied to an exact source revision.

## Not approved yet

- PixelRAG: keep separate until Python-version compatibility and the ML dependency footprint are resolved.
- E2B: deferred until license metadata, deployment cost, isolation controls, and real-host acceptance are resolved.
- Direct Z.ai integration: not needed while the existing OpenRouter adapter is sufficient for bounded text chat; reconsider only if direct routing or GLM-specific capabilities are required.
- Text RAG: evaluate separately; PixelRAG is visually oriented.

## Adoption gate

For every upstream, record the canonical URL and revision, license obligations, runtime compatibility, dependencies, data/network/filesystem behavior, Hub interface, tests, feature flag, and rollback plan. Discovery is not approval. Do not install or execute discovered projects automatically. Optional integrations must not silently enable paid services or send private data to third parties.

## Order

1. Complete a real MCP host acceptance test before enabling the bridge in a deployment.
2. Keep GLM available only through the existing explicitly enabled OpenRouter adapter until a measured need justifies a direct provider.
3. Keep E2B deferred until the sandbox threat model, licensing, costs, and real-host acceptance are complete.
4. Keep Headroom deferred unless an isolated benchmark demonstrates material benefit without destabilizing the existing provider/context stack.
5. Apply the Cloudflare-derived review checklist to future integrations and security-sensitive changes.

Headroom, PixelRAG, Cloudflare's audit skill, E2B, and direct Z.ai integration remain candidates or methodology references; MCP is the first implemented optional runtime bridge, subject to host acceptance. GLM can use the existing OpenRouter path without a new integration.

## Local candidate catalog

The first capability-catalog slice is available through the authenticated API:

- `POST /capabilities/candidates` registers a canonical HTTPS source URL and declared capabilities.
- `GET /capabilities/candidates` lists candidates; filter with `?status=discovered`, `reviewing`, `approved`, `rejected`, or `disabled`.
- `GET /capabilities/candidates/{candidate_id}` retrieves one candidate.
- `POST /capabilities/candidates/{candidate_id}/transition` advances review status.

Registration is metadata-only: it does not fetch, install, import, or execute upstream code. Duplicate canonical URLs are rejected. Approval is blocked unless a known license identifier, public HTTPS license URL, security review, compatibility notes, and a test plan are recorded. This catalog is a first building block, not yet an automated GitHub scanner, package installer, plugin runtime, or self-modifying code system.
