"""Regression guards for the scheduled development agent's credential boundary."""
from __future__ import annotations

import json
import re
from pathlib import Path


def test_scheduled_agent_disables_shell_and_external_directory_tools() -> None:
    workflow = (
        Path(__file__).resolve().parents[1]
        / ".github"
        / "workflows"
        / "continuous-development.yml"
    ).read_text(encoding="utf-8")
    run_step = workflow.split(
        "      - name: Run one focused development cycle", maxsplit=1
    )[1].split("      - name: Detect and package changes", maxsplit=1)[0]

    config_match = re.search(
        r"(?m)^\s*OPENCODE_CONFIG_CONTENT:\s*'([^']+)'$",
        run_step,
    )
    assert config_match is not None, "OpenCode must receive explicit inline security policy"
    config = json.loads(config_match.group(1))

    assert config.get("tools", {}).get("bash") is False
    permissions = config.get("permission", {})
    assert permissions.get("bash") == "deny"
    assert permissions.get("external_directory") == "deny"
    assert "OPENROUTER_API_KEY:" in run_step
    assert "The OpenCode bash tool is disabled by policy" in run_step
    assert "do not attempt shell execution" in run_step


def test_agent_patch_validator_protects_opencode_project_configuration() -> None:
    workflow = (
        Path(__file__).resolve().parents[1]
        / ".github"
        / "workflows"
        / "continuous-development.yml"
    ).read_text(encoding="utf-8")

    assert 'b"opencode.json"' in workflow
    assert 'b"opencode.jsonc"' in workflow
    assert 'b"opencode.json5"' in workflow
    assert 'b".opencode/"' in workflow
    protected_control_paths = (
        "backend/mrhub/api/dependencies.py",
        "backend/mrhub/api/routes/agent_model_runs.py",
        "backend/mrhub/api/routes/agent_run.py",
        "backend/mrhub/api/routes/approvals.py",
        "backend/mrhub/api/routes/auth.py",
        "backend/mrhub/api/routes/jobs.py",
        "backend/mrhub/api/routes/policy.py",
        "backend/mrhub/api/routes/security_lab.py",
        "backend/mrhub/api/routes/tasks.py",
        "backend/mrhub/api/routes/tools.py",
        "backend/mrhub/config.py",
    )
    for path in protected_control_paths:
        assert f'b"{path}"' in workflow
    assert 'b"backend/mrhub/tools/"' in workflow
