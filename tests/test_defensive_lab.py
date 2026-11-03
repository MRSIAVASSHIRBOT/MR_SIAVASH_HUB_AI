import datetime as dt
import json

import pytest

from client_helpers import authenticated_client
from mrhub.security.defensive_lab import (
    DefensiveReviewScope,
    ScopeValidationError,
    audit_configuration_text,
    audit_requirements_text,
    audit_structured_log_text,
)


def _scope(
    asset: str = "repo:owned-project",
    *,
    expires_at: dt.datetime | None = None,
) -> DefensiveReviewScope:
    return DefensiveReviewScope(
        authorization_reference="ticket-123",
        authorized_assets=(asset,),
        expires_at=expires_at or dt.datetime.now(dt.UTC) + dt.timedelta(days=1),
    )


def test_scope_requires_explicit_assets_and_current_authorization():
    now = dt.datetime(2026, 11, 2, tzinfo=dt.UTC)
    scope = DefensiveReviewScope(
        authorization_reference="ticket-123",
        authorized_assets=("repo:owned-project",),
        expires_at=now + dt.timedelta(hours=1),
    )
    scope.assert_current(now)
    assert scope.review_mode == "offline_static_only"

    with pytest.raises(ScopeValidationError, match="expired"):
        scope.assert_current(now + dt.timedelta(hours=2))


def test_scope_rejects_duplicate_or_blank_asset_identifiers():
    with pytest.raises(ValueError, match="unique"):
        DefensiveReviewScope(
            authorization_reference="ticket-123",
            authorized_assets=("repo:owned-project", "repo:owned-project"),
            expires_at=dt.datetime(2026, 11, 3, tzinfo=dt.UTC),
        )
    with pytest.raises(ValueError):
        DefensiveReviewScope(
            authorization_reference="   ",
            authorized_assets=("repo:owned-project",),
            expires_at=dt.datetime(2026, 11, 3, tzinfo=dt.UTC),
        )


def test_configuration_audit_reports_line_evidence_without_values():
    text = (
        "host = 127.0.0.1\n"
        "debug = true\n"
        "verify = false\n"
        "allow_origins = ['*']\n"
    )
    result = audit_configuration_text(
        text,
        scope=_scope(),
        asset="repo:owned-project",
        filename="settings.env",
    )

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
        audit_configuration_text(
            "x" * 1_000_001,
            scope=_scope(),
            asset="repo:owned-project",
        )


