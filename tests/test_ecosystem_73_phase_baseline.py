import re
from pathlib import Path

ROADMAP = Path(__file__).resolve().parents[1] / "docs" / "roadmap" / "ECOSYSTEM_73_PHASE_BASELINE.md"


def test_ecosystem_baseline_lists_each_phase_exactly_once() -> None:
    """Prevent phase identifiers from drifting or being silently dropped."""
    content = ROADMAP.read_text(encoding="utf-8")
    actual = re.findall(r"^\| `([A-Z]\d{1,2})` \|", content, re.MULTILINE)
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
