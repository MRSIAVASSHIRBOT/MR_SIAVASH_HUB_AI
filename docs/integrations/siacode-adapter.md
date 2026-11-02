# SiaCode integration proposal for MR_SIAVASH_HUB_AI

**Status:** proposed integration design; not yet a runtime adapter.  
**Source reviewed:** [Siavashc/SiaCode](https://github.com/Siavashc/SiaCode) README on 2026-11-02.  
**Owner project:** MR_SIAVASH_HUB_AI.

## Decision

Treat SiaCode as an **optional, externally managed coding-execution backend**, not as a dependency of the core platform and not as a replacement for the existing provider registry, workflow engine, NEXUS, or policy layer.

The useful idea to adapt is its launch-time health gate and recovery-oriented orchestration. Do not copy the external repository wholesale or let its scripts bypass the hub's authorization and audit contracts.

## What the upstream README claims

The README describes a Windows/PowerShell launcher that connects Claude Code through a local Anthropic-compatible proxy and an ngrok tunnel to a remote molab notebook running a large MiniMax-M2.7 GGUF model. It describes a free GPU path, a roughly 108 GB model download, and recovery after an ephemeral sandbox is stopped.

These are **upstream claims, not independently verified guarantees**. Availability, quotas, service terms, model weights, throughput, region access, and session lifetime can change. The model is large and the notebook lifecycle is external; this is not equivalent to free, always-on, local inference.

## Proposed architecture

```text
NEXUS / Agent request
        |
        v
Task + Workflow Engine
        |
        v
Policy evaluation -> explicit approval when required
        |
        v
Coding-backend adapter interface
        |
        +--> existing local / configured model providers
        |
        +--> optional SiaCode bridge (disabled by default)
                  |
                  +-- health/readiness probe
                  +-- bounded request/response contract
                  +-- cancellation and timeout reporting
                  +-- sanitized diagnostics
```

The SiaCode bridge must not own scheduling, persistence, credentials, task policy, or approval decisions. Those remain in MR_SIAVASH_HUB_AI.

## Integration stages

### Stage 1 — documentation and capability contract

- Record SiaCode as an optional integration candidate.
- Define a provider/adapter contract without importing upstream scripts.
- Require explicit configuration and a readiness check before a task can select the adapter.
- Report distinct states: unconfigured, unavailable, ready, busy, and failed.
- Preserve provider identity and failure reason in task/job metadata without recording prompts, tokens, or credentials.

### Stage 2 — read-only preflight adapter

Implement a small adapter that checks configuration and the documented local endpoint's health. It must not create a molab notebook, launch a shell, install software, start a tunnel, or download model weights automatically.

Acceptance tests:
- disabled by default;
- missing configuration fails closed;
- unreachable endpoint returns a stable sanitized error;
- redirects are disabled;
- request timeout and response size are bounded;
- no secrets appear in logs or API errors;
- no implicit switch to another provider after failure.

### Stage 3 — explicitly enabled coding requests

Only after Stage 2 tests pass, add bounded coding-request submission behind the shared task policy. Use an isolated workspace and require review of proposed diffs before applying them. Do not grant arbitrary shell execution or automatic repository writes merely because the upstream tool can execute tools.

Acceptance tests:
- policy is checked before dispatch;
- request size, output size, duration, and concurrency are bounded;
- cancellation and timeout become observable job states;
- output is treated as untrusted data;
- external-side-effect steps are never blindly replayed after an ambiguous result;
- audit events identify the adapter and outcome without secrets or raw sensitive inputs.

### Stage 4 — optional operator workflow

Expose enablement and health state in the operator console only after the adapter is tested. Any account linking, tunnel creation, model download, external publishing, or paid/credit-consuming action remains a separately disclosed, explicit operator action.

## Security and reliability requirements

1. **Disabled by default:** no external tunnel or remote execution starts automatically.
2. **Secret isolation:** notebook credentials, ngrok tokens, and provider credentials belong in a secret store or protected environment; never commit them or return them to the UI.
3. **Tunnel trust boundary:** an ngrok URL is a network exposure point, not proof of identity. Require authenticated transport and a narrowly scoped endpoint; do not expose an unauthenticated arbitrary-code endpoint.
4. **No implicit fallback:** a failed SiaCode call must not silently route to another model or provider.
5. **Least privilege:** the adapter can submit only the task types and workspace scope granted by policy.
6. **Resource awareness:** a remote 108 GB model download and a time-limited notebook are unsuitable as assumptions for routine, dependable jobs.
7. **Recovery is bounded:** health checks may report or request a safe retry, but must not spawn unlimited rebuild loops or replay non-idempotent operations.
8. **Provenance:** label results as generated by the configured remote backend and retain minimal traceable execution metadata.
9. **Upstream separation:** use the upstream project under its stated license only after reviewing the actual files and dependencies. This proposal does not vendor or execute upstream code.

## Current limitations

- No SiaCode process has been launched from MR_SIAVASH_HUB_AI.
- No external account, tunnel, notebook, GPU, or model endpoint has been configured or tested.
- No runtime adapter or new dependency is included by this document.
- The upstream README's free-service and performance claims remain unverified.
- This document does not assert that integration is complete.

## References

- [SiaCode repository](https://github.com/Siavashc/SiaCode)
- [MR_SIAVASH_HUB_AI module boundaries](../architecture/module-boundaries.md)
- [MR_SIAVASH_HUB_AI implementation roadmap](../roadmap/implementation-plan.md)
