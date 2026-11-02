from mrhub.integrations.health_probe import (
    validate_health_path,
    validate_loopback_base_url,
)


def test_shared_contract_accepts_loopback_and_health_path():
    assert validate_loopback_base_url("http://127.0.0.1:18789") == "http://127.0.0.1:18789"
    assert validate_loopback_base_url("http://[::1]:9000") == "http://[::1]:9000"
    assert validate_health_path("/health") == "/health"


def test_shared_contract_rejects_remote_hosts_and_unsafe_paths():
    assert validate_loopback_base_url("https://example.com") is None
    assert validate_loopback_base_url("http://192.168.1.10:8000") is None
    assert validate_health_path("//example.com/health") is None
    assert validate_health_path("/../admin") is None
    assert validate_health_path("/%2e%2e/admin") is None
    assert validate_health_path("/health\\admin") is None
