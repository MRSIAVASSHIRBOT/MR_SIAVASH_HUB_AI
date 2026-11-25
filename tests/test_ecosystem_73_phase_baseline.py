import re
from pathlib import Path

ROADMAP = Path(__file__).resolve().parents[1] / "docs" / "roadmap" / "ECOSYSTEM_73_PHASE_BASELINE.md"


def test_ecosystem_baseline_lists_each_phase_exactly_once() -> None:
    """Prevent phase identifiers from drifting or being silently dropped."""
    content = ROADMAP.read_text(encoding="utf-8")
    inventory = content.split("## 2. Phase inventory", 1)[1].split(
        "## 3. Parallelization policy", 1
    )[0]
    actual = re.findall(r"^\| `([A-Z]\d{1,2})` \|", inventory, re.MULTILINE)
    expected = {
        *(f"H{index}" for index in range(21)),
        *(f"E{index}" for index in range(15)),
        *(f"A{index}" for index in range(15)),
        *(f"B{index}" for index in range(12)),
        *(f"X{index}" for index in range(1, 11)),
    }

    assert len(actual) == 73
    assert len(actual) == len(set(actual))
    assert set(actual) == expected


def test_ecosystem_baseline_requires_integration_and_evidence_for_completion() -> None:
    """Ensure the baseline never equates phase presence or CI with completion."""
    content = ROADMAP.read_text(encoding="utf-8")

    assert "Definition of Done" in content
    assert "at least one dependent phase" in content.lower()
    assert "exact-head ci is green" in content.lower()
    assert "Runtime, Telegram, device, remote database and deployment acceptance" in content
    assert "This is a dated GitHub source/CI snapshot, not a deployment claim." in content
    assert "EL_AGENT" in content


def test_agent_companion_and_telegram_bridge_remain_distinct_products() -> None:
    """Keep E11's device companion separate from the EL_IR_BOT transport bridge."""
    content = ROADMAP.read_text(encoding="utf-8")
    adr = (
        ROADMAP.parents[1]
        / "architecture"
        / "decisions"
        / "ADR-0046-four-repository-scope-and-agent-bridge-boundary.md"
    ).read_text(encoding="utf-8")

    assert "ADR-0046" in content
    assert "EL_IR_BOT" in content
    assert "EL_AGENT remains a separate fifth ecosystem product" in content
    assert "EL_IR_BOT owns the Telegram edge transport" in adr
    assert "EL_AGENT is a separate Windows/Android companion" in adr
    assert "EL_AGENT features do not count as E11 completion" in adr
