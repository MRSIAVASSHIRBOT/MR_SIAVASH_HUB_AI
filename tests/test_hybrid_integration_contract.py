import json
import pathlib

CONTRACT_PATH = (
    pathlib.Path(__file__).resolve().parents[1]
    / "contracts"
    / "hybrid"
    / "v1"
    / "manifest.json"
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
    openapi_paths = create_app().openapi()["paths"]

    for endpoint in contract["hub_telegram"]["endpoints"]:
        method = endpoint["method"].lower()
        path = endpoint["path"]
        assert path in openapi_paths, f"Contract path missing from OpenAPI: {path}"
        assert method in openapi_paths[path], (
            f"Contract method missing from OpenAPI: {method} {path}"
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
    assert contract["observability"]["request_id"]["status"] == "not_yet_standardized"
