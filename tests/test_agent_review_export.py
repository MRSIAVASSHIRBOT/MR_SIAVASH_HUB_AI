import hashlib
import json

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


def test_export_is_deterministic_and_checksum_matches_payload():
    first = export_review_summary(summary())
    second = export_review_summary(summary())

    assert first == second
    assert first["schema_version"] == 1
    assert first["sha256"] == hashlib.sha256(
        first["payload"].encode("utf-8")
    ).hexdigest()
    assert json.loads(first["payload"])["findings"] == ["needs review"]


@pytest.mark.parametrize(
    "changes",
    [
        {"revision": True},
        {"revision": 0},
        {"approved": "yes"},
        {"digest": "bad"},
        {"digest": "g" * 64},
        {"findings": "not-a-list"},
        {"findings": [object()]},
    ],
)
def test_rejects_malformed_fields(changes):
    with pytest.raises(ExportError):
        export_review_summary(summary(**changes))


def test_rejects_missing_required_fields():
    with pytest.raises(ExportError, match="Missing required fields"):
        export_review_summary({"revision": 1})


def test_rejects_too_many_or_oversized_findings():
    with pytest.raises(ExportError):
        export_review_summary(summary(findings=["x"] * 501))
    with pytest.raises(ExportError):
        export_review_summary(summary(findings=["x" * 501]))


def test_enforces_encoded_utf8_byte_limit():
    with pytest.raises(ExportError, match="Summary too large"):
        export_review_summary(summary(findings=["é" * 500] * 500))


def test_rejects_invalid_unicode_encoding():
    with pytest.raises(ExportError, match="UTF-8 JSON"):
        export_review_summary(summary(findings=["\ud800"]))
