from datetime import UTC, datetime, timedelta

import pytest

from mrhub.security.defensive_lab import (
    DefensiveReviewScope,
    ScopeValidationError,
    audit_configuration_text,
)


def test_scope_requires_explicit_assets_and_current_authorization():
    now = datetime(2026, 11, 2, tzinfo=UTC)
    scope = DefensiveReviewScope(
        authorization_reference="ticket-123",
        authorized_assets=("repo:owned-project",),
        expires_at=now + timedelta(hours=1),
    )
    scope.assert_current(now)
    assert scope.review_mode == "offline_static_only"

    with pytest.raises(ScopeValidationError, match="expired"):
        scope.assert_current(now + timedelta(hours=2))


def test_scope_rejects_duplicate_or_blank_asset_identifiers():
    with pytest.raises(ValueError, match="unique"):
        DefensiveReviewScope(
            authorization_reference="ticket-123",
            authorized_assets=("repo:owned-project", "repo:owned-project"),
            expires_at=datetime(2026, 11, 3, tzinfo=UTC),
        )
    with pytest.raises(ValueError):
        DefensiveReviewScope(
            authorization_reference="   ",
            authorized_assets=("repo:owned-project",),
            expires_at=datetime(2026, 11, 3, tzinfo=UTC),
        )


def test_configuration_audit_reports_line_evidence_without_values():
    text = (
        "host = 127.0.0.1\n"
        "debug = true\n"
        "verify = false\n"
        "allow_origins = ['*']\n"
    )
    result = audit_configuration_text(text, filename="settings.env")

    assert result["mode"] == "offline_defensive_configuration_review"
    assert result["network_requests_made"] is False
    assert result["targets_modified"] is False
    assert {(item["rule_id"], item["line"]) for item in result["findings"]} == {
        ("CFG001", 2),
        ("CFG003", 3),
        ("CFG004", 4),
    }
    assert "true" not in str(result)
    assert "false" not in str(result)


def test_configuration_audit_enforces_input_limit():
    with pytest.raises(ValueError, match="1 MB"):
        audit_configuration_text("x" * 1_000_001)


def test_configuration_audit_flags_insecure_cookie_settings_without_echoing_values():
    result = audit_configuration_text(
        "SESSION_COOKIE_SECURE = false\n"
        "SESSION_COOKIE_HTTPONLY = false\n",
        filename="app.env",
    )

    assert {(item["rule_id"], item["line"]) for item in result["findings"]} == {
        ("CFG005", 1),
        ("CFG006", 2),
    }
    assert "false" not in str(result)
    assert result["configuration_values_included"] is False
    assert result["network_requests_made"] is False
    assert result["targets_modified"] is False