def test_configuration_audit_flags_insecure_cookie_settings_without_echoing_values():
    result = audit_configuration_text(
        "SESSION_COOKIE_SECURE = false\n"
        "SESSION_COOKIE_HTTPONLY = false\n",
        scope=_scope(),
        asset="repo:owned-project",
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



def test_configuration_audit_requires_current_exact_asset_scope():
    scope = _scope("repo:owned-project")

    with pytest.raises(ScopeValidationError, match="outside"):
        audit_configuration_text(
            "debug = true",
            scope=scope,
            asset="repo:another-project",
        )

    expired_scope = _scope(
        expires_at=dt.datetime.now(dt.UTC) - dt.timedelta(seconds=1)
    )
    with pytest.raises(ScopeValidationError, match="expired"):
        audit_configuration_text(
            "debug = true",
            scope=expired_scope,
            asset="repo:owned-project",
        )


def test_configuration_findings_include_confidence_and_remediation_without_values():
    result = audit_configuration_text(
        "debug = true",
        scope=_scope(),
        asset="repo:owned-project",
        filename="settings.env",
    )

    finding = result["findings"][0]
    assert finding["rule_id"] == "CFG001"
    assert finding["confidence"] == "high"
    assert "Disable debug mode" in finding["remediation"]
    assert result["scope_validated"] is True
    assert result["asset"] == "repo:owned-project"
    assert result["configuration_values_included"] is False


def test_dependency_manifest_review_is_offline_scoped_and_never_installs_packages():
    manifest = (
        "# project dependencies\n"
        "fastapi==0.115.0\n"
        "uvicorn>=0.30\n"
        "sample-lib @ https://packages.invalid/sample.whl\n"
        "-r nested-requirements.txt\n"
        "--index-url https://packages.invalid/simple\n"
    )
    result = audit_requirements_text(
        manifest,
        scope=_scope(),
        asset="repo:owned-project",
        filename="requirements.txt",
    )

    assert result["mode"] == "offline_dependency_manifest_review"
    assert result["packages_reviewed"] == 3
    assert result["unsupported_directives"] == 2
    assert result["review_complete"] is False
    assert {item["rule_id"] for item in result["findings"]} == {
        "DEP001",
        "DEP002",
        "DEP004",
        "DEP005",
    }
    assert result["vulnerability_database_consulted"] is False
    assert result["network_requests_made"] is False
    assert result["packages_installed"] is False
    assert result["targets_modified"] is False
    assert "packages.invalid" not in str(result)


def test_dependency_manifest_review_rejects_out_of_scope_asset_and_bounds_input():
    scope = _scope()
    with pytest.raises(ScopeValidationError, match="outside"):
        audit_requirements_text(
            "fastapi==0.115.0",
            scope=scope,
            asset="repo:other",
        )

    with pytest.raises(ValueError, match="1 MB"):
        audit_requirements_text(
            "x" * 1_000_001,
            scope=scope,
            asset="repo:owned-project",
        )


def test_dependency_manifest_exact_pin_is_not_flagged_but_ranges_are():
    result = audit_requirements_text(
        "fastapi==0.115.0\n"
        "uvicorn>=0.30\n"
        "example==1.2,>=1.1\n",
        scope=_scope(),
        asset="repo:owned-project",
    )

    assert result["packages_reviewed"] == 3
    assert [item["line"] for item in result["findings"]] == [2, 3]
    assert all(item["rule_id"] == "DEP001" for item in result["findings"])



def test_authenticated_config_review_api_enforces_scope_and_returns_safe_evidence():
    client = authenticated_client()
    response = client.post(
        "/security-lab/config-review",
        json={
            "scope": {
                "authorization_reference": "ticket-123",
                "authorized_assets": ["repo:owned-project"],
                "expires_at": (dt.datetime.now(dt.UTC) + dt.timedelta(days=1)).isoformat(),
                "review_mode": "offline_static_only",
            },
            "asset": "repo:owned-project",
            "filename": "settings.env",
            "text": "debug = true\n",
        },
    )

    assert response.status_code == 200
    result = response.json()
    assert result["scope_validated"] is True
    assert result["asset"] == "repo:owned-project"
    assert result["findings"][0]["rule_id"] == "CFG001"
    assert result["configuration_values_included"] is False
    assert result["network_requests_made"] is False
    assert result["targets_modified"] is False

    from mrhub.config import get_settings
    from mrhub.infrastructure.database import TaskRepository

    audit = TaskRepository(get_settings().database_path).list_audit()
    completed = [
        item for item in audit
        if item["event_type"] == "security_lab.review_completed"
    ]
    assert len(completed) == 1
    assert "ticket-123" not in str(completed[0])
    assert "debug = true" not in str(completed[0])


def test_authenticated_dependency_review_api_denies_out_of_scope_assets():
    client = authenticated_client()
    response = client.post(
        "/security-lab/dependency-review",
        json={
            "scope": {
                "authorization_reference": "ticket-123",
                "authorized_assets": ["repo:owned-project"],
                "expires_at": (dt.datetime.now(dt.UTC) + dt.timedelta(days=1)).isoformat(),
                "review_mode": "offline_static_only",
            },
            "asset": "repo:other-project",
            "filename": "requirements.txt",
            "text": "fastapi>=0.115\n",
        },
    )

    assert response.status_code == 403
    assert response.json()["detail"]["reason_code"] == "authorization_scope_denied"

    from mrhub.config import get_settings
    from mrhub.infrastructure.database import TaskRepository

    audit = TaskRepository(get_settings().database_path).list_audit()
    denied = [
        item for item in audit
        if item["event_type"] == "security_lab.review_denied"
    ]
    assert len(denied) == 1
    assert denied[0]["outcome"] == "denied"
    assert denied[0]["metadata"]["reason_code"] == "authorization_scope_denied"


def test_authenticated_dependency_review_api_is_offline_and_reports_unpinned_packages():
    client = authenticated_client()
    response = client.post(
        "/security-lab/dependency-review",
        json={
            "scope": {
                "authorization_reference": "ticket-123",
                "authorized_assets": ["repo:owned-project"],
                "expires_at": (dt.datetime.now(dt.UTC) + dt.timedelta(days=1)).isoformat(),
                "review_mode": "offline_static_only",
            },
            "asset": "repo:owned-project",
            "filename": "requirements.txt",
            "text": "fastapi>=0.115\n",
        },
    )

    assert response.status_code == 200
    result = response.json()
    assert result["findings"][0]["rule_id"] == "DEP001"
    assert result["vulnerability_database_consulted"] is False
    assert result["network_requests_made"] is False
    assert result["packages_installed"] is False
    assert result["targets_modified"] is False

    from mrhub.config import get_settings
    from mrhub.infrastructure.database import TaskRepository

    audit = TaskRepository(get_settings().database_path).list_audit()
    completed = [
        item for item in audit
        if item["event_type"] == "security_lab.review_completed"
    ]
    assert len(completed) == 1
    assert "ticket-123" not in str(completed[0])
    assert "fastapi>=0.115" not in str(completed[0])


def test_security_lab_api_requires_authentication():
    from fastapi.testclient import TestClient

    from mrhub.main import create_app

    client = TestClient(create_app())
    response = client.post(
        "/security-lab/config-review",
        json={
            "scope": {
                "authorization_reference": "ticket-123",
                "authorized_assets": ["repo:owned-project"],
                "expires_at": (dt.datetime.now(dt.UTC) + dt.timedelta(days=1)).isoformat(),
            },
            "asset": "repo:owned-project",
            "text": "debug = true",
        },
    )

    assert response.status_code == 401



def test_scope_rejects_authorizations_longer_than_thirty_days():
    scope = DefensiveReviewScope(
        authorization_reference="ticket-long",
        authorized_assets=("repo:owned-project",),
        expires_at=dt.datetime.now(dt.UTC) + dt.timedelta(days=31),
    )
    with pytest.raises(ScopeValidationError, match="30-day"):
        scope.assert_current()



def test_structured_log_review_correlates_events_without_returning_actor_identifiers():
    actor = "sensitive-user-identifier"
    records = [
        {"event_type": "auth.login.failed", "actor_id": actor}
        for _ in range(5)
    ]
    records += [
        {"event_type": "auth.login.succeeded", "actor_id": actor},
        {"event_type": "authorization.role_changed", "actor_id": "admin-actor"},
        {"event_type": "audit.integrity_failed"},
        {"event_type": "audit.record_deleted"},
    ]
    text = "\n".join(json.dumps(record) for record in records)

    result = audit_structured_log_text(
        text,
        scope=_scope(),
        asset="repo:owned-project",
        filename="events.jsonl",
    )

    assert result["mode"] == "offline_structured_security_log_review"
    assert result["scope_validated"] is True
    assert result["lines_reviewed"] == 9
    assert result["structured_records"] == 9
    assert result["network_requests_made"] is False
    assert result["targets_modified"] is False
    assert result["actor_identifiers_included"] is False
    assert result["raw_log_values_included"] is False
    assert {item["rule_id"] for item in result["findings"]} == {
        "LOG001", "LOG002", "LOG003", "LOG004", "LOG005"
    }
    assert actor not in str(result)
    assert "admin-actor" not in str(result)


def test_structured_log_review_counts_malformed_records_without_echoing_them():
    raw_secret = "malformed-line-with-sensitive-content"
    text = (
        json.dumps({"event_type": "unknown.event", "actor_id": "private-actor"})
        + "\n"
        + raw_secret
        + "\n"
        + json.dumps(["not", "an", "object"])
    )
    result = audit_structured_log_text(
        text,
        scope=_scope(),
        asset="repo:owned-project",
    )

    assert result["structured_records"] == 1
    assert result["unparsed_lines"] == 2
    assert result["findings"] == []
    assert raw_secret not in str(result)
    assert "private-actor" not in str(result)


def test_structured_log_review_enforces_scope_and_line_limit():
    scope = _scope()
    with pytest.raises(ScopeValidationError, match="outside"):
        audit_structured_log_text(
            "{}",
            scope=scope,
            asset="repo:another-project",
        )
    with pytest.raises(ValueError, match="10000-line"):
        audit_structured_log_text(
            "{}\n" * 10_001,
            scope=scope,
            asset="repo:owned-project",
        )


def test_authenticated_structured_log_review_api_returns_safe_findings_and_audits_metadata():
    client = authenticated_client()
    records = "\n".join(
        json.dumps({"event_type": "auth.login.failed", "actor_id": "private-login-id"})
        for _ in range(5)
    )
    response = client.post(
        "/security-lab/log-review",
        json={
            "scope": {
                "authorization_reference": "ticket-log-123",
                "authorized_assets": ["host:approved-test"],
                "expires_at": (dt.datetime.now(dt.UTC) + dt.timedelta(days=1)).isoformat(),
                "review_mode": "offline_static_only",
            },
            "asset": "host:approved-test",
            "filename": "auth-events.jsonl",
            "text": records,
        },
    )

    assert response.status_code == 200
    result = response.json()
    assert result["mode"] == "offline_structured_security_log_review"
    assert result["findings"][0]["rule_id"] == "LOG004"
    assert result["network_requests_made"] is False
    assert result["targets_modified"] is False
    assert "private-login-id" not in response.text

    from mrhub.config import get_settings
    from mrhub.infrastructure.database import TaskRepository

    audit = TaskRepository(get_settings().database_path).list_audit()
    completed = [
        item for item in audit
        if item["event_type"] == "security_lab.review_completed"
    ]
    assert len(completed) == 1
    assert completed[0]["metadata"]["reason_code"] == "offline_structured_security_log_review"
    assert "private-login-id" not in str(completed[0])
