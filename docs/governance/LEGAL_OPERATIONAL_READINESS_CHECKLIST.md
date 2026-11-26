# Legal & Operational Readiness Checklist — G12

- **Baseline:** 2026-11-27
- **Scope:** HUB, EL_AI, EL_AGENT, MR_SIAVASH_AI and their approved integrations
- **Authority:** [G0–G12 governance](../GOVERNANCE_PRODUCT_STRATEGY_G0_G12.md), [ADR-0047](../architecture/decisions/ADR-0047-four-product-ecosystem-scope-and-telegram-ownership.md), and [G9 risk register](ECOSYSTEM_RISK_DEPENDENCY_REGISTER.md)
- **Status:** OWNER ACTION REQUIRED — this checklist is a preparation and evidence-tracking aid, not a legal opinion, certification or production approval

## 1. Purpose and decision rule

G12 is complete only when applicable legal, privacy, financial, operational and live-acceptance decisions have been made by the appropriate accountable owner and supported by recorded evidence.

A repository document, public GitHub visibility, passing CI, or a drafted checklist does not establish legal rights, regulatory compliance, service readiness or deployment authorization. Where qualified legal advice is appropriate, obtain it before making public/legal claims or distributing a release.

Use **NOT REVIEWED**, **NEEDS EVIDENCE**, **OWNER DECISION REQUIRED**, **ACCEPTED**, or **NOT APPLICABLE**. Every ACCEPTED / NOT APPLICABLE state must include the reviewer, date, rationale and evidence.

## 2. Intellectual property, authorship and licensing

| ID | Review item | Required evidence / decision | Accountable owner | Initial state |
|---|---|---|---|---|
| L-01 | Confirm project and contributor authorship/provenance | Repository history, contributor records, third-party notices, and an approved attribution policy | Ecosystem owner | OWNER DECISION REQUIRED |
| L-02 | Select, retain or document the licensing model for each repository | Written decision identifying the license/terms, files covered, exceptions and distribution permissions; legal review where appropriate | Ecosystem owner + qualified adviser | OWNER DECISION REQUIRED |
| L-03 | Inventory third-party code, libraries, assets, fonts, datasets and model terms | Dependency/asset inventory, license compatibility review, attribution obligations and model/provider use restrictions | Product maintainers + qualified adviser | NEEDS EVIDENCE |
| L-04 | Define contribution and redistribution rules | Contributor permission/provenance process, third-party contribution rules, and release attribution | Ecosystem owner | OWNER DECISION REQUIRED |

**Existing evidence:** HUB COPYRIGHT.md records that no project-wide open-source license has been selected or granted. This is a recorded project status, not an independent legal assessment.

## 3. Privacy, data handling and user-facing disclosures

| ID | Review item | Required evidence / decision | Accountable owner | Initial state |
|---|---|---|---|---|
| P-01 | Map personal/confidential data by product and flow | Data inventory with source, classification, purpose, storage location, recipients and retention | Product data owners | NEEDS EVIDENCE |
| P-02 | Review privacy notices, terms and consent for each user-facing surface | Approved notices/terms for Web, Telegram, Desktop, Android and APIs as applicable | Ecosystem owner + qualified adviser | OWNER DECISION REQUIRED |
| P-03 | Review third-party model/provider processing | Provider terms, data sent, retention/training settings where available, region, opt-in status and fallback policy | Product owner | NEEDS EVIDENCE |
| P-04 | Validate retention, export, deletion and incident disclosure workflows | Test evidence showing user data controls and documented response/notification decision path | Product maintainers + privacy owner | NEEDS EVIDENCE |
| P-05 | Review public/private separation | Negative tests proving public website/Gateway cannot access HUB owner memory, credentials, private tasks or device control | HUB security + Website maintainer | NEEDS EVIDENCE |

Do not include live credentials, private user data, or production records in this checklist. Link redacted evidence with access controls.

## 4. Operational ownership and service readiness

