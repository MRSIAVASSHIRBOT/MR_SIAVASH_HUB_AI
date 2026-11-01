from datetime import UTC, datetime, timedelta

from mrhub.capabilities.metadata_evaluation import evaluate_repository_metadata


def test_evaluation_prioritizes_recent_licensed_active_repository_without_approving():
    metadata = {
        "license": {"spdx_id": "MIT"},
        "archived": False,
        "disabled": False,
        "fork": False,
        "stargazers_count": 1500,
        "updated_at": (datetime.now(UTC) - timedelta(days=10)).isoformat(),
    }

    result = evaluate_repository_metadata(metadata)

    assert result["score"] >= 70
    assert result["recommendation"] == "prioritize_review"
    assert result["scope"] == "metadata_only"
    assert result["security_audit_completed"] is False
    assert result["approval_granted"] is False
    assert result["installation_started"] is False
    assert result["source_code_executed"] is False


def test_evaluation_requires_manual_review_for_unknown_license():
    result = evaluate_repository_metadata({"license": None, "stargazers_count": 0})

    assert result["recommendation"] == "manual_review_required"
    assert any(signal["code"] == "license_unknown" for signal in result["signals"])


def test_evaluation_deprioritizes_archived_or_disabled_repository():
    result = evaluate_repository_metadata({
        "license": {"spdx_id": "MIT"},
        "archived": True,
        "disabled": False,
        "stargazers_count": 2000,
    })

    assert result["score"] < 50
    assert result["recommendation"] == "manual_review_required"
    assert any(signal["code"] == "repository_inactive" for signal in result["signals"])


def test_evaluation_handles_malformed_timestamps_and_clamps_score():
    result = evaluate_repository_metadata({
        "license": {"spdx_id": "MIT"},
        "updated_at": "not-a-timestamp",
        "stargazers_count": 100000,
    })

    assert 0 <= result["score"] <= 100
    assert any(signal["code"] == "invalid_updated_at" for signal in result["signals"])
