"""Regression tests for the scheduled OpenCode agent's tool boundary."""
from __future__ import annotations

import json
import re
from pathlib import Path


WORKFLOW = (
    Path(__file__).resolve().parents[1]
    / ".github"
    / "workflows"
    / "continuous-development.yml"
)


def _config() -> dict[str, object]:
    workflow = WORKFLOW.read_text(encoding="utf-8")
    match = re.search(
        r"(?m)^\s*OPENCODE_CONFIG_CONTENT:\s*'([^']+)'$",
        workflow,
    )
    assert match is not None, "scheduled agent must receive inline security policy"
    return json.loads(match.group(1))


def _assert_default_deny(policy: object) -> None:
    assert isinstance(policy, dict)
    assert policy.get("*") == "deny"
    for tool in ("read", "edit", "glob", "grep"):
        assert policy.get(tool) == "allow"
    for tool in (
        "bash",
        "task",
        "skill",
        "webfetch",
        "websearch",
        "lsp",
        "external_directory",
    ):
        assert policy.get(tool) == "deny"


def test_scheduled_agent_uses_default_deny_tool_policy() -> None:
    config = _config()

    _assert_default_deny(config.get("permission"))
    agents = config.get("agent")
    assert isinstance(agents, dict)
    build = agents.get("build")
    assert isinstance(build, dict)
    _assert_default_deny(build.get("permission"))

    assert config.get("tools", {}).get("bash") is False
    assert config.get("lsp") is False
    assert config.get("mcp") == {}


def test_effective_policy_is_checked_without_provider_credentials() -> None:
    workflow = WORKFLOW.read_text(encoding="utf-8")
    verification = workflow.split(
        "      - name: Verify effective OpenCode tool policy", maxsplit=1
    )[1].split("      - name: Run one focused development cycle", maxsplit=1)[0]
    run_step = workflow.split(
        "      - name: Run one focused development cycle", maxsplit=1
    )[1].split("      - name: Detect and package changes", maxsplit=1)[0]

    assert "opencode --pure debug config" in verification
    assert "json.loads" in verification
    assert "OPENROUTER_API_KEY" not in verification
    assert "opencode --pure run" in run_step
    assert "OPENROUTER_API_KEY: ${{ secrets.MR_SIAVASH_HUB_AI }}" in run_step
    assert "Add/update tests, but do not attempt to execute them." in run_step
    assert workflow.count("OPENROUTER_API_KEY: ${{ secrets.MR_SIAVASH_HUB_AI }}") == 1


def test_scheduled_publisher_uses_immutable_artifact_action_pins() -> None:
    workflow = WORKFLOW.read_text(encoding="utf-8")
    assert (
        "actions/upload-artifact@cf430e030ddbb5b0abf93d22962f4752f3646cd9"
        in workflow
    )
    assert (
        "actions/download-artifact@9000827ccba6bdab643e8b6fd33ac0654aef8333"
        in workflow
    )
