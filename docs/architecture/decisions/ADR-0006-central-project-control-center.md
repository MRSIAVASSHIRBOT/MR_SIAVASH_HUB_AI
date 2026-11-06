# ADR-0006: Central Project Control Center

- Status: Proposed
- Date: 2026-11-06
- Decision owners: repository owner
- Scope: MR_SIAVASH_HUB_AI operator experience and its integration boundaries

## Context

The repository already contains a self-hosted Persian/RTL operator UI at `/ui/`, owner authentication, health/readiness cards, provider metadata, task and workflow inspection, workflow cancellation/resume controls, memory and knowledge tools, and content/media workspaces. Replacing it with a second dashboard would duplicate authentication, operational state, UI components, and security boundaries.

The wider project ecosystem includes independently deployed repositories. The current UI does not yet provide a verified, unified inventory or cross-project status view. In particular, a local API readiness response must not be presented as proof that a separate website, Worker, database, or external integration is healthy.

## Decision

Extend the existing authenticated operator UI into the **Central Project Control Center**. Do not create a parallel dashboard or move the independent projects into this repository.

The first implementation phase is read-only. It must aggregate only evidence available through explicitly configured, least-privilege adapters and show source, observation time, and freshness for every status. A missing credential, unsupported endpoint, stale observation, or failed probe is shown as **unknown/unavailable**, never as healthy.

### Initial project registry

The first registry should contain only these confirmed active projects, with each deployment boundary kept distinct:

| Project | Repository | Initial status sources |
| --- | --- | --- |
| MR_SIAVASH_HUB_AI | `MRSIAVASSHIRBOT/MR_SIAVASH_HUB_AI` | Local `/health`, `/ready`, worker heartbeat, GitHub metadata/CI |
| MR_SIAVASH_AI | `MRSIAVASSHIRBOT/MR_SIAVASH_AI` | GitHub metadata/CI; Cloudflare Worker/Pages status only after an explicit read-only account integration is configured |
| Gshop | `MRSIAVASSHIRBOT/Gshop` | GitHub metadata/CI; Cloudflare Pages/Worker and D1 status only through configured read-only endpoints |

The registry is configuration, not a discovery mechanism that silently enrolls every accessible repository. A project can be marked inactive without deleting its history. The paused Telegram bot and unrelated repositories are not enrolled by default.

### Control-center information model

Each project card and detail view should distinguish:

- **Repository:** default branch, latest commit, open pull requests, latest relevant CI result, and repository observation timestamp.
- **Runtime:** configured health endpoint, observed result, check time, and freshness; no endpoint means unknown, not healthy.
- **Infrastructure:** only explicitly configured read-only Cloudflare metadata; never infer deployment success from repository state.
- **Risk:** open blockers, stale checks, failing CI, and unresolved operational findings, with links to their source records.
- **History:** last successful observation and previous state, so status changes can be explained.

Every status uses a small finite vocabulary: `healthy`, `degraded`, `failing`, `unknown`, `not_configured`. A status is accompanied by a reason code and source reference. Aggregate health must not hide a failing subsystem behind a green project-level badge.

### Trust and security boundaries

1. All private project data is served by authenticated same-origin API routes. Browser code never receives GitHub or Cloudflare API tokens.
2. Adapters use allow-listed hosts, fixed endpoint templates, bounded pagination/timeouts/response sizes, strict schema validation, and sanitized errors. No arbitrary URL fetch, shell execution, or arbitrary code execution is exposed.
3. The first phase is read-only: no repository writes, branch creation, PR merging, DNS changes, Worker deployment, secret changes, D1 mutation, or resource deletion.
4. GitHub and Cloudflare access are independent optional integrations. Lack of one must not prevent local Hub status from rendering.
5. Store only the minimum metadata needed for the dashboard. Do not persist access tokens, raw provider payloads, secrets, workflow request bodies, or private source contents in status history.
6. Apply per-owner authorization, audit metadata for every probe/configuration change, and `Cache-Control: no-store` to private status responses.
7. External probes must be rate-limited and user-triggered or scheduled by a bounded worker. The page must not start unbounded polling.
8. Status results are observations, not guarantees. UI copy must show timestamps and stale/unknown states explicitly.

### Approval boundary for future actions

A later phase may propose reviewable repository changes or infrastructure actions, but execution remains separate from monitoring. Any operation that changes production, DNS, access control, secrets, billing, public exposure, or deletes/modifies persistent data requires a fresh, explicit owner approval bound to the exact action and target. A dashboard click must not convert a read-only integration into a broad administrative capability.

## Implementation phases

### Phase 0 — Architecture and inventory (this ADR)

- Reuse the existing `/ui/` shell, authentication, CSP, and same-origin API pattern.
- Keep the project registry explicit and version-controlled.
- Define typed status contracts and freshness semantics before rendering cards.
- Do not claim cross-project monitoring is implemented.

### Phase 1 — Read-only project registry and repository status

- Add a typed, validated project registry with stable project IDs and explicit repository names.
- Add a GitHub adapter that can read repository metadata, default-branch head, open PR metadata, and latest CI summaries using a server-side least-privilege credential.
- Do not expose raw GitHub credentials or source contents to the browser.
- Return partial results per project; a failure for one repository must not fail the whole dashboard.
- Add deterministic tests for schema validation, pagination bounds, timeouts, missing credentials, stale observations, and partial failures.

### Phase 2 — Runtime and Cloudflare observations

- Add explicitly configured, allow-listed health probes for independently deployed services.
- Reuse the existing isolated read-only Cloudflare gateway where its contract fits; do not bypass it with a second unrestricted client.
- Treat Pages, Workers, and D1 as separate resources and report only fields actually returned by supported read endpoints.
- Keep production mutations out of this phase.

### Phase 3 — Risk and operational intelligence

- Correlate CI failures, stale health checks, open PRs, and documented blockers into explainable risk summaries.
- Preserve source links and observation timestamps.
- Avoid opaque scores; every priority must be traceable to a concrete finding and severity rule.

### Phase 4 — Reviewable action proposals

- Present suggested fixes as proposals with target, diff/operation summary, expected impact, rollback notes, and test evidence.
- Require action-bound approval for sensitive changes.
- Keep execution and verification separate; report each state independently.

## Acceptance criteria

- The existing operator UI remains the only control-center entry point.
- The initial registry contains only the three confirmed active projects.
- Each project can independently show partial, stale, unknown, or unavailable data without falsely reporting healthy.
- Every displayed status includes source and last-observed time.
- No browser-visible provider credentials or unrestricted URL/proxy endpoint exists.
- Read-only integration tests cover authentication, owner scoping, timeouts, pagination, malformed provider responses, and partial failures.
- Existing Hub dashboard functions and security tests remain green.
- No Cloudflare production deployment or infrastructure mutation is performed as part of this ADR.

## Explicit non-goals

- Replacing GitHub, Cloudflare, or the existing project dashboards.
- Automatically discovering and enrolling every repository.
- Merging pull requests or deploying production resources.
- Running shell commands or arbitrary remote code from the dashboard.
- Treating a green repository CI result as proof of live runtime health.
- Claiming the control center is implemented before the phases and acceptance criteria are verified.
