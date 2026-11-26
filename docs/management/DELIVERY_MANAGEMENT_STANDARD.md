# Delivery Management Standard — G11

- **Baseline:** 2026-11-27
- **Scope:** HUB, EL_AI, EL_AGENT, MR_SIAVASH_AI and approved shared contracts
- **Authority:** [G0–G12 governance](../GOVERNANCE_PRODUCT_STRATEGY_G0_G12.md), [four-product technical phase inventory](../roadmap/FOUR_PRODUCT_TECHNICAL_PHASES.md), and [continuous execution standard](CONTINUOUS_EXECUTION_STANDARD.md)
- **Status:** Initial delivery-control standard; repository-level milestones and owners require progressive validation

## 1. Purpose

G11 turns portfolio goals and technical phases into bounded, owned, reviewable and evidence-backed delivery. The control objects are:

1. **Work Order (WO):** one bounded deliverable with an accountable owner, dependencies, acceptance criteria and evidence.
2. **Milestone (MS):** a named outcome grouping one or more Work Orders with explicit entry/exit gates.
3. **Release (REL):** a reviewed, tested and approved set of changes published to an identified environment/version.

A phase is not a Work Order, a milestone is not a release, and a merged PR is not automatically a production release.

## 2. Work Order lifecycle

| State | Entry condition | Exit condition |
|---|---|---|
| PROPOSED | Need or defect is recorded | Scope, owner, priority and evidence are sufficient for triage |
| READY | Dependencies and acceptance criteria are explicit; no unresolved start blocker | Work starts on an approved branch |
| IN_PROGRESS | An implementer is actively changing the agreed scope | Implementation submitted for review or a concrete blocker appears |
| BLOCKED | A named external/owner dependency prevents safe progress | Dependency evidence attached and owner clears the gate |
| REVIEW | PR or artifact is available for independent review | Review findings resolved; exact-head checks and criteria evaluated |
| ACCEPTED | All Work Order acceptance criteria pass and accountable reviewer records decision | Included in an authorized release or closed as a non-release deliverable |
| RELEASED | Accepted content is present in the intended release/environment and post-release evidence is recorded | Monitor, maintain, or supersede |
| CANCELLED | Work is no longer valid or is superseded | Reason and replacement reference recorded |

Rules:

- A Work Order has one accountable role and one owning repository. Cross-repository work uses linked provider/consumer Work Orders under one shared integration ID.
- A Work Order must declare scope and non-goals, related G phase/technical phase, dependencies, G9 risk IDs, acceptance criteria, tests and rollback/disable behavior where relevant.
- Do not set READY while a mandatory prerequisite or owner-controlled gate remains unresolved.
- Work that overlaps an open PR must be coordinated by exact path, branch and SHA. Do not duplicate it or overwrite another contributor's work.
- Changes to scope, acceptance criteria or contract version are recorded before implementation continues.
- Blocked time does not count as implementation progress; the blocker and next owner action must be explicit.

The reusable fields are in [WORK_ORDER_TEMPLATE.md](WORK_ORDER_TEMPLATE.md).

## 3. Priority and sequencing

| Priority | Meaning | Handling |
|---|---|---|
| P0 | Immediate security, data-loss, unauthorized-action or irreversible production risk | Stop affected rollout and escalate |
| P1 | High-impact blocker or prerequisite for a committed milestone | Prioritize before dependent work; owner gate cannot be bypassed |
| P2 | Important reliability, completeness or maintainability work | Schedule by dependency and risk |
| P3 | Valuable improvement without a near-term blocking dependency | Keep visible and reassess |

Sequence by dependency and risk, not by the largest phase count. Work may run in parallel only where ownership and changed paths do not conflict.

## 4. Milestone model

A milestone must state its outcome, included Work Order IDs, prerequisites, exit gates, evidence owner and release relationship. A target date is optional and must remain unset until the owner or delivery lead schedules it; do not invent deadlines.

Initial governance milestone structure:

