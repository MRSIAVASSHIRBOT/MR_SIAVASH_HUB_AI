import pytest

from mrhub.research.repository import ResearchValidationError, canonicalize_evidence_url


@pytest.mark.parametrize(
    "url",
    [
        "https://./guide",
        "https://..../guide",
        "https://example..com/guide",
        "https://-example.com/guide",
        "https://example-.com/guide",
        "https://example_name.com/guide",
        "https://single-label/guide",
        "https://example.com:8443/guide",
        "https://[fd00::1]/guide",
    ],
)
def test_canonicalize_evidence_url_rejects_malformed_or_non_public_hosts(url):
    with pytest.raises(ResearchValidationError):
        canonicalize_evidence_url(url)


def test_canonicalize_evidence_url_normalizes_public_ipv6_literal():
    assert canonicalize_evidence_url(
        "https://[2606:4700:4700::1111]/guide/"
    ) == "https://[2606:4700:4700::1111]/guide"


def test_canonicalize_evidence_url_normalizes_idn_hostname():
    assert canonicalize_evidence_url(
        "https://bücher.example/guide/"
    ) == "https://xn--bcher-kva.example/guide"
