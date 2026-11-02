from mrhub.integrations.health_probe import (
    validate_health_path,
    validate_loopback_base_url,
)


def test_loopback_url_accepts_literal_ipv4_loopback():
    assert validate_loopback_base_url("http://127.0.0.1:18789") == "http://127.0.0.1:18789"


def test_loopback_url_accepts_literal_ipv6_loopback():
    assert validate_loopback_base_url("http://[::1]:9000") == "http://[::1]:9000"


def test_loopback_url_rejects_remote_hosts_and_non_http_schemes():
    assert validate_loopback_base_url("https://example.com") is None
    assert validate_loopback_base_url("http://192.168.1.10:8000") is None
    assert validate_loopback_base_url("file:///tmp/health") is None


def test_loopback_url_rejects_credentials_and_query_strings():
    assert validate_loopback_base_url("http://user:pass@127.0.0.1:8000") is None
    assert validate_loopback_base_url("http://127.0.0.1:8000/?token=secret") is None


def test_health_path_accepts_simple_absolute_path():
    assert validate_health_path("/health") == "/health"


def test_health_path_rejects_absolute_urls_and_traversal():
    assert validate_health_path("https://example.com/health") is None
    assert validate_health_path("//example.com/health") is None
    assert validate_health_path("/../admin") is None
    assert validate_health_path("/health?token=secret") is None
    assert validate_health_path("/%2e%2e/admin") is None
    assert validate_health_path("/health\\admin") is None
