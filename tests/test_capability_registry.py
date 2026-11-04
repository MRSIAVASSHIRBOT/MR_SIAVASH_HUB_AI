from __future__ import annotations

import pytest

from mrhub.capabilities.registry import (
    CapabilityRegistry,
    CapabilityValidationError,
    canonicalize_source_url,
)


def make_registry(tmp_path):
    return CapabilityRegistry(tmp_path / "capabilities.sqlite3")


def test_candidate_registration_persists_normalized_metadata(tmp_path):
    registry = make_registry(tmp_path)
    candidate = registry.add_candidate(
        source_url="https://GitHub.com/Example/Useful-Tool.git/",
        display_name="Useful Tool",
        summary="Adds a reusable capability.",
        capabilities=["summarize", "search", "summarize"],
    )

    assert candidate.canonical_url == "https://github.com/Example/Useful-Tool"
    assert candidate.status == "discovered"
    assert candidate.license_id == "unknown"
    assert candidate.capabilities == ("summarize", "search")
    assert registry.get(candidate.candidate_id) == candidate
    assert registry.list_candidates(status="discovered") == [candidate]


def test_duplicate_canonical_source_is_rejected(tmp_path):
    registry = make_registry(tmp_path)
    registry.add_candidate(source_url="https://github.com/example/tool", display_name="Tool")

    with pytest.raises(CapabilityValidationError, match="already in the catalog"):
        registry.add_candidate(
            source_url="https://GITHUB.com/example/tool/", display_name="Duplicate"
        )


@pytest.mark.parametrize(
    "url",
    [
        "http://github.com/example/tool",
        "https://user:password@example.com/tool",
        "https://example.com/tool?token=secret",
        "https://localhost/tool",
        "https://127.0.0.1/tool",
        "https://example.local/tool",
        "https://example.com:8443/tool",
    ],
)
def test_source_urls_fail_closed(url):
    with pytest.raises(CapabilityValidationError):
        canonicalize_source_url(url)


def test_candidate_cannot_be_approved_without_review_evidence(tmp_path):
    registry = make_registry(tmp_path)
    candidate = registry.add_candidate(
        source_url="https://github.com/example/tool", display_name="Tool"
    )
    candidate = registry.transition(candidate.candidate_id, "reviewing")

    with pytest.raises(CapabilityValidationError, match="known license"):
        registry.transition(candidate.candidate_id, "approved")


def test_approval_requires_license_security_compatibility_and_test_plan(tmp_path):
    registry = make_registry(tmp_path)
    candidate = registry.add_candidate(
        source_url="https://github.com/example/tool", display_name="Tool"
    )
    registry.transition(candidate.candidate_id, "reviewing")
    evidence = {
        "license_url": "https://github.com/example/tool/blob/main/LICENSE",
        "security_review": "No execution or credential access during discovery.",
        "compatibility_notes": "Python 3.11+; isolated adapter boundary required.",
        "test_plan": "Run contract, dependency, and regression tests.",
    }

    approved = registry.transition(
        candidate.candidate_id, "approved", license_id="MIT", evidence=evidence
    )
    assert approved.status == "approved"
    assert approved.license_id == "MIT"
    assert set(approved.evidence) == set(evidence)


def test_approval_rejects_non_https_license_evidence(tmp_path):
    registry = make_registry(tmp_path)
    candidate = registry.add_candidate(
        source_url="https://github.com/example/tool", display_name="Tool"
    )
    registry.transition(candidate.candidate_id, "reviewing")
    evidence = {
        "license_url": "http://example.com/LICENSE",
        "security_review": "Reviewed without executing upstream code.",
        "compatibility_notes": "Requires an adapter boundary.",
        "test_plan": "Run contract and regression tests.",
    }

    with pytest.raises(CapabilityValidationError, match="public HTTPS license URL"):
        registry.transition(candidate.candidate_id, "approved", license_id="MIT", evidence=evidence)


def test_status_transitions_are_enforced_and_rejected_sources_can_be_revisited(tmp_path):
    registry = make_registry(tmp_path)
    candidate = registry.add_candidate(
        source_url="https://github.com/example/tool", display_name="Tool"
    )

    with pytest.raises(CapabilityValidationError, match="Invalid capability status transition"):
        registry.transition(candidate.candidate_id, "approved", license_id="MIT")

    rejected = registry.transition(candidate.candidate_id, "rejected")
    assert rejected.status == "rejected"
    reviewing = registry.transition(rejected.candidate_id, "reviewing")
    assert reviewing.status == "reviewing"


def test_catalog_limits_list_size_and_does_not_execute_source(tmp_path):
    registry = make_registry(tmp_path)
    candidate = registry.add_candidate(
        source_url="https://github.com/example/tool",
        display_name="Tool",
        integration_type="manual",
    )

    assert registry.list_candidates(limit=0) == [candidate]
    assert "execution" not in candidate.as_dict()
    assert registry.get(candidate.candidate_id).status == "discovered"
