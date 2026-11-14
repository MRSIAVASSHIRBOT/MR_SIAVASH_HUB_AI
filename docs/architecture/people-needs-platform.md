# People-Needs and Capability Platform Foundation

## Purpose

Build a product platform around verified user problems rather than a disconnected list of AI features. The first implementation establishes a first-party capability catalog and an owner-scoped evidence ledger for product opportunities. Existing modules remain the canonical execution infrastructure.

## Existing architecture reused

- AI/model routing, bounded Agent Orchestrator, memory and source-backed knowledge retrieval.
- Shared Task/Job/Workflow engine, policy checks, approval records, worker leases, cancellation, recovery, and audit events.
- Existing content drafts, media assets, video processing, scheduled dispatch, and social adapters.
- Existing defensive security, project registry, and developer-agent foundations.
- Existing third-party capability-source catalog remains separate: it tracks upstream integration candidates, not first-party service domains or customer problems.

## First-party service domains

The authenticated `GET /platform/domains` catalog records ten stable domains: content, web, automation, customer support, business operations, defensive security, learning, documents, productivity, and multilingual services. Each domain is explicitly labelled `foundation`, `partial`, or `planned`; this is a product-planning contract, not a claim that every user-facing service is complete.

## Needs and opportunity evidence

The authenticated `/research/opportunities` API stores owner-scoped opportunity records and curated public-source evidence. Evidence records contain a canonical HTTPS URL, source category, short observation summary, signal strength, publication timestamp, and capture timestamp. An owner-scoped source registry deduplicates canonical URLs across opportunities while preserving a separate observation for each opportunity. The registry records the normalized hostname, an explicit publisher group, and first/last capture timestamps. Reusing a source does not duplicate its provenance record; each opportunity still retains its own contextual observation.

Publication timestamps must include a timezone and cannot be in the future. Freshness is reported, not inferred from the capture date: public discussions, forums, app reviews, and support requests use a 180-day window; other sources use 365 days; research reports use 730 days. Missing publication dates are marked unknown and stale evidence remains visible, but neither can satisfy the validation gate.

Opportunity lifecycle:

`new -> validating -> validated -> prioritized -> in_progress`

Alternative transitions allow deferral or rejection and later re-validation. Every transition is validated. Evidence is unique by canonical URL within an opportunity and links to one owner-scoped source record across opportunities. Validation requires at least two current, dated URLs, two source types, two distinct hostnames, and two publisher groups. Publisher groups are researcher-supplied provenance labels (defaulting to the exact hostname); they reduce obvious syndication/subdomain double-counting but are not independent verification or proof of common ownership.

## Priority heuristic

When all three owner-reviewed scores exist, a transparent 0–100 heuristic is calculated:

`priority = round((impact × 0.40 + frequency × 0.35 + feasibility × 0.25) × 20)`

Each input is an owner/researcher assessment from 1 to 5. The score is a triage aid, not a measured market-size estimate or proof of demand. Evidence count and signal strength remain visible separately.

## Security and privacy

- All routes require an authenticated owner session.
- All opportunity and evidence queries are owner-scoped in SQL.
- Source URLs must be HTTPS, public-hosted, and free of embedded credentials, query strings, fragments, and non-standard ports.
- This subsystem records curated observations only; it has no fetch, crawler, arbitrary network, or source-execution capability.
- External actions remain under the shared policy and approval system.
- User-submitted text and public-source summaries are untrusted data, not instructions.

## Next development slices

1. Review source terms and add publisher-specific provenance guidance before broadening read-only discovery providers.
2. Calibrate confidence using representative pilot evidence and outcome measurements; hostname/publisher labels remain researcher assertions.
3. Map each validated opportunity to existing modules or a bounded new capability proposal.
4. Add a capability-to-workflow template catalog and approved integration onboarding.
5. Add representative pilot studies with adoption, task completion, user satisfaction, reliability, and operating-cost measurements.

## Explicit non-goals for this foundation

