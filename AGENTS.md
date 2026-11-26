# Repository Engineering Guidance

## Mission
Develop MR_SIAVASH_HUB_AI as a secure, local-first, modular AI workspace. Follow the architecture and roadmap already documented in this repository; do not invent a parallel architecture.

## Canonical portfolio scope
Use `docs/architecture/decisions/ADR-0047-four-product-ecosystem-scope-and-telegram-ownership.md` and `docs/GOVERNANCE_PRODUCT_STRATEGY_G0_G12.md` as the current portfolio authority. The active ecosystem has four products: HUB, EL_AI, EL_AGENT and MR_SIAVASH_AI. The ecosystem Telegram bot belongs inside EL_AI. `MR_SIAVASH_EL_IR_BOT` is out of scope; do not inspect, modify, migrate, deploy or create dependencies on it as part of this portfolio. The older 73-phase baseline and PAIOS execution roadmap are historical references for the superseded scope: do not execute B0–B11 or legacy-Bridge migration tasks from them. Any future scope change requires an explicit owner decision and a new ADR.

## Required workflow
1. Read the relevant README and architecture/security docs before making structural changes.
2. Inspect existing implementations and tests before editing. Prefer the smallest coherent change.
3. Add or update tests for behavior changes and run the narrowest relevant checks, then broader checks when practical.
4. Report exactly what changed, what commands/checks ran, their outcomes, and any unresolved risks.
5. Use a reviewable branch and pull request for code changes. Never bypass required checks or silently merge your own work.

## Security boundaries
- Never reveal, print, commit, or copy credentials, tokens, private keys, or environment secrets.
- Never add credential theft, phishing, malware, covert tracking, unauthorized access, or evasion capabilities.
- Do not enable arbitrary shell execution, unrestricted network access, or dynamic dependency installation at runtime.
- Keep least privilege, explicit policy checks, auditability, bounded timeouts/retries, and fail-closed behavior.
- External publishing, spending, destructive actions, and sensitive-data access must remain behind explicit approval gates.

## Engineering conventions
- Preserve the local-first modular-monolith design and stable module contracts.
- Keep provider routing explicit; never silently fall back from local to cloud inference.
- Use the existing migration system for schema changes; do not edit historical migrations.
- Do not introduce a new dependency or service unless the task needs it and the trade-off is documented.
- Do not claim tests passed unless they were actually run and their results were observed.
