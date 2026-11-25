import json
import pathlib

CONTRACT_PATH = (
    pathlib.Path(__file__).resolve().parents[1]
    / "contracts"
    / "hybrid"
    / "v1"
    / "manifest.json"
)
OPENAPI_HTTP_METHODS = frozenset(
    {"get", "post", "put", "patch", "delete", "options", "head", "trace"}
)


def _contract() -> dict:
    return json.loads(CONTRACT_PATH.read_text(encoding="utf-8"))


def test_hybrid_contract_declares_supported_version_and_owners():
    contract = _contract()

    assert contract["contract_id"] == "mr-siavash-hybrid-integration"
    assert contract["contract_version"] == "1.0.0"
    assert contract["owners"] == {
        "hub": "private-state-policy-and-agent-control-plane",
        "el_ai": "telegram-transport-identity-and-command-routing",
        "website_gateway": "public-knowledge-and-public-support",
    }


def test_telegram_endpoint_manifest_matches_generated_openapi():
    from mrhub.main import create_app

    contract = _contract()
    telegram = contract["hub_telegram"]
    base_path = telegram["base_path"]
    openapi_paths = create_app().openapi()["paths"]

    declared_endpoints = {
        (endpoint["method"].upper(), endpoint["path"])
        for endpoint in telegram["endpoints"]
    }
    implemented_endpoints = {
        (method.upper(), path)
        for path, operations in openapi_paths.items()
        if path == base_path or path.startswith(f"{base_path}/")
        for method in operations
        if method.lower() in OPENAPI_HTTP_METHODS
    }

    assert len(declared_endpoints) == len(telegram["endpoints"]), (
        "Contract contains duplicate Telegram endpoint declarations"
    )
    assert declared_endpoints == implemented_endpoints, (
        "Telegram contract/OpenAPI drift: "
        f"missing_from_contract={sorted(implemented_endpoints - declared_endpoints)}, "
        f"missing_from_openapi={sorted(declared_endpoints - implemented_endpoints)}"
    )


def test_telegram_scopes_and_default_scope_match_implementation():
    from mrhub.api.routes.telegram_integration import DEFAULT_SCOPES, TelegramScope

    contract = _contract()
    declared_scopes = set(contract["hub_telegram"]["scopes"])
    implemented_scopes = set(TelegramScope.__args__)

    assert declared_scopes == implemented_scopes
    assert contract["hub_telegram"]["default_scopes"] == sorted(DEFAULT_SCOPES)


def test_telegram_token_and_challenge_lifetimes_match_implementation():
    from mrhub.integrations.telegram_pairing import TelegramPairingRepository

    contract = _contract()
    lifetimes = contract["hub_telegram"]["lifetimes_seconds"]

    assert lifetimes["access_token"] == TelegramPairingRepository.ACCESS_TTL_SECONDS
    assert lifetimes["refresh_token"] == TelegramPairingRepository.REFRESH_TTL_SECONDS
    assert lifetimes["pairing_challenge"] == TelegramPairingRepository.CHALLENGE_TTL_SECONDS


def test_hybrid_trust_boundaries_remain_explicit():
    contract = _contract()
    boundaries = contract["trust_boundaries"]

    assert boundaries["shared_database"] is False
    assert boundaries["website_gateway_may_call_private_hub"] is False
    assert boundaries["browser_may_hold_hub_credentials"] is False
    assert boundaries["public_gateway_data_classification"] == "public_only"
    request_id = contract["observability"]["request_id"]
    assert request_id["status"] == "standardized"
    assert request_id["header"] == "X-Request-ID"
    assert request_id["format"] == "canonical_lowercase_uuid"
    assert request_id["accepted_uuid_versions"] == [1, 2, 3, 4, 5, 6, 7, 8]
    assert request_id["server_fallback"] == "generate_uuid4_when_missing_or_invalid"
    assert request_id["response"] == "echo_canonical_request_id"
    assert request_id["request_state"] == "request.state.request_id"
    assert request_id["log_event"] == "http_request_completed"
    assert request_id["log_fields"] == [
        "request_id", "method", "route_template", "status_code", "duration_ms", "outcome"
    ]
    assert request_id["authorization_effect"] is False
    assert request_id["idempotency_effect"] is False
    assert request_id["public_gateway"] == "independent_correlation_id_only"
    assert request_id["retry_policy"] == (
        "single_401_refresh_then_one_retry_same_request_id; no_generic_retry_or_backoff"
    )
    assert "retries the original operation once" in request_id["note"]
    assert "does not perform generic retries or backoff" in request_id["note"]
    assert request_id["el_ai_log_event"] == "hub_request_completed"
    assert request_id["el_ai_log_fields"] == [
        "request_id", "method", "route_template", "status_code", "duration_ms", "outcome"
    ]
    job_correlation = contract["observability"]["bridge_job_correlation"]
    assert job_correlation["status"] == "standardized"
    assert job_correlation["header"] == "X-Correlation-ID"
    assert job_correlation["source"] == "el_ai_bridge_job_uuid_context"
    assert job_correlation["format"] == "canonical_lowercase_uuid"
    assert job_correlation["accepted_uuid_versions"] == [1, 2, 3, 4, 5, 6, 7, 8]
    assert job_correlation["server_fallback"] == "request_id_when_missing_or_invalid"
    assert job_correlation["request_state"] == "request.state.correlation_id"
    assert job_correlation["response"] == "not_echoed"
    assert job_correlation["log_event"] == "http_request_completed"
    assert job_correlation["log_fields"] == [
        "request_id", "correlation_id", "method", "route_template",
        "status_code", "duration_ms", "outcome"
    ]
    assert job_correlation["el_ai_log_fields"] == [
        "request_id", "correlation_id", "method", "route_template",
        "status_code", "duration_ms", "outcome"
    ]
    assert job_correlation["authorization_effect"] is False
    assert job_correlation["idempotency_effect"] is False
    assert job_correlation["ownership_effect"] is False
    assert "never an owner identity" in job_correlation["note"]


CONTRACT_DOC_PATH = (
    pathlib.Path(__file__).resolve().parents[1]
    / "docs"
    / "integrations"
    / "hybrid-integration-contract-v1.md"
)


def test_hybrid_contract_document_matches_bounded_retry_policy():
    document = CONTRACT_DOC_PATH.read_text(encoding="utf-8")
    request_id = _contract()["observability"]["request_id"]

    assert request_id["retry_policy"] == (
        "single_401_refresh_then_one_retry_same_request_id; no_generic_retry_or_backoff"
    )
    assert "one bounded recovery" in document
    assert "separate request with its own request ID" in document
    assert "at most once with the original request ID" in document
    assert "A second 401 is surfaced" in document
    assert "no generic retries or backoff" in document
    assert "The bridge does not automatically retry Hub requests." not in document


WEBSITE_GATEWAY_CONTRACT_PATH = (
    pathlib.Path(__file__).resolve().parents[1]
    / "contracts"
    / "hybrid"
    / "website-gateway"
    / "v1"
    / "manifest.json"
)


def _website_gateway_contract() -> dict:
    return json.loads(WEBSITE_GATEWAY_CONTRACT_PATH.read_text(encoding="utf-8"))


def test_website_gateway_relay_is_proposal_only_until_both_sides_are_implemented():
    relay = _website_gateway_contract()

    assert relay["contract_id"] == "mr-siavash-website-hub-public-query-relay"
    assert relay["contract_version"] == "1.0.0"
    assert relay["status"] == "proposed"
    assert all(
        endpoint["implementation_status"] == "not_implemented"
        for endpoint in relay["endpoints"]
    )
    assert relay["implementation_boundary"] == {
        "runtime_routes_added": False,
        "database_migrations_added": False,
        "secrets_added": False,
        "cloudflare_resources_changed": False,
        "production_enabled": False,
    }


def test_website_gateway_contract_document_matches_disabled_status():
    document_path = (
        pathlib.Path(__file__).resolve().parents[1]
        / "docs"
        / "integrations"
        / "website-hub-relay-v1.md"
    )
    document = document_path.read_text(encoding="utf-8")
    relay = _website_gateway_contract()

    assert "Status: proposed — not implemented" in document
    assert relay["contract_id"] in document
    assert "Gateway never opens a connection into the owner's private network" in document
    assert "The proposal adds no runtime endpoint, schema migration, secret, Cloudflare binding" in document
    assert "A7 is not complete until" in document


