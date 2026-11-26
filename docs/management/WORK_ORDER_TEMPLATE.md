# Work Order Template — G11

Use one Work Order per bounded outcome. Copy this file into the relevant repository's management area or create a tracked issue using the same fields. Do not create duplicate work when an equivalent issue, PR, or owner-assigned task already exists.

## 1. Identity and ownership

- **Work Order ID:** `WO-<PRODUCT>-<NNN>`
- **Title:**
- **Governance / technical phase:** `Gx`, `Hx`, `Ex`, `Dx`, `Ax`, or `Xx`
- **Owning product/repository:**
- **Accountable role:**
- **Implementer:**
- **Independent reviewer / QA:**
- **Priority:** P0 / P1 / P2 / P3
- **Status:** PROPOSED / READY / IN_PROGRESS / BLOCKED / REVIEW / ACCEPTED / RELEASED / CANCELLED
- **Created / last reviewed:**
- **Target milestone:** 
- **Related issue / PR / ADR:**

## 2. Outcome

**Problem / user or operational need**

Describe the observed problem and who is affected. Link evidence rather than using unsupported assumptions.

**Expected outcome**

State the observable capability or decision that will exist after acceptance.

**Success measure**

Name the metric or binary acceptance condition, its source, and the measurement window. Do not invent numeric targets without a baseline and owner approval.

## 3. Scope control

**In scope**
- 

**Explicitly out of scope**
- 

**Affected paths, APIs, schemas, workflows or products**
- 

**Cross-product contract**
- Provider / owning authority:
- Consumer(s):
- Contract version:
- Data classification and permitted fields:
- Authentication / authorization scope:
- Compatibility and deprecation behavior:

## 4. Dependencies and risk

- **Prerequisite Work Orders:**
- **External dependencies:**
- **Environment / account / device gates:**
- **Relevant risk IDs from G9:**
- **Security and privacy impact:**
- **Data migration / backup impact:**
- **Cost / billing impact:**
- **Rollback / disable strategy:**

If a dependency is owner-controlled, mark the Work Order BLOCKED or OWNER GATE until the required evidence is attached. Do not bypass the gate by assuming approval.

## 5. Acceptance criteria

Write observable, independently verifiable statements. Each criterion must have a corresponding verification method and evidence location.

| ID | Acceptance criterion | Verification method | Evidence / exact SHA | Result |
|---|---|---|---|---|
| AC-01 |  |  |  | NOT RUN |
| AC-02 |  |  |  | NOT RUN |

Acceptance criteria must cover applicable invalid input, negative authorization, failure/retry, privacy/logging, compatibility, and recovery cases—not only the happy path.

## 6. Implementation and verification plan

- **Design / ADR required:** Yes / No; link:
- **Implementation steps:**
  1. 
- **Tests to add or update:**
- **Commands and workflow checks:**
- **Manual / browser / device / provider acceptance:**
- **Documentation and operator changes:**

For every reported PASS, record the exact tested commit SHA, check name, run URL, and result. Mark skipped, unavailable, cancelled, or unexecuted checks separately; never infer success from another SHA.

## 7. Delivery record

- **Working branch:**
- **Pull request:**
- **Changed files:**
- **Review outcome:**
- **Merge commit / main SHA:**
- **Release tag / version (if applicable):**
- **Post-merge verification:**
- **Operational evidence:**
- **Residual risks / follow-up Work Orders:**

## 8. Closure decision

- [ ] All acceptance criteria passed on the exact candidate.
- [ ] Required independent review completed.
- [ ] Security/privacy and compatibility checks completed where applicable.
- [ ] Documentation and operator instructions updated.
- [ ] Required migration, backup, rollback and recovery evidence recorded.
- [ ] Owner-controlled gates satisfied and evidence attached.
- [ ] Post-merge exact-main verification completed.

**Decision:** ACCEPTED / NOT ACCEPTED / BLOCKED

**Decision owner and role:**

**Date and evidence:**

An open PR, a successful partial workflow, or a drafted artifact is not sufficient for ACCEPTED or RELEASED.
