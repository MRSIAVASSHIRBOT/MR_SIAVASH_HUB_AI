# Release Evidence Record

Copy this template into the release record for each candidate. Keep URLs to the exact CI runs and record the candidate SHA those runs validated.

## Candidate
- Release/version:
- Candidate commit SHA:
- Release date:
- Release owner:
- Intended environment:

## Required CI checks
| Check | Run URL | Commit SHA | Result |
|---|---|---|---|
| CI Python 3.11 | | | |
| CI Python 3.12 | | | |
| Backend CI | | | |
| Windows wheel smoke 3.11 | | | |
| Windows wheel smoke 3.12 | | | |
| Windows launcher validation | | | |
| Video render Linux/Windows | | | |
| Defensive Python scan | | | |
| Workflow security audit | | | |

## Review findings
- Test failures/flakes and disposition:
- Coverage report reviewed (critical modules / gaps):
- Dependency audit findings and disposition:
- Security findings and disposition:
- API contract and operational smoke evidence:

## Database / recovery
- Migration/schema version:
- Backup location/identifier (avoid credentials or sensitive paths):
- Restore test evidence:
- Rollback target and known limitations:

## Deployment
- Configuration verified:
- Health endpoint:
- Readiness endpoint:
- Worker heartbeat:
- UI/API smoke:
- Logs/metrics reviewed:
- Observation window and signals:

## Decision
- [ ] Release
- [ ] Hold

- Decision rationale:
- Blocking items (if hold):
- Follow-up issues/PRs:
