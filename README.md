# MR_SIAVASH_HUB_AI

> **Original project and author attribution: `MR_SIAVASH_IR_BOT`**  
> Copyright © 2026 MR_SIAVASH_IR_BOT. See [COPYRIGHT.md](COPYRIGHT.md) for attribution and license status. Preserve this attribution and do not misrepresent the original authorship when redistributing modified copies.


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

The deterministic `stub-text-v1` remains available for tests. A real local Ollama adapter is now available but disabled by default. To opt in, install Ollama and a model separately, then set `MRH_LOCAL_INFERENCE_ENABLED=true`, `MRH_LOCAL_INFERENCE_MODEL=<installed-model-name>`, and optionally `MRH_LOCAL_INFERENCE_BASE_URL=http://127.0.0.1:11434`. The adapter accepts only plain HTTP loopback URLs, disables redirects and environment proxies, applies a finite timeout, bounds output tokens, and returns sanitized errors. The authenticated `POST /models/generate` endpoint is unavailable until local inference is explicitly enabled and a model is configured. A failed local request never falls back to cloud. No model is downloaded and no process is launched automatically. The optional OpenRouter adapter is a separate, disabled-by-default text-only path; additional remote providers and tool-calling remain future work.

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

The deterministic stub is available for tests. Ollama local inference and the OpenRouter text adapter are separate opt-in providers and remain disabled by default; neither silently falls back to another provider. The worker is started explicitly as a separate process. This is not yet a claim of production-grade distributed-worker high availability or forced interruption of synchronous handlers. Arbitrary shell execution, arbitrary code execution, and external social publishing remain disabled.


## Durable agent workflow execution

Workflow submission is asynchronous. POST /agent/workflows validates the request, stores only a digest plus a separately encrypted execution envelope, and returns the queued workflow/job identifiers. The worker decrypts the envelope only when the canonical worker lease is held; authentication failure, an absent key, or a mismatched owner/resource binding fails closed.

1. Install the project and dependencies: `python -m pip install -e .`
2. Configure `MRH_DATABASE_PATH` and `MRH_WORKFLOW_PAYLOAD_KEY`. Generate a fresh key for each deployment with:
   `python -c "import secrets,base64; print(base64.urlsafe_b64encode(secrets.token_bytes(32)).decode())"`
3. Store the key in the deployment secret manager or protected environment configuration. Do not commit it, reuse the test key, or rotate it without a migration plan for queued payloads.
4. Start the API process as usual, then start a worker in a separate process from the repository root:
   `python -m mrhub.worker_service`
5. Poll GET /agent/workflows/{workflow_id} for durable state. The API does not silently start a worker; the separate process is an explicit operational choice.
6. Open `http://127.0.0.1:8000/ui/` for the authenticated operator console. It displays queue metrics and owner-scoped workflow history, and provides explicit cancellation, safe-resume enqueueing, and externally verified outcome reconciliation.

Workflow resume is asynchronous too: POST /agent/workflows/{workflow_id}/resume validates the original request and enqueues the existing job. Only the pull worker executes resumed steps under its lease and fencing token. The original request must be supplied again because plaintext inputs are not stored in workflow history. A resume request never runs tools inside the HTTP process. The console can inspect the resume decision before enqueueing.

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

The source-backed knowledge API accepts bounded user-submitted text, stores source provenance, chunks documents for SQLite FTS5 retrieval, and returns citation references. It never fetches supplied URLs and is not automatically injected into agent context. See `docs/operations/knowledge.md`.

An optional OpenRouter text adapter can be enabled explicitly through environment configuration and invoked with `POST /models/generate-remote`. It is disabled by default, restricted to the approved HTTPS origin, and never silently falls back to another provider. See `docs/operations/remote-models.md`.

The self-hosted RTL operator dashboard is served at `/ui/`; it provides status, task and Job Engine metrics, owner-scoped Workflow history, step inspection, cancellation, safe-resume enqueueing, external-outcome reconciliation, provider, memory, knowledge, content-draft, and explicit model-inference controls without external web assets. See `docs/operations/operator-ui.md`.

The content draft API provides owner-scoped draft/version management, deduplication, explicit approval/revocation, archive/restore, and audit events. It does not publish externally. See `docs/operations/content-drafts.md`.


## Verified integration status — 2026-11-02

- Instagram Graph API image publishing is implemented as an explicit opt-in adapter.
- Approved Instagram drafts can reference owner-scoped JPEG/PNG assets. The pull-driven dispatcher generates a short-lived HMAC-signed HTTPS media URL instead of passing a local filesystem path.
- Public media delivery is disabled until `MRH_PUBLIC_MEDIA_BASE_URL` and `MRH_PUBLIC_MEDIA_SIGNING_KEY` are configured. Instagram publishing additionally requires valid professional-account credentials and permissions.
- CI verifies the signed URL generation, expiry/signature handling, and scheduled dispatcher handoff using test doubles. It does not verify public network reachability or publish to a real Instagram account.
- External reachability, edge rate limiting, and a controlled live-account acceptance test remain deployment gates. Production publishing must not be described as end-to-end verified until those gates pass.


## Automated code security analysis

Python source is additionally analyzed with GitHub CodeQL using the `security-extended` query suite on pull requests, pushes to `main`, and a weekly schedule. Results are uploaded to GitHub Code Scanning. This complements (and does not replace) local static checks, Ruff, tests, and dependency auditing. See `docs/security/code-scanning.md` for permissions, scope, and operational guidance.
