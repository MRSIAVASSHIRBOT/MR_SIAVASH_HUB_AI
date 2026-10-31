# Module Boundaries and Contracts

## 1. Rule

A module owns its domain logic and data. Other modules interact through application services, typed schemas, or domain events—not private database tables or internal imports.

## 2. Module registry

| Domain | Owns | Must not own |
|---|---|---|
| AI Core | model capabilities, provider adapters, routing decisions | agent lifecycle or workflow scheduling |
| Agent System | agent definitions, plans, delegation policy | separate job queue or direct unrestricted tools |
| Memory | scoped memories, retrieval, retention and provenance | global unfiltered context |
| NEXUS | developer task plans, repository context, code-review workflows | independent model router or unrestricted shell |
| Video Engine | media project metadata, render plans, asset references | job scheduler or provider secrets |
| Discovery Engine | source connectors, research records, citations | arbitrary crawling or policy bypass |
| Social Automation | content plans, drafts, channel publishing workflows | channel credentials in UI or unsupervised public posting |
| Telegram Integration | Telegram transport adapter, update normalization | business logic duplicated from Social Automation |
| Cybersecurity Lab | authorized defensive assessments and reports | credential theft, covert access, exploit deployment or evasion |
| Workflow Engine | workflow definitions, schedules, job state, retries and cancellation | model-specific logic |
| Plugin System | tool manifests, schemas, trust levels and grants | implicit execution authority |
| Developer Console | operator views for jobs, agents, diagnostics and approvals | privileged backend logic |

## 3. Shared contracts

### Task
- `task_id`: opaque unique identifier
- `workspace_id`: tenant/workspace scope
- `task_type`: registered task kind
- `status`: queued, running, waiting_approval, succeeded, failed, cancelled
- `risk_class`: low, moderate, high, prohibited
- `created_at`, `updated_at`
- `idempotency_key`: optional deduplication key
- `trace_id`: end-to-end correlation identifier

### Tool manifest
- stable tool identifier and version
- human-readable purpose
- input and output JSON schemas
- declared network and data access
- side-effect classification
- timeout and resource limits
- required permission grants
- publisher and integrity metadata

### Tool invocation
- caller agent/task identity
- workspace scope
- validated input
- policy decision and reason
- grant reference
- timeout/deadline
- result reference
- audit correlation identifier

### Domain event
- event identifier and schema version
- event type
- workspace and aggregate identifiers
- occurred-at timestamp
- trace/correlation identifier
- minimal typed payload
- no secrets or unnecessary personal data

## 4. Ownership and dependency direction

Presentation -> API/application services -> domain modules -> infrastructure ports.

Infrastructure adapters implement ports declared by domain/application layers. Domain modules do not import UI code or concrete provider SDKs.

## 5. Consolidation decisions

- Agent execution and workflows share one Task/Job Engine.
- Memory and knowledge search share a retrieval service with explicit scopes.
- Plugins and MCP tools share one Tool Registry and authorization path.
- Telegram and other social networks are channel adapters; publishing policy belongs to Social Automation.
- NEXUS is a specialist developer agent built on the shared core.
- Developer Console is a UI over operational APIs, not a second orchestration backend.
- Video rendering is a job type executed by bounded workers.

## 6. Data ownership

Each module accesses its own repositories through its application service. Cross-module reads use public query interfaces. Cross-module writes use commands/events. Initial SQLite may use one physical database, but table ownership remains explicit.

## 7. Versioning

Public internal contracts are versioned. Breaking changes require migration notes and tests. Plugin manifests must declare compatible API versions. Unknown fields are rejected for security-sensitive inputs unless explicitly documented otherwise.
