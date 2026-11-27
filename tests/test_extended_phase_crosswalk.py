import re
from pathlib import Path

PHASE_RANGES = {
    "G": 12,
    "H": 32,
    "E": 21,
    "L": 19,
    "A": 22,
    "X": 23,
    "I": 15,
    "ML": 17,
}


def test_extended_phase_crosswalk_covers_each_requested_identifier_once():
    repository_root = Path(__file__).resolve().parents[1]
    crosswalk = repository_root / "docs" / "roadmap" / "EXTENDED_PHASE_CROSSWALK.md"
    document = crosswalk.read_text(encoding="utf-8")

    for prefix, maximum in PHASE_RANGES.items():
        identifiers = [
            int(match)
            for match in re.findall(
                rf"^\|\s*{prefix}(\d+)\s*\|",
                document,
                flags=re.MULTILINE,
            )
        ]
        assert identifiers == list(range(maximum + 1)), prefix

    assert "ADR-0051" in document
    assert "MR_SIAVASH_HUB_AI" in document
    assert "MR_SIAVASH_EL_AI" in document
    assert "MR_SIAVASH_EL_AGENT" in document
    assert "MR_SIAVASH_AI" in document
