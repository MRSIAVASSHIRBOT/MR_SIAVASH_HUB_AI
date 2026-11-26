# Ecosystem Work Order Registry — G11

- **Baseline:** 2026-11-27
- **Portfolio authority:** [ADR-0051](../architecture/decisions/ADR-0051-four-product-ecosystem-scope-and-telegram-ownership.md)
- **Delivery policy:** [Delivery Management Standard](DELIVERY_MANAGEMENT_STANDARD.md)
- **Reusable schema:** [Work Order Template](WORK_ORDER_TEMPLATE.md)
- **Risk authority:** [G9 Risk & Dependency Register](../governance/ECOSYSTEM_RISK_DEPENDENCY_REGISTER.md)
- **Status:** Initial governance backlog; statuses are evidence states, not estimates of effort

## 1. Active governance Work Orders

| ID | Phase | Outcome | Owning repository / accountable role | Priority | Status | Dependencies / risks | Acceptance evidence |
|---|---|---|---|---|---|---|---|
| WO-GOV-001 | G0/G1/G4/G8 | Establish and accept the four-product scope, portfolio roles and ADR-0051 | HUB / ecosystem owner + architecture | P1 | REVIEW | D-01; R-02 | Reviewed/merged ADR-0051 and G0–G12 baseline; current repository entry points and active roadmaps agree |
| WO-GOV-002 | G7 | Enforce protected main branches and required review/check policy | All four repositories / repository owner-admin | P1 | BLOCKED | D-02; R-01 | Effective rules read back from GitHub for HUB, EL_AI, EL_AGENT and Website; required checks run on exact PR heads |
| WO-GOV-003 | G6 | Complete per-repository baseline inventory at current exact main SHAs | Each repository / product maintainer | P1 | IN_PROGRESS | D-09; R-03, R-10, R-11 | Initial [G6 inventory](../governance/REPOSITORY_BASELINE_G6.md) exists; remaining recursive module/config/lockfile inventory, exact source SHAs and live/deployment freshness must be evidenced per repo |
| WO-GOV-004 | G2/G3 | Link requirements and use cases to owning product, Work Order and executable verification | HUB coordinates / product owners | P2 | IN_PROGRESS | R-12, R-13 | Initial [G2/G3 traceability map](../traceability/REQUIREMENT_USECASE_TRACEABILITY.md) covers all catalogue IDs; exact source/test IDs, Work Order links and current-SHA results remain to be reconciled |
| WO-GOV-005 | G8 | Establish ADR quality, unique identifier traceability and cross-product contract decision control | HUB / architecture owner | P1 | IN_PROGRESS | D-03, D-09; R-04, R-14 | Shared [ADR template](../architecture/decisions/ADR_TEMPLATE.md) and [ADR index](../architecture/ADR_INDEX.md) adopted; current portfolio decision ADR-0051 has a unique ID; collision aliases are inventoried; no implementation precedes required decision |
| WO-GOV-006 | G9 | Operate the centralized portfolio risk/dependency register | HUB / delivery coordinator + product risk owners | P1 | IN_PROGRESS | D-01…D-10; R-12 | Every active P0/P1 risk has accountable owner, mitigation, dependency, evidence, status and explicit accept/close decision |
| WO-GOV-007 | G11 | Adopt Work Order, milestone, release and evidence lifecycle | HUB / delivery coordinator + product maintainers | P1 | IN_PROGRESS | R-01, R-03, R-11, R-12 | Template and delivery standard adopted; linked Work Orders and milestones maintained; exact-SHA evidence and owner gates recorded |
| WO-GOV-008 | G12 | Complete licensing, privacy, operational ownership, backup and incident readiness review | Ecosystem owner + qualified adviser + product operators | P1 | OWNER GATE | D-04…D-08; R-05…R-09 | [G12 readiness checklist](../governance/LEGAL_OPERATIONAL_READINESS_CHECKLIST.md) completed with written legal/privacy review, named operators, restore drill, incident/rollback plan and explicit cost/live-service decisions |
| WO-GOV-010 | G3 | Reconcile logical use-case sequences against actual product APIs, schemas and state transitions | HUB coordinates / owning product maintainers | P2 | IN_PROGRESS | R-04, R-13; D-03, D-09 | [G3 sequence diagrams](../architecture/USE_CASE_SEQUENCE_DIAGRAMS.md) reviewed by each product; actual API/module names, denial/failure paths and executable test references linked |
| WO-GOV-011 | G7 | Align CI and engineering standards across Python, Android and Website stacks | HUB coordinates / product maintainers + Security Assurance | P1 | IN_PROGRESS | R-01, R-10, R-15 | [G7 standards matrix](../governance/ENGINEERING_STANDARDS_MATRIX_G7.md) reviewed; full workflow inventory, immutable action pins, lint/test/security gates and required-check evidence reconciled per exact main SHA |
| WO-GOV-009 | G8 | Reconcile duplicate historical ADR identifiers with a backward-compatible alias/index plan | HUB / architecture owner + product maintainers | P2 | PROPOSED | R-14 | Complete inbound-link inventory; decide canonical namespace; preserve historical files and citations; provide aliases/redirect notes and merge a separately reviewed compatibility change |

