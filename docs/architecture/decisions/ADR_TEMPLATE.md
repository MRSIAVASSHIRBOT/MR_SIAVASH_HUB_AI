# Architecture Decision Record (ADR) Template

Use one ADR for a material architecture, data-ownership, security-boundary, contract, deployment-topology, dependency, or lifecycle decision. Keep accepted ADRs immutable in meaning; record a superseding ADR rather than rewriting historical decisions.

- **ADR ID:** ADR-NNNN
- **Title:**
- **Status:** Proposed / Accepted / Rejected / Superseded / Deprecated
- **Date proposed:**
- **Date decided:**
- **Decision owner:**
- **Authors / reviewers:**
- **Scope:** HUB / EL_AI / EL_AGENT / MR_SIAVASH_AI / shared
- **Related Work Orders / issues / PRs:**
- **Supersedes / superseded by:**

## 1. Context and problem

Describe the situation, observed constraints, business/product need, and why a decision is required now. Link exact source, tests, metrics, incidents, requirements, or owner statements. Separate verified facts from assumptions.

## 2. Decision drivers and constraints

List the factors that materially affect the choice:

- Functional requirements and quality attributes.
- Security, privacy, trust boundaries and threat assumptions.
- Data ownership, classification, retention and provenance.
- Performance, availability, recovery and operability.
- Cost, licensing, provider and platform constraints.
- Compatibility, migration and reversibility.
- Owner-controlled or legal/operational gates.

## 3. Options considered

| Option | Summary | Benefits | Costs / risks | Compatibility / migration |
|---|---|---|---|---|
| A — preferred candidate |  |  |  |  |
| B — alternative |  |  |  |  |
| C — defer / retain current state |  |  |  |  |

Include the status quo where it is a meaningful option. Explain why material alternatives were rejected; do not manufacture options that were not evaluated.

## 4. Decision

State the selected option precisely, including:

- Components/products that own the capability and data.
- Interfaces, contract versions, schemas and event boundaries.
- Authentication, authorization scopes, approval and audit requirements.
- Failure, timeout, retry, idempotency, cancellation and recovery semantics.
- Deployment/configuration behavior and explicit non-goals.
- Conditions or owner approval required before activation.

## 5. Architecture and data-flow impact

**Affected products and modules:**

**Provider → consumer contracts:**

**Data classification and permitted fields:**

**Trust boundaries and authorization:**

**External services / devices / providers:**

**Observability, audit and evidence:**

**Privacy, retention, deletion and export:**

## 6. Security and safety assessment

Record relevant threats, misuse/abuse cases, least-privilege assumptions, negative tests, secrets boundaries, model/tool trust, and fail-closed behavior. Link security review or explicitly mark it NOT RUN / NOT APPLICABLE with rationale.

## 7. Consequences

### Positive consequences
- 

### Negative consequences and trade-offs
- 

### Risks accepted or introduced
- 

### Follow-up Work Orders
- 

## 8. Implementation, migration and rollback

Describe the staged rollout, compatibility window, migration/backfill, feature flags, monitoring, rollback/disable strategy and recovery procedure. A decision that cannot yet be implemented safely must say what blocks implementation.

## 9. Verification and acceptance

| Criterion | Verification | Exact SHA / evidence | Result |
|---|---|---|---|
| Compatibility |  |  | NOT RUN |
| Security / authorization |  |  | NOT RUN |
| Failure and recovery |  |  | NOT RUN |
| Operational acceptance |  |  | NOT RUN |

## 10. Approval and review

- **Decision:** ACCEPTED / REJECTED / DEFERRED
- **Decision owner:**
- **Approval evidence:**
- **Decision date:**
- **Review trigger / date:**

An ADR is **Accepted** only when the accountable decision owner has made the decision and the record captures its consequences. Implementation, merge, deployment and legal/financial authorization remain separate gates. A proposed ADR does not authorize production side effects.
