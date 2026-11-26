# Requirements and Use-Case Traceability — G2/G3

- **Baseline:** 2026-11-27
- **Portfolio authority:** [ADR-0051](../architecture/decisions/ADR-0051-four-product-ecosystem-scope-and-telegram-ownership.md)
- **Requirements source:** [ECOSYSTEM_REQUIREMENTS.md](../requirements/ECOSYSTEM_REQUIREMENTS.md)
- **Use-case source:** [USE_CASE_CATALOG.md](../architecture/USE_CASE_CATALOG.md)
- **Technical phase source:** [FOUR_PRODUCT_TECHNICAL_PHASES.md](../roadmap/FOUR_PRODUCT_TECHNICAL_PHASES.md)
- **Ownership source:** [OWNERSHIP_RACI.md](../governance/OWNERSHIP_RACI.md)
- **Status:** Initial traceability map; implementation/test-path confirmation and product-owner approval remain in progress

## 1. Purpose and semantics

This matrix connects each cross-product requirement to the owning technical phase(s), representative use cases and the verification method already specified by the requirement catalogue. It is a traceability index, not proof that a requirement is implemented or accepted.

- **Mapped:** requirement has an owning product, phase and use-case association.
- **Verification pending:** the requirement's named verification method still needs an exact test path, current source SHA and observed result.
- **Owner gate:** acceptance depends on an account, live environment, legal decision or physical device.
- **Done:** allowed only after the exact implementation and acceptance evidence is linked; no row is marked Done by this initial mapping.

## 2. Functional requirement traceability

