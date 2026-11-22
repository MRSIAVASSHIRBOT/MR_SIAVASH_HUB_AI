# MR_SIAVASH_HUB_AI

> **Original project and author attribution: `MR_SIAVASH_IR_BOT`**  
> Copyright © 2026 MR_SIAVASH_IR_BOT. See [COPYRIGHT.md](COPYRIGHT.md) for attribution and license status. Preserve this attribution and do not misrepresent the original authorship when redistributing modified copies.


An integrated, modular AI workspace designed for local-first and hybrid execution.

## Product direction
MR_SIAVASH_HUB_AI combines a shared intelligence core with specialist capabilities for agents, memory, workflows, developer assistance, content production, integrations, and defensive security.

The initial release is designed for one primary user while keeping clean boundaries for future multi-user support.

**Ecosystem goal reference:** [Canonical goals, ownership, integration boundaries, and staged roadmap for all four MR_SIAVASH projects](docs/PROJECT_GOALS_ECOSYSTEM.md).

## Engineering principles
- **Local-first, hybrid-capable:** run feasible workloads locally and route heavier tasks to explicitly configured providers.
- **Modular monolith first:** maintain clear module contracts without introducing distributed-system overhead prematurely.
- **Secure by default:** least privilege, explicit tool grants, secret isolation, audit trails, and approval gates for sensitive actions.
- **Observable and recoverable:** jobs expose status, logs, cancellation, bounded retries, and recoverable checkpoints where appropriate.
- **Cost-aware:** prefer free and open-source components; external paid services remain opt-in.
- **Testable:** unit, integration, end-to-end, and security checks are part of the delivery process.

## Quick start
Requires Python 3.11 or newer.

On Windows, the recommended local launch path starts both the API and its separate pull-driven worker, creates a persistent local workflow-encryption key, and checks readiness:

```powershell
Set-ExecutionPolicy -Scope Process Bypass
.\scripts\start-local.ps1
```

Open the operator UI at `http://127.0.0.1:8000/ui/` or the API docs at `http://127.0.0.1:8000/docs`. Stop the processes with ` .\scripts\stop-local.ps1` (remove the leading space when copying). See [Windows local quick start](docs/operations/windows-quickstart.md) for requirements, security boundaries, and troubleshooting.

For manual development setup, create and activate a Python 3.11 virtual environment, run `python -m pip install -e ".[dev]"`, then start the API with `uvicorn mrhub.main:app --host 127.0.0.1 --port 8000`. Start the worker separately with `python -m mrhub.worker_service` when processing queued jobs. Durable agent workflows also require the same persistent `MRH_WORKFLOW_PAYLOAD_KEY` in both process environments; see the worker runbook.

OpenAPI documentation is available at `http://127.0.0.1:8000/docs`.

On first launch, initialize the local owner account from the same machine using `POST /auth/setup` with a unique password of at least 14 characters. Then call `POST /auth/login`; send the returned bearer token in the `Authorization` header for protected endpoints. Sessions expire after 12 hours by default and can be revoked with `POST /auth/logout`. Login attempts are throttled after five failed attempts per client address within five minutes; successful login clears that address's failure counter. Authentication responses are marked non-cacheable. This in-process throttle is suitable for the single-process local runtime; multi-worker deployments need a shared limiter and correctly configured trusted proxy handling. The setup endpoint is loopback-only and becomes permanently unavailable after the owner account is created.

`GET /health`, `POST /auth/setup`, and `POST /auth/login` are public (setup is restricted to loopback). Task, job, policy, and model endpoints require a valid session. `POST /tasks/{task_id}/approval` records a one-time owner-authenticated approval or rejection bound to a SHA-256 fingerprint of task identity, type, risk class, and description; the decision and task transition are persisted together. `GET /tasks/{task_id}/approval` retrieves the decision. Rejected tasks enter a terminal state. Initial protected endpoints also include `POST /tasks`, `GET /tasks`, `GET /tasks/{task_id}`, `POST /jobs/{task_id}/cancel`, `POST /policy/evaluate`, `GET /models`, and `POST /models/select`.

## Model provider interface

Provider adapters implement a typed contract for model metadata, request/response validation, health status, and generation. A registry resolves the selected provider/model pair; the router performs capability matching and refuses silent local-to-cloud fallback. Provider errors expose stable reason codes rather than request contents or credentials.

The deterministic `stub-text-v1` remains available for tests. A real local Ollama adapter is available but disabled by default. To opt in, install Ollama and a model separately, then set `MRH_LOCAL_INFERENCE_ENABLED=true`, `MRH_LOCAL_INFERENCE_MODEL=<installed-model-name>`, and optionally `MRH_LOCAL_INFERENCE_BASE_URL=http://127.0.0.1:11434`. The adapter accepts only plain HTTP loopback URLs, disables redirects and environment proxies, applies a finite timeout, bounds output tokens, and returns sanitized errors. The authenticated `POST /models/generate` endpoint is unavailable until local inference is explicitly enabled and a model is configured. A failed local request never falls back to cloud. No model is downloaded and no process is launched automatically. Moonshot Kimi K3.1 Pro remains a separate, disabled-by-default remote adapter with explicit invocation and no implicit fallback. Kimi currently exposes bounded single-turn text and one-image analysis endpoints; full 1M-token context, video input, multi-turn preserved reasoning, and tool execution remain unimplemented. See `docs/operations/kimi-k31-pro.md`.

Run tests:

```powershell
pytest
```

## Local hardware diagnostics

A read-only, standard-library host report is available for local model planning. From the repository root, run `python -m mrhub.diagnostics.hardware` in the configured project environment. See `docs/operations/hardware-diagnostics.md` for scope and limitations. The report is printed locally and is not uploaded.

## Initial capability domains
1. AI Core and Model Router
2. Agent Orchestrator
3. Memory and Retrieval
4. Workflow and Job Engine
5. Tool and Plugin Registry
6. NEXUS Developer Agent
7. Social Automation and Telegram Integration
8. Video Engine
9. Discovery and Research
10. Defensive Cybersecurity Lab
11. Developer Console

These are product domains, not separate competing backends. Shared infrastructure is implemented once and exposed through stable interfaces.

## Safety and trust boundaries
The platform is intended for legitimate personal productivity, software development, content creation, and defensive/authorized security work. It will not include credential theft, phishing kits, covert tracking, malware or payload generation, unauthorized access, or evasion features.

External publishing, spending, destructive operations, access to sensitive data, and other high-impact actions require explicit policy checks and, where configured, user approval.

## Current status
The repository now contains a modular FastAPI/SQLite control plane, owner authentication, policy and approval gates, structured audit events, a typed model registry, local memory and source-backed knowledge APIs, content drafts, and owner-scoped local media assets with bounded FFmpeg processing. The Job and Workflow Engine supports durable task state, idempotency, checkpoints, lease/fencing checks, interrupted-step recovery, safe resume, cancellation, and a separate pull-driven worker. Both initial workflow execution and resume execution are worker-owned; HTTP requests validate and enqueue rather than executing workflow steps.