| Milestone | Outcome | Candidate Work Orders | Exit gate |
|---|---|---|---|
| MS-GOV-01 — Canonical portfolio baseline | One accepted four-product scope and linked G0–G12 authority | WO-GOV-001, WO-GOV-004 | ADR-0051 and baseline reviewed/merged; all active roadmaps and repository entry points agree |
| MS-GOV-02 — Repository trust controls | Protected integration branches and verified CI/review policy | WO-GOV-002, WO-GOV-003 | Effective rules read back for all four repositories; required checks identified and enforced |
| MS-GOV-03 — Requirements and architecture traceability | Requirements, use cases, ADRs and technical phases are traceable | WO-GOV-005, WO-GOV-006 | Stable IDs link requirement → owner → phase/Work Order → acceptance test/evidence |
| MS-GOV-04 — Operational and legal readiness | Release operations, recovery, cost and legal gates are explicit | WO-GOV-007, WO-GOV-008 | Owner/legal reviews recorded; backup restore and live environment acceptance evidenced where applicable |

These milestones are planning containers, not committed delivery dates or claims of completion. Re-sequence or split them when fresh repository evidence warrants it.

## 5. Release lifecycle and release gates

### 5.1 Candidate preparation

Every release candidate records:

- Release ID/version, owning product, environment and intended audience.
- Exact source commit(s), dependency/contract versions, migration identifiers and artifact hashes.
- Included and excluded Work Orders, PRs and unresolved G9 risks.
- Change classification: docs-only, code, schema/data, security, deployment/configuration, external integration, or device/runtime.
- Test matrix and exact-head workflow results.
- Security/privacy review, compatibility checks, backup/restore and rollback plan where relevant.
- Required owner approvals, provider/account/device gates, budget impact and operator on-call/ownership.

### 5.2 Acceptance gates

A release may proceed only when all applicable gates pass:

1. Scope and ownership are approved; dependencies are satisfied.
2. The exact candidate SHA has the required CI and targeted tests.
3. Independent review covers the changed files and integration boundary.
4. Security/privacy, authorization, secret handling and data-minimization checks pass where applicable.
5. Migrations, backup/restore and rollback are safe and documented where applicable.
6. Provider, physical-device, account, cost, legal or production gates have explicit owner evidence.
7. Release notes and operator instructions identify known limitations and residual risks.
8. The environment reports the intended version/source after release; post-release smoke/health evidence is recorded.

### 5.3 Owner-controlled actions

The following require explicit authorization by the appropriate owner and are not implied by code review or CI:

- Paid service/resource provisioning, plan sync, billing changes or paid provider activation.
- Production deployment, public release/tag, live Telegram webhook/message changes.
- Physical-device actions outside controlled acceptance.
- Destructive data/schema operations, secret rotation or access-policy changes.
- Legal declarations or assertions of licensing/privacy compliance.

A release can be technically ready and still remain BLOCKED by one of these external gates.

## 6. Progress and reporting

Report progress from evidence, not activity volume:

- Work Orders by lifecycle state and priority.
- Milestone exit criteria passed / total, with source links.
- P0/P1 risks open, mitigated, accepted or closed.
- Acceptance criteria passed / total on exact candidate SHAs.
- Dependencies blocked and the named next decision/action.
- Releases accepted, deployed, rolled back, or awaiting owner authorization.

Do not use a percentage complete unless the denominator is defined and each item has a verifiable state. Do not count drafted plans, open PRs, skipped workflows, or stale CI as completed work.

Every work batch reports the branch, exact SHA, PR, changed paths, checks and outcomes, unresolved risks and next gate in the format required by the [continuous execution standard](CONTINUOUS_EXECUTION_STANDARD.md).

## 7. Governance and maintenance

- Keep the active Work Order registry in [ECOSYSTEM_WORK_ORDERS.md](ECOSYSTEM_WORK_ORDERS.md).
- Keep risk IDs aligned with [ECOSYSTEM_RISK_DEPENDENCY_REGISTER.md](../governance/ECOSYSTEM_RISK_DEPENDENCY_REGISTER.md).
- Update milestone membership when Work Orders split, merge or are superseded.
- Review active milestones at each coordinated repository checkpoint and before releases.
- Preserve historical records; never rewrite a prior release result to make it appear current.
- Review this standard after a material change in portfolio structure, CI policy, release process, deployment topology or legal/operational responsibility.