| ID | Review item | Required evidence / decision | Accountable owner | Initial state |
|---|---|---|---|---|
| O-01 | Name accountable product maintainers and release operators | Owner-approved RACI with named roles/accounts, deputies and access boundaries | Ecosystem owner | OWNER DECISION REQUIRED |
| O-02 | Define support, monitoring and escalation responsibilities | Runbook, monitoring/alert ownership, service hours/availability expectations and escalation path | Product operations owner | NEEDS EVIDENCE |
| O-03 | Verify backup and recovery | Protected backup procedure and isolated restore drill; for HUB restore SQLite data with its matching workflow-encryption key | HUB operations owner / relevant product operators | NEEDS EVIDENCE |
| O-04 | Verify incident response and credential revocation | Incident classification, containment, secret rotation/revocation, audit preservation and recovery steps | Security + operations owners | NEEDS EVIDENCE |
| O-05 | Verify release and rollback process | Release provenance, exact artifact/source identity, rollback/disable steps and post-release health evidence | Release operator | NEEDS EVIDENCE |
| O-06 | Confirm environment and live-service acceptance separately from CI | Named environment, test identity, exact version, smoke/integration evidence and known limitations | Product operator | OWNER DECISION REQUIRED |

## 5. Cost, providers and external services

| ID | Review item | Required evidence / decision | Accountable owner | Initial state |
|---|---|---|---|---|
| C-01 | Confirm provider/model service terms and data handling | Provider configuration, terms, rate limits, data path, opt-in status and failure behavior | Product owner | NEEDS EVIDENCE |
| C-02 | Approve recurring and usage-based costs before activation | Current plan, exact recurring/variable charge estimate, budget ceiling, alert/stop control and explicit approval | Billing/account owner | OWNER DECISION REQUIRED |
| C-03 | Confirm free-tier quotas and overage behavior where used | Current account quota/eligibility and a tested fail-closed behavior at quota exhaustion | Product owner | NEEDS EVIDENCE |
| C-04 | Review external publishing, messaging and device side effects | Permission scope, owner confirmation, rate limits, audit, disable/revoke procedure and safe test environment | Product owner + operator | OWNER DECISION REQUIRED |

No deployment, paid resource provisioning, provider activation, live Telegram change or public release is authorized by the existence of this checklist.

## 6. Product-specific acceptance gates

| Product | Required operational evidence | Initial state |
|---|---|---|
| HUB | Owner setup/auth, protected default branch, backup + key restore, worker lifecycle, audit/authorization, release and rollback | NEEDS EVIDENCE |
| EL_AI | Test-bot Telegram round trip, duplicate/unknown/expired delivery, rate-limit/failure handling, secret custody and disable procedure | OWNER DECISION REQUIRED |
| EL_AGENT | Physical Windows/Android install and permission matrix, offline behavior, device-local policy, recovery and rollback | OWNER DECISION REQUIRED |
| MR_SIAVASH_AI | Public/private boundary review, privacy notices, production/preview provenance, secret isolation and release rollback | NEEDS EVIDENCE |

## 7. Sign-off record

Complete a separate sign-off for each product and shared obligation. Do not use one generic approval to imply approval of unrelated repositories or environments.

| Scope | Decision | Reviewer / role | Date | Evidence / rationale | Residual risks |
|---|---|---|---|---|---|
| Ecosystem legal/IP | PENDING |  |  |  |  |
| Privacy/data processing | PENDING |  |  |  |  |
| HUB operations | PENDING |  |  |  |  |
| EL_AI operations / Telegram | PENDING |  |  |  |  |
| EL_AGENT device acceptance | PENDING |  |  |  |  |
| Website public service | PENDING |  |  |  |  |
| Cost / external providers | PENDING |  |  |  |  |

## 8. G12 exit criteria

G12 may be marked DONE only when:

1. Applicable IP, licensing, third-party and contribution decisions are reviewed and documented.
2. Privacy/data-flow/retention/disclosure requirements are approved and verified for each relevant surface.
3. Named maintainers, operators, monitoring, escalation and incident responsibilities are accepted.
4. Required backup and restore drills pass; key custody and recovery limitations are explicit.
5. Cost/provider/external side-effect gates have current owner approvals.
6. Applicable Telegram, device, cloud and production acceptance has been performed in the intended environment with redacted evidence.
7. Residual risks are accepted by the correct owner or remain blockers; none are silently waived.

Until those conditions are evidenced, G12 remains OWNER ACTION REQUIRED.
