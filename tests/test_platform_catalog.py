from mrhub.platform.catalog import get_domain, list_domains


def test_catalog_has_ten_stable_domains_and_explicit_maturity():
    domains = list_domains()
    assert len(domains) == 10
    assert len({item["domain_id"] for item in domains}) == 10
    assert {item["maturity"] for item in domains} <= {"foundation", "partial", "planned"}
    assert get_domain("content")["maturity"] == "foundation"
    assert get_domain("web")["maturity"] == "planned"
    assert get_domain("missing") is None


def test_catalog_returns_defensive_copies():
    first = list_domains()
    first[0]["next_steps"].append("mutated")
    assert "mutated" not in list_domains()[0]["next_steps"]
