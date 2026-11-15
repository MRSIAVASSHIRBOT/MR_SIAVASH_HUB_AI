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
        "request_id", "method", "route_template", "status_code"
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
        "request_id", "method", "route_template", "status_code", "outcome"
    ]
