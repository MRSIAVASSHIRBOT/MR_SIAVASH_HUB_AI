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
| WO-GOV-003 | G6 | Complete per-repository baseline inventory at current exact main SHAs | Each repository / product maintainer | P1 | READY | D-09; R-03, R-10, R-11 | Code/module map, manifests/lockfiles, config, tests, CI, secrets boundary, deployment and live-evidence distinction recorded per repo |
| WO-GOV-004 | G2/G3 | Link requirements and use cases to owning product, Work Order and executable verification | HUB coordinates / product owners | P2 | READY | R-12, R-13 | Stable requirement/use-case IDs map to owner → implementation path → test/acceptance evidence; unimplemented requirements remain explicit |
| WO-GOV-005 | G8 | Establish ADR quality and cross-product contract decision traceability | HUB / architecture owner | P1 | IN_PROGRESS | D-03, D-09; R-04, R-14 | Shared [ADR template](../architecture/decisions/ADR_TEMPLATE.md) adopted; decision index includes status/supersession, owner, security/data-flow impact and verification; no implementation precedes required decision |
| WO-GOV-006 | G9 | Operate the centralized portfolio risk/dependency register | HUB / delivery coordinator + product risk owners | P1 | IN_PROGRESS | D-01…D-10; R-12 | Every active P0/P1 risk has accountable owner, mitigation, dependency, evidence, status and explicit accept/close decision |
| WO-GOV-007 | G11 | Adopt Work Order, milestone, release and evidence lifecycle | HUB / delivery coordinator + product maintainers | P1 | IN_PROGRESS | R-01, R-03, R-11, R-12 | Template and delivery standard adopted; linked Work Orders and milestones maintained; exact-SHA evidence and owner gates recorded |
| WO-GOV-008 | G12 | Complete licensing, privacy, operational ownership, backup and incident readiness review | Ecosystem owner + qualified adviser + product operators | P1 | OWNER GATE | D-04…D-08; R-05…R-09 | [G12 readiness checklist](../governance/LEGAL_OPERATIONAL_READINESS_CHECKLIST.md) completed with written legal/privacy review, named operators, restore drill, incident/rollback plan and explicit cost/live-service decisions |

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
4. Execute WO-GOV-004/005 against current product requirements, APIs and tests; create consumer-side acceptance work where required.
5. Maintain WO-GOV-006/007 as ongoing controls; reconcile G9 risks and G11 milestones on every checkpoint.
6. Keep WO-GOV-008 behind the owner/legal/operations gate; complete the [G12 checklist](../governance/LEGAL_OPERATIONAL_READINESS_CHECKLIST.md) with accountable reviewers and do not invent legal or production acceptance.

## 4. Status change log

| Date | Work Order | Change | Evidence |
|---|---|---|---|
| 2026-11-27 | WO-GOV-001 | Existing four-product/G0–G12 baseline identified in PR #639; retained in review rather than duplicated | [PR #639](https://github.com/MRSIAVASSHIRBOT/MR_SIAVASH_HUB_AI/pull/639) |
| 2026-11-27 | WO-GOV-006/007 | Added canonical G9 register and G11 delivery controls/templates as reviewable artifacts | Current branch PR #639; exact Actions evidence pending |
