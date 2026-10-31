# MR_SIAVASH_HUB_AI

An integrated, modular AI workspace designed for local-first and hybrid execution.

## Product direction

MR_SIAVASH_HUB_AI combines a shared intelligence core with specialist capabilities for agents, memory, workflows, developer assistance, content production, integrations, and defensive security.

The initial release is designed for one primary user while keeping clean boundaries for future multi-user support.

## Engineering principles

- **Local-first, hybrid-capable:** run feasible workloads locally and route heavier tasks to explicitly configured providers.
- **Modular monolith first:** maintain clear module contracts without introducing distributed-system overhead prematurely.
- **Secure by default:** least privilege, explicit tool grants, secret isolation, audit trails, and approval gates for sensitive actions.
- **Observable and recoverable:** jobs expose status, logs, cancellation, bounded retries, and recoverable checkpoints where appropriate.
- **Cost-aware:** prefer free and open-source components; external paid services remain opt-in.
- **Testable:** unit, integration, end-to-end, and security checks are part of the delivery process.

## Quick start

Requires Python 3.11 or newer.

```powershell
py -3.11 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -e ".[dev]"
uvicorn mrhub.main:app --reload
```

OpenAPI documentation is available at `http://127.0.0.1:8000/docs`.

Run tests:

```powershell
pytest
```

## Initial capability domains

1. AI Core and Model Router
2. Agent Orchestrator
3. Memory and Retrieval
4. Workflow and Job Engine
5. Tool and Plugin Registry
6. NEXUS Developer Agent
7. Social Automation and Telegram Integration
8. Video Engine
9. Discovery and Research
10. Defensive Cybersecurity Lab
11. Developer Console

These are product domains, not separate competing backends. Shared infrastructure is implemented once and exposed through stable interfaces.

## Safety and trust boundaries

The platform is intended for legitimate personal productivity, software development, content creation, and defensive/authorized security work. It will not include credential theft, phishing kits, covert tracking, malware or payload generation, unauthorized access, or evasion features.

External publishing, spending, destructive operations, access to sensitive data, and other high-impact actions require explicit policy checks and, where configured, user approval.

## Current status

The repository contains the architecture baseline and the first API/database slice. The task endpoints currently record and inspect task metadata only; they do not execute agents, models, or external tools.

## Documentation

- `docs/architecture/overview.md` — system architecture
- `docs/architecture/module-boundaries.md` — module ownership and contracts
- `docs/security/threat-model.md` — trust boundaries and security controls
- `docs/roadmap/implementation-plan.md` — staged delivery plan

## License

License selection is pending. No license grant should be inferred until a license file is added.