def test_website_gateway_pairing_is_owner_confirmed_and_hub_initiated():
    relay = _website_gateway_contract()

    assert relay["topology"]["direction"] == "hub_initiated_outbound_only"
    assert relay["topology"]["gateway_may_open_connection_to_hub"] is False
    assert relay["topology"]["local_hub_port_may_be_public"] is False
    assert relay["topology"]["public_tunnel_to_hub_allowed"] is False
    assert relay["topology"]["browser_may_hold_hub_credentials"] is False
    assert relay["pairing"]["initiated_by"] == "authenticated_gateway_administrator"
    assert relay["pairing"]["confirmed_by"] == "authenticated_local_hub_owner"
    assert relay["pairing"]["challenge_single_use"] is True
    assert relay["pairing"]["challenge_lifetime_seconds"] == 300
    assert relay["connector_authentication"]["algorithm"] == "Ed25519"
    assert relay["connector_authentication"]["nonce_single_use"] is True


def test_website_gateway_relay_has_only_public_query_scope_and_no_private_authority():
    relay = _website_gateway_contract()

    assert relay["pairing"]["initial_scopes"] == ["public_assistant:process"]
    assert relay["pairing"]["default_scopes"] == []
    policy = relay["processing_policy"]
    for capability in (
        "private_memory_read",
        "private_knowledge_read",
        "owner_task_read",
        "owner_task_create",
        "local_file_read",
        "tool_discovery",
        "tool_execution",
        "device_control",
        "approval_bypass",
    ):
        assert policy[capability] is False
    assert policy["owner_context_must_be_absent"] is True
    assert policy["public_request_treated_as_untrusted_data"] is True

    envelope = relay["request_envelope"]
    assert envelope["classification"] == "public_untrusted_input"
    assert {
        "owner_id",
        "telegram_user_id",
        "memory",
        "private_context",
        "task_id",
        "tool_arguments",
        "credentials",
    }.issubset(envelope["forbidden_fields"])


def test_website_gateway_relay_endpoints_are_unique_and_scoped():
    relay = _website_gateway_contract()
    endpoints = relay["endpoints"]
    keys = [(item["method"], item["path"]) for item in endpoints]

    assert len(keys) == len(set(keys))
    assert len(endpoints) >= 8
    assert all(item["method"] in {"GET", "POST", "DELETE"} for item in endpoints)
    assert all(item["auth_mode"] for item in endpoints)
    assert relay["request_envelope"]["limits"]["total_request_bytes"] <= 12 * 1024
    assert relay["response_envelope"]["limits"]["response_characters"] <= 8000
    assert relay["retry_policy"]["maximum_attempts"] <= 3


def test_website_gateway_relay_uses_server_owned_expiry_and_fenced_connector_leases():
    relay = _website_gateway_contract()

    request_envelope = relay["request_envelope"]
    assert request_envelope["server_generated_fields"] == ["request_id", "expires_at"]
    assert request_envelope["client_supplied_server_fields_accepted"] is False
    assert request_envelope["client_fields"] == ["message", "consent", "public_context"]

    pull = relay["pull_protocol"]
    assert pull["cursor_scope"] == "connector_id"
    assert pull["cursor_is_opaque"] is True
    assert pull["maximum_batch_size"] == relay["request_envelope"]["limits"]["pull_batch_size"]["maximum"]
    assert "same_batch_and_lease_tokens" in pull["same_cursor_retry"]

    lease = relay["lease_contract"]
    assert lease["minimum_entropy_bytes"] >= 32
    assert lease["storage"] == "hash_only_gateway_side"
    assert lease["binds_to"] == ["connector_id", "request_id", "lease_until"]
    assert lease["completion_requires_current_token"] is True
    assert lease["reclaimed_request_receives_new_token"] is True
    assert lease["old_token_cannot_complete_after_reclaim"] is True
    assert lease["token_in_logs"] is False

    poll = relay["public_poll_authentication"]
    assert poll["credential_header"] == "X-Relay-Poll-Credential"
    assert poll["credential_transport"] == "header_only"
    assert poll["credential_may_appear_in_url"] is False
    assert poll["credential_may_be_set_as_cookie"] is False
    assert poll["credential_storage"] == "browser_memory_only"
    assert poll["credential_in_logs_or_analytics"] is False

    assert "lease_token" in relay["observability"]["forbidden_fields"]
