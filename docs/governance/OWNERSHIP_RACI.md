# Product Ownership & RACI — G5

- **Date:** 2026-11-27
- **Status:** Initial operating RACI; organization/person-level assignments require owner review.
- **Authority:** ADR-0047
- **Scope:** Four active products plus independent security assurance.

## 1. Roles

| Role | Meaning |
|---|---|
| Owner | Ecosystem owner; final product, legal, cost and high-impact operational decision authority |
| HUB | MR_SIAVASH_HUB_AI product maintainer |
| EL_AI | MR_SIAVASH_EL_AI product maintainer |
| EL_AGENT | MR_SIAVASH_EL_AGENT product maintainer |
| Website | MR_SIAVASH_AI product maintainer |
| Security Assurance | Independent reviewer/function operating across products; it does not own product features or approve its own findings |
| Release Operator | Authorized operator for a specific environment and deployment; must be explicitly assigned for each release |

R = Responsible for doing the work; A = Accountable for the outcome; C = Consulted; I = Informed. Each row has one accountable product/role for the stated domain. Owner accountability for reserved decisions is explicit.

## 2. Capability ownership

| Capability / decision | Owner | HUB | EL_AI | EL_AGENT | Website | Security Assurance |
|---|---|---|---|---|---|---|
| Ecosystem vision, mission, portfolio scope | A | R | C | C | C | C |
| Central planning, GPI/AWI/CGI, decisions | I | A/R | C | C | I | C |
| Shared private owner memory and workflow state | I | A/R | C | C | I | C |
| Tool/skill registry and cross-project grants | I | A/R | C | C | I | C |
| HUB API, worker, model and workflow runtime | I | A/R | C | C | I | C |
| Telegram bot, Telegram identity and delivery | I | C | A/R | I | I | C |
| Personal conversation and personalization | I | C | A/R | C | I | C |
| Local Windows/Android runtime and device policy | I | C | C | A/R | I | C |
| Local model/provider and offline capability | I | C | C | A/R | I | C |
| Public identity, website, education and workspace | I | C | C | I | A/R | C |
| Public Gateway and public content boundary | I | C | C | I | A/R | C |
| Cross-product contracts and integration plan | I | A/R* | R | R | R | C |
| Product-specific testing and CI | I | A | A | A | A | C |
| Independent threat model and assurance review | I | C | C | C | C | A/R |
| Product-level remediation | I | A/R | A/R | A/R | A/R | C |
| Paid provider/infrastructure commitment | A | R | C | C | C | C |
| Production release approval | A | R* | R* | R* | R* | C |
| Legal/IP/license/privacy/terms approval | A | C | C | C | C | C |
| Live Telegram/device acceptance | A | C | R | R | I | C |
| Backup/restore and incident response per product | I | A/R | A/R | A/R | A/R | C |

* HUB coordinates shared interface policy and portfolio integration, but each producer/consumer remains responsible for its own contract implementation. A release operator must be explicitly named; no blanket cross-product production authority is implied.

## 3. Decision rights

### Product owners

Each product maintainer may make reversible implementation choices inside the accepted product boundary, provided interfaces, data ownership, security constraints and costs do not change.

### Reserved owner decisions

The ecosystem owner retains decisions for:
- changes to portfolio scope or product identity;
- material changes to vision, audience, pricing or product priority;
- paid infrastructure, provider spending or recurring commitments;
- production deployment, external publishing, live Telegram activation and remote device action enablement;
- secret rotation or credential changes with live impact;
- destructive data operation, retention changes or migration with production impact;
- legal, privacy, IP, license and terms-of-service acceptance.

### Independent security review

Security Assurance may block or require remediation for an evidenced trust-boundary failure. Product maintainers may not close their own security findings solely by self-attestation; evidence and independent re-review are required for high-severity items.

## 4. Escalation and conflict resolution

1. Resolve implementation conflicts within the affected product if ownership does not cross boundaries.
2. Cross-product data, contract or identity conflict goes to HUB architecture coordination and affected maintainers.
3. Scope or product-authority conflict goes to the ecosystem owner and requires an ADR.
4. Security-critical unresolved conflict blocks the affected release slice.
5. Cost/legal/production decisions remain blocked until the relevant owner action is recorded.

## 5. Completion and review

This RACI becomes operational after the owner reviews the role assignments and identifies named maintainers/release operators. Repository names are capability owners; they do not imply that the same individual has approved every legal, paid or production action.