No public web crawler, automated account creation, private-community scraping, personal-data profiling, autonomous public publishing, paid provider activation, or arbitrary code execution is introduced.


## Consent-based feedback intake

The authenticated /research/feedback endpoints support structured feedback capture. Submission requires explicit consent_to_research=true; the server records a versioned consent marker. The schema deliberately has no name, email, phone, account handle, or free-form contact field. The intake stores only a domain, broad audience segment, concise need summary, current workaround, and optional impact/frequency scores. The UI/API contract should tell contributors not to include identifying or sensitive personal information.

Feedback is owner-scoped, can be triaged as new/reviewed/converted/dismissed, and can be deleted by its owner. This first slice is an authenticated operator intake, not a public anonymous survey service or a direct third-party inbox integration. Consent is required for research use; it does not imply permission to publish quotations or identify contributors.

## Outcome measurement

Each opportunity can store owner-scoped outcome measurements through /research/opportunities/{id}/outcomes. Supported metrics include time saved, task completion rate, satisfaction, error rate, active users, and operating cost. Every record includes a baseline, observed value, unit, sample size, and measurement period. Values are observations, not causal proof: pilots should report their population, method, limitations, and whether the sample is representative. Measurements are deleted with their parent opportunity.


## Operator workspace

The local authenticated operator UI now exposes the capability catalog, opportunity intake, curated evidence entry, feedback triage/deletion, and outcome measurement. It uses the existing same-origin API and session token handling; it does not load third-party scripts or publish feedback externally. Opportunity validation still requires the API's evidence gate, and measurement timestamps must include an explicit timezone offset.

The feedback intake rejects obvious email addresses, phone-number patterns, and credential-like strings in its free-text fields as a defense-in-depth measure. This is not a guarantee that all identifying information can be detected; operators must continue to minimize and review text before saving it.


## Read-only public-source discovery

The authenticated /research/discovery/search endpoint offers bounded keyword discovery through two fixed public APIs: Hacker News Algolia search and selected Stack Exchange sites. Provider hosts and paths are constants; user input is sent only as a query parameter and is never interpreted as a URL. Requests use short timeouts, no redirects, bounded response size, a SQLite-backed per-owner request budget shared by API worker processes using the same database, and an identical-query cooldown. Result links are returned as review candidates only; result pages are not fetched and results are not automatically stored as evidence.

Hacker News candidates link to the public discussion thread. Stack Exchange results are accepted only when their HTTPS hostname matches the selected allow-listed site. Author names and profile details are not collected. The discovery limiter stores short-lived request records in the existing SQLite database, so separate API worker processes sharing that database enforce the same per-owner budget. Provider Retry-After responses and Stack Exchange backoff values are persisted as provider-wide cooldowns; the API returns a Retry-After header when a cooldown is active. This is suitable for the current single-host SQLite deployment model; a multi-host deployment must move this limiter to a shared transactional store. Expired request records are pruned during subsequent checks. Provider cooldowns apply across owners, preventing one account from ignoring an upstream quota signal. Provider quota/backoff signals and source-specific terms must be reviewed before increasing usage.

Official provider references:
- Hacker News Search API: https://hn.algolia.com/api
- Stack Exchange API: https://api.stackexchange.com/docs
- Stack Exchange advanced search: https://api.stackexchange.com/docs/advanced-search

These connectors are discovery aids, not representative market research. A researcher must inspect the source, record an independent observation, consider its date and context, and seek corroboration before validating an opportunity.


## Evidence independence rationale

Evidence records may include an optional researcher-entered independence rationale (up to 1,000 characters). The rationale is shown in the operator form and retained with the evidence record. It is an explicit research attestation, not an automated ownership verification. When transitioning an opportunity to validated, only current, dated evidence with a non-empty rationale counts toward the existing diversity gates (distinct URL, source type, hostname, and publisher group). Operators must substantiate the rationale from public information; the system does not claim to prove editorial independence.