## 2. Work Order operating rules

1. The ID is stable for the lifetime of the item. If scope becomes materially different, supersede it and create a linked Work Order.
2. Exactly one repository is the implementation owner. Cross-repository work is represented by linked consumer/provider Work Orders and a shared integration identifier.
3. `READY` means dependencies, ownership and acceptance criteria are sufficiently clear to start. An owner gate cannot be treated as READY.
4. `IN_PROGRESS` requires an active branch or a recorded non-code action with a responsible owner and next evidence step.
5. `REVIEW` means the PR/artifact is available and checks are being evaluated; it does not mean accepted.
6. `ACCEPTED` requires all acceptance criteria and independent review evidence. `RELEASED` additionally requires intended-environment verification.
7. Status updates must include date, exact SHA/PR or owner decision, evidence links, and any changed dependency.
8. Do not close another contributor's work, rewrite their branch, or duplicate overlapping paths without coordination.
9. Do not claim that a G phase is DONE merely because its first Work Order or documentation artifact exists.

## 3. Next sequencing

1. Resolve WO-GOV-001 through explicit review of the existing G0–G12 PR; no parallel governance baseline should be created.
2. Keep WO-GOV-002 blocked until repository owner/admin applies and verifies the branch rules.
3. Run WO-GOV-003 against fresh exact-main snapshots, then update G6 and the dependency pins from observed facts.
4. Continue WO-GOV-004 and WO-GOV-010 against product requirements, sequence flows, APIs and tests; create consumer-side acceptance work where required.
5. Continue WO-GOV-005/009 for ADR index and historical ID compatibility; keep the existing accepted decisions intact.
6. Continue WO-GOV-011 for G7 workflow and standards parity.
7. Maintain WO-GOV-006/007 as ongoing controls; reconcile G9 risks and G11 milestones on every checkpoint.
8. Keep WO-GOV-008 behind the owner/legal/operations gate; complete the [G12 checklist](../governance/LEGAL_OPERATIONAL_READINESS_CHECKLIST.md) with accountable reviewers and do not invent legal or production acceptance.

## 4. Status change log

| Date | Work Order | Change | Evidence |
|---|---|---|---|
| 2026-11-27 | WO-GOV-001 | Existing four-product/G0–G12 baseline identified in PR #639; retained in review rather than duplicated | [PR #639](https://github.com/MRSIAVASSHIRBOT/MR_SIAVASH_HUB_AI/pull/639) |
| 2026-11-27 | WO-GOV-006/007 | Added canonical G9 register and G11 delivery controls/templates as reviewable artifacts | Current branch PR #639; exact Actions evidence pending |
| 2026-11-27 | WO-GOV-003/004/010/011 | Added G6 baseline, G2/G3 traceability map, G3 logical sequence diagrams and G7 standards matrix; follow-up evidence reconciliation remains in progress | Current branch PR #639; exact-head checks pending |
