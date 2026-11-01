# MR_SIAVASH_HUB_AI

An integrated, modular AI workspace designed for local-first and hybrid execution.

## Product direction
MR_SIAVASH_HUB_AI combines a shared intelligence core with specialist capabilities for agents, memory, workflows, developer assistance, content production, integrations, and defensive security.

The initial release is designed for one primary user while keeping clean boundaries for future multi-user support.

## Engineering principles
- **Local-first, hybrid-capable:** run feasible workloads locally and route heavier tasks to explicitly configured providers.
- **Modular monolith first:** maintain clear module contracts without introducing distributed-system overhead prematurely.
- **Secure by default:** least privilege, explicit tool grants, secret isolation, audit trails, and approval gates for sensitive actions.
- **Observable and recoverable:** jobs expose status, logs, cancellation, bounded retries, and recoverable checkpoints where appropriate.
- **Cost-aware:** prefer free and open-source components; external paid services remain opt-in.
- **Testable:** unit, integration, end-to-end, and security checks are part of the delivery process.

## Quick start
Requires Python 3.11 or newer.

```powershell
py -3.11 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -e ".[dev]"
uvicorn mrhub.main:app --reload
```

OpenAPI documentation is available at `http://127.0.0.1:8000/docs`.

On first launch, initialize the local owner account from the same machine using `POST /auth/setup` with a unique password of at least 14 characters. Then call `POST /auth/login`; send the returned bearer token in the `Authorization` header for protected endpoints. Sessions expire after 12 hours by default and can be revoked with `POST /auth/logout`. Login attempts are throttled after five failed attempts per client address within five minutes; successful login clears that address's failure counter. Authentication responses are marked non-cacheable. This in-process throttle is suitable for the single-process local runtime; multi-worker deployments need a shared limiter and correctly configured trusted proxy handling. The setup endpoint is loopback-only and becomes permanently unavailable after the owner account is created.

`GET /health`, `POST /auth/setup`, and `POST /auth/login` are public (setup is restricted to loopback). Task, job, policy, and model endpoints require a valid session. `POST /tasks/{task_id}/approval` records a one-time owner-authenticated approval or rejection bound to a SHA-256 fingerprint of task identity, type, risk class, and description; the decision and task transition are persisted together. `GET /tasks/{task_id}/approval` retrieves the decision. Rejected tasks enter a terminal state. Initial protected endpoints also include `POST /tasks`, `GET /tasks`, `GET /tasks/{task_id}`, `POST /jobs/{task_id}/cancel`, `POST /policy/evaluate`, `GET /models`, and `POST /models/select`.

## Model provider interface

Provider adapters implement a typed contract for model metadata, request/response validation, health status, and generation. A registry resolves the selected provider/model pair; the router performs capability matching and refuses silent local-to-cloud fallback. Provider errors expose stable reason codes rather than request contents or credentials.

The deterministic `stub-text-v1` remains available for tests. A real local Ollama adapter is now available but disabled by default. To opt in, install Ollama and a model separately, then set `MRH_LOCAL_INFERENCE_ENABLED=true`, `MRH_LOCAL_INFERENCE_MODEL=<installed-model-name>`, and optionally `MRH_LOCAL_INFERENCE_BASE_URL=http://127.0.0.1:11434`. The adapter accepts only plain HTTP loopback URLs, disables redirects and environment proxies, applies a finite timeout, bounds output tokens, and returns sanitized errors. The authenticated `POST /models/generate` endpoint is unavailable until local inference is explicitly enabled and a model is configured. A failed local request never falls back to cloud. No model is downloaded and no process is launched automatically. Remote providers remain a separate opt-in milestone.

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
The repository contains the architecture baseline and initial control-plane slice: versioned SQLite schema migrations, task records, policy evaluation, job state transitions/cancellation, capability-aware model selection, structured audit events, local owner authentication, action-bound approvals, and a pull-driven worker with fail-closed dispatch and bounded retry for deterministic demo tasks. The provider layer has typed contracts, an explicit registry, capability-aware dispatch, a deterministic stub, and an opt-in Ollama adapter restricted to loopback HTTP. Local inference is disabled by default; remote provider calls, shell, arbitrary code execution, and external publishing are not enabled. Worker execution remains explicitly pull-driven and intended for a single local worker process; distributed leases and forced interruption of synchronous handlers are not implemented.


## Durable agent workflow execution

Workflow submission is asynchronous. POST /agent/workflows validates the request, stores only a digest plus a separately encrypted execution envelope, and returns the queued workflow/job identifiers. The worker decrypts the envelope only when the canonical worker lease is held; authentication failure, an absent key, or a mismatched owner/resource binding fails closed.

1. Install the project and dependencies: `python -m pip install -e .`
2. Configure `MRH_DATABASE_PATH` and `MRH_WORKFLOW_PAYLOAD_KEY`. Generate a fresh key for each deployment with:
   `python -c "import secrets,base64; print(base64.urlsafe_b64encode(secrets.token_bytes(32)).decode())"`
3. Store the key in the deployment secret manager or protected environment configuration. Do not commit it, reuse the test key, or rotate it without a migration plan for queued payloads.
4. Start the API process as usual, then start a worker in a separate process from the repository root:
   `python -m mrhub.worker_service`
5. Poll GET /agent/workflows/{workflow_id} for durable state. The API does not silently start a worker; the separate process is an explicit operational choice.

The encrypted envelope is bound with authenticated associated data to the workflow ID, task ID, and owner ID. Raw request/tool inputs are not written to workflow history or logs. External-side-effect steps must not be blindly replayed after an ambiguous outcome.


## Documentation
- `docs/architecture/overview.md` — system architecture
- `docs/architecture/module-boundaries.md` — module ownership and contracts
- `docs/security/threat-model.md` — trust boundaries and security controls
- `docs/roadmap/implementation-plan.md` — staged delivery plan

## License
License selection is pending. No license grant should be inferred until a license file is added.


## Model resource planning

A conservative RAM-fit estimator is available in `mrhub.diagnostics.resource_advisor`. It consumes the read-only hardware report and an explicit model profile, reserves system memory, reports uncertainty, and never starts inference. See `docs/operations/model-resource-advisor.md`.


A static, local model-profile registry is available through the authenticated `GET /models/profiles` endpoint. Its sample entries are explicitly unverified estimates, not model compatibility guarantees. See `docs/operations/model-profiles.md`.

The initial owner-scoped memory API supports explicit private notes, SQLite FTS5 lexical search, update/delete, expiry, and owner-only JSON export. It is not automatically injected into agent context. See `docs/operations/memory.md`.
