import pytest

from mrhub.agents.review_export import ExportError, export_review_summary


def summary(**overrides):
    value = {
        "revision": 1,
        "digest": "a" * 64,
        "approved": False,
        "findings": ["needs review"],
    }
    value.update(overrides)
    return value


def test_export_is_deterministic_and_returns_checksum():
    first = export_review_summary(summary())
    second = export_review_summary(summary())

    assert first == second
    assert len(first["sha256"]) == 64
    assert first["schema_version"] == 1


@pytest.mark.parametrize(
    "overrides",
    [
        {"revision": True},
        {"revision": 0},
        {"approved": "yes"},
        {"digest": "invalid"},
        {"digest": "G" * 64},
        {"findings": "not-a-list"},
        {"findings": [None]},
    ],
)
def test_rejects_malformed_summary(overrides):
    with pytest.raises(ExportError):
        export_review_summary(summary(**overrides))


def test_rejects_too_many_findings():
    with pytest.raises(ExportError):
        export_review_summary(summary(findings=["finding"] * 501))


def test_rejects_oversized_individual_finding():
    with pytest.raises(ExportError):
        export_review_summary(summary(findings=["x" * 501]))


def test_enforces_serialized_utf8_byte_limit():
    findings = ["é" * 500] * 500
    with pytest.raises(ExportError):
        export_review_summary(summary(findings=findings))


def test_ignores_unrecognized_input_fields():
    expected = export_review_summary(summary())
    actual = export_review_summary(summary(untrusted_extra="ignored"))
    assert actual == expected