| Requirement | Owner | Technical phase(s) | Use case(s) | Required verification (from G2 catalogue) | Evidence state |
|---|---|---|---|---|---|
| FR-HUB-01 | HUB | H2, H3 | UC-01 | Work Order schema/API tests; malformed and ambiguous input cases | Mapped / verification pending |
| FR-HUB-02 | HUB | H1, H7, H8, H16 | UC-02 | Worker integration, restart/recovery and cancellation tests | Mapped / verification pending |
| FR-HUB-03 | HUB | H11, X2 | UC-01, UC-02, UC-07, UC-10 | Negative authorization matrix; expiry/revocation and replay tests | Mapped / verification pending |
| FR-HUB-04 | HUB | H9, H11, H16 | UC-02, UC-11 | Owner isolation, provenance, export/deletion and authorization tests | Mapped / verification pending |
| FR-HUB-05 | HUB | H14, X6 | UC-02, UC-11 | Adapter contract tests; prove no hidden local-to-cloud fallback | Mapped / verification pending |
| FR-HUB-06 | HUB | H10, H7, H8, H12 | UC-02, UC-12 | Merged evaluator contract tests: `tests/test_work_order_evidence_contract.py` (PR #640); merged owner-scoped API and tests: `backend/mrhub/api/routes/agent.py`, `tests/test_agent_work_order_evidence_api.py` (PR #641; merge `4f684b8a`) | Partial implementation evidence / verification pending; production verifiers and E8 consumer contract remain open |
| FR-HUB-07 | HUB | H15, H17, H18 | UC-12 | Schema/log redaction and operator authorization tests | Mapped / verification pending |
| FR-ELAI-01 | EL_AI | E2, E13, X8 | UC-03, UC-08 | Runtime routing tests proving private context never enters public requests/replies | Mapped / verification pending |
| FR-ELAI-02 | EL_AI | E10, E14 | UC-03 | Outbound invalid-Unicode regression tests in `tests/test_telegram_api.py` (PR #148 merged); full Telegram adapter integration and test-bot acceptance remain separate gates | Partial implementation evidence / owner gate |
| FR-ELAI-03 | EL_AI + HUB | E1, E5, E13, H11, X2 | UC-03, UC-07 | Pairing, expiry, scope, revocation, replay and client-isolation tests | Mapped / verification pending |
| FR-ELAI-04 | EL_AI | E10, H8, X9 | UC-04 | State-machine and failure-injection tests; unknown delivery distinct from confirmed delivery | Mapped / verification pending |
| FR-ELAI-05 | EL_AI | E10, E13 | UC-03 | Outbound text/caption Unicode validation in `tests/test_telegram_api.py` (PR #148 merged); input-envelope size/fuzz and media-bound tests remain open | Partial implementation evidence / verification pending |
| FR-ELAI-06 | EL_AI | E8, E12, H10 | UC-01, UC-03 | Command authorization and lifecycle integration tests | Mapped / verification pending |
| FR-ELAI-07 | EL_AI | E1, E2, E13 | UC-03 | Cross-actor negative tests; Business routes remain disabled until acceptance | Mapped / owner gate |
| FR-AGENT-01 | EL_AGENT | D0, D5, D7, D8 | UC-06 | Offline acceptance with adapters disabled and no network access | Mapped / device gate |
| FR-AGENT-02 | EL_AGENT | D3, D4 | UC-05 | Deny-by-default policy tests, invalid-action and timeout tests | Mapped / verification pending |
| FR-AGENT-03 | EL_AGENT | D3, D6 | UC-05 | Prompt-injection/action-boundary tests and forged proposal tests | Mapped / verification pending |
| FR-AGENT-04 | EL_AGENT | D4 | UC-05, UC-06 | Restart, duplicate-submission, lease/fencing and unknown-outcome tests | Mapped / verification pending |
| FR-AGENT-05 | EL_AGENT | D5, D9 | UC-06 | Provider contract tests; offline and consented remote tests | Mapped / verification pending |
| FR-AGENT-06 | EL_AGENT + HUB | D11, H11, X2, X9 | UC-07 | Pair/revoke/expiry/contract tests plus standalone-with-HUB-disabled test | Mapped / verification pending |
| FR-AGENT-07 | EL_AGENT | D3, D12 | UC-05 | Confirmation bypass and stale approval tests | Mapped / verification pending |
| FR-WEB-01 | MR_SIAVASH_AI | A0, A1, A2 | UC-09 | Browser journeys, viewport matrix, accessibility checks | Mapped / verification pending |
| FR-WEB-02 | MR_SIAVASH_AI | A3, A6, A13 | UC-08, UC-12 | Snapshot schema and UI contract tests; no private service inference | Mapped / verification pending |
| FR-WEB-03 | MR_SIAVASH_AI | A6, A7, X2, X8 | UC-08 | Data minimization, prompt-boundary and public/private isolation tests | Mapped / verification pending |
| FR-WEB-04 | MR_SIAVASH_AI | A4, A12 | UC-09 | Storage migration, corruption and recovery tests | Mapped / verification pending |
| FR-WEB-05 | MR_SIAVASH_AI | A8, A9, A12, H11 | UC-10 | Auth, consent, retention, audit and deletion tests | Mapped / verification pending |
| FR-WEB-06 | MR_SIAVASH_AI | A3, A10, A13 | UC-08, UC-09, UC-10 | Content/registry validation and UX acceptance | Mapped / verification pending |
| FR-X-01 | Shared / HUB | X1, X2, H11, H12 | UC-01, UC-03, UC-07, UC-08 | Producer/consumer contract CI, unsupported-version tests | Mapped / verification pending |
| FR-X-02 | All products | X1, X2, X8 | UC-02, UC-07, UC-08 | Architecture fitness tests and repository dependency scan | Mapped / verification pending |
| FR-X-03 | All products | X7, X9, H15 | UC-02, UC-03, UC-04, UC-07 | Contract tests and trace propagation tests | Mapped / verification pending |
| FR-X-04 | All products | X2, X8, X9 | UC-04, UC-06, UC-07 | Revocation, timeout and offline-mode tests | Mapped / verification pending |

## 3. Non-functional requirement traceability

| Requirement | Owning assurance area | Technical phase(s) | Verification / acceptance evidence | State |
|---|---|---|---|---|
| NFR-SEC-01 | All product owners + Security Assurance | H11, E13, D3, A6/A8, X2/X8 | Negative authorization suites across actor, scope and resource ownership | Mapped / verification pending |
| NFR-SEC-02 | All maintainers | H15, E13, D2/D13, A6/A8, X8 | EL_AGENT local token-file format/size/regular-file/symlink tests in `tests/test_security.py` (PR #33 merged); cross-product secret scan, redacted log fixtures and browser/static artifact scan remain | Partial implementation evidence / verification pending |
| NFR-SEC-03 | HUB + EL_AI + EL_AGENT | H11, H14, E3/E13, D3/D6, X8 | Prompt-injection and tool-boundary tests; deterministic authorization | Mapped / verification pending |
| NFR-PRIV-01 | Product data owners | H9/H11, E2/E13, D10, A5/A6, X3/X8 | Data-flow review, cross-actor negative tests and retention evidence | Mapped / verification pending |
| NFR-REL-01 | Runtime owners | H1/H7/H8, E10, D4, X9 | Fault injection, bounded retries, idempotency, restart and unknown-outcome tests | Mapped / verification pending |
| NFR-OBS-01 | Product operations owners | H15, E13, D13, A8, X7 | Correlation/health checks and redaction tests | Mapped / verification pending |
| NFR-COST-01 | Product owners + ecosystem owner | H14, E9, D5, A6, X6 | Opt-in configuration, quota/cost evidence and no silent paid fallback | Mapped / owner review |
| NFR-PORT-01 | Architecture owners | H6/H14, E9, D5, A6, X1/X6 | Adapter substitution and contract compatibility tests | Mapped / verification pending |
| NFR-PERF-01 | Runtime owners | H7/H18, E10, D4/D9, A6/A13 | Payload/concurrency/timeout/resource bounds and representative measurements | Mapped / verification pending |
| NFR-ACC-01 | Website owner | A1/A2/A13 | Keyboard, semantic, contrast and responsive manual/automated audit | Mapped / verification pending |
| NFR-I18N-01 | EL_AI + Website owners | E2/E3, A1/A2/A4 | Persian/RTL and mixed-script behavior tests | Mapped / verification pending |
| NFR-MAINT-01 | Maintainers across four products | H19, E14, D13/D14, A14, X10 | Reproducible dependency/build checks, ADR traceability and contribution/release audit | Mapped / verification pending |
| NFR-REC-01 | Operations owners | H8/H16/H19, E14, D4/D13/D14, A14, X10 | Isolated restore, rollback and recovery rehearsal evidence | Mapped / owner gate |

## 4. Use-case to phase and requirement coverage

| Use case | Primary technical phase(s) | Key requirement(s) | Main exception/negative gate |
|---|---|---|---|
| UC-01 Goal to Work Order | H2/H3, E3/E4, X1 | FR-HUB-01, FR-HUB-03, FR-ELAI-06, FR-X-01 | Ambiguous input, unsupported intent, no execution before approval |
| UC-02 Durable workflow execution | H1/H7/H8/H10/H11/H16 | FR-HUB-02/03/04/06, NFR-REL-01 | Restart, cancellation, revoked grant, stale/conflicting evidence |
| UC-03 Owner Telegram conversation | E1/E2/E3/E5/E10/E13, H11/H12 | FR-ELAI-01/02/03/05/07, FR-X-01 | Unknown Telegram identity, public/private leakage, rate limit, unknown send |
| UC-04 Ambiguous Telegram delivery | E10, H8, X9 | FR-ELAI-04, FR-X-03/04 | No blind replay; unknown stays unknown without trusted reconciliation |
| UC-05 Approved local device action | D3/D4/D6/D7/D8/D12 | FR-AGENT-02/03/04/07 | Invalid action, missing confirmation, timeout, untrusted proposal |
| UC-06 Standalone/offline EL_AGENT | D0/D5/D7/D8/D9 | FR-AGENT-01/04/05 | HUB/network/cloud disabled; no hidden fallback or data upload |
| UC-07 Optional HUB/EL_AGENT pairing | H11/H12, D11, X1/X2/X9 | FR-AGENT-06, FR-ELAI-03, FR-X-01/04 | Pairing expiry/revoke, device offline, local policy denial |
| UC-08 Public Website assistant | A5/A6/A7, X2/X8 | FR-WEB-02/03, FR-ELAI-01, NFR-PRIV-01 | Consent absent, private owner context requested, malformed source |
| UC-09 Learning/local workspace | A1/A2/A4/A12 | FR-WEB-01/04, NFR-ACC-01/NFR-I18N-01 | Corrupt local storage, invalid import, quota exhaustion |
| UC-10 Content/support/admin | A8/A9/A12, H11 | FR-WEB-05/06 | Missing consent, revoked role, duplicate publish, rollback failure |
| UC-11 Capability registration/invocation | H6/H11/H12/H14 | FR-HUB-04/05, NFR-SEC-01/03 | Unknown version, permission escalation, malformed output |
| UC-12 Portfolio/evidence review | H10/H15/H17/H19, X7/X10 | FR-HUB-06/07, FR-WEB-02 | Stale evidence, mismatched source SHA, CI/live/device/legal conflation |

## 5. Traceability gaps and required follow-up

1. **Test-path linkage:** the G2 catalogue currently names verification methods but does not consistently link each row to exact test file(s), test identifiers and exact-main result. Add those links only after source-level verification.
2. **Sequence diagrams:** G3 has primary and exception flows for 12 use cases, but detailed sequence diagrams and per-product state transitions remain implementation follow-ups.
3. **Owner confirmation:** actor/audience expansion, named requirement owners and numeric SLO targets require owner review; no values are invented here.
4. **Cross-repository coverage:** producer and consumer tests must both be linked for shared contracts X1–X10; provider-side tests alone do not complete consumer acceptance.
5. **Evidence freshness:** every verification link must state the commit SHA and run URL; older CI or runtime evidence is historical, not current acceptance.

## 5.1 Merged implementation evidence — 2026-11-27

| Requirement / slice | Owning product | Source commit / test path | Evidence boundary |
|---|---|---|---|
| D2 local API token file safety (subset of NFR-SEC-02) | EL_AGENT | PR #33 merge `de8007bd3a32e636a589d8afb7806725ac55d414`; `src/el_agent/security.py`, `tests/test_security.py` | Linux/Windows Python 3.11/3.12 exact-head tests passed; no Android Keystore or physical-device acceptance claimed |
| E10 outbound Unicode input validation (subset of FR-ELAI-02/05) | EL_AI | PR #148 merge `bb7239c46556f6fa68841e48740507f31ba58e6c`; `src/el_ai/telegram/api.py`, `tests/test_telegram_api.py` | Python 3.11/3.12 and post-merge security/supply-chain checks passed; no live Telegram E2E claimed |
| H10 deterministic evaluator contract (FR-HUB-06) | HUB | PR #640 merge `47a8e4fee206ef72e928fa3ce381a52ee4324921`; `tests/test_work_order_evidence_contract.py` | Exact PR-head checks passed; post-merge main validation was separately tracked |
| H10 owner-scoped API (FR-HUB-06) | HUB | PR #641 merged as `4f684b8a8494ffe263db6769b312f884cd6df311`; `backend/mrhub/api/routes/agent.py`, `tests/test_agent_work_order_evidence_api.py` | Exact PR-head checks passed; production registry intentionally has no verifier adapters yet, so untrusted evidence remains review_required |

These slices update evidence state only. They do not mark the parent requirement or phase Done.

## 6. G2/G3 exit rule

G2/G3 can advance only when each mandatory requirement/use case has:

- an accountable product/role and stable identifier;
- one or more owning technical phases and linked Work Orders;
- observable acceptance criteria and negative/failure cases;
- exact test file/test IDs or a documented manual acceptance protocol;
- exact commit SHA and verification run/result;
- explicit owner/environment gate where applicable.

This map completes an initial traceability layer; G2 and G3 remain IN_PROGRESS until the implementation and acceptance links are audited.
