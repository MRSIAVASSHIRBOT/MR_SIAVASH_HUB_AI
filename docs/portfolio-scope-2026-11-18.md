# Portfolio Scope Snapshot — 2026-11-18

## Active repositories
- `MR_SIAVASH_HUB_AI`: primary orchestration platform.
- `MR_SIAVASH_AI`: public site and Gateway.
- `Gshop`: online store.
- `MR_SIAVASH_EL_AI`: Telegram/public assistant with opt-in Hub boundaries.

## Discovery-only / Backlog
- `MR_SIAVASH_EL_IR_BOT`
- `MR_SIAVASH_IR_H_BOT`

These repositories remain discovery-only unless explicitly activated. PostZen publishing is a separate automation and is not part of repository maintenance.

## Release boundaries
- No Production deployment, DNS, secret, permission, payment, or D1 mutation is authorized by this document.
- Production changes require explicit owner approval.
- Changes should be developed on branches and merged through reviewed pull requests.

## Cross-project dependencies
- EL_AI may integrate with HUB_AI only through explicit opt-in contracts.
- Gshop inventory/payment changes require isolated D1 tests and a rollback plan.
- MR_SIAVASH_AI Gateway changes require source-parity verification against the active Worker before release.
