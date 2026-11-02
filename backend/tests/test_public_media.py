from pydantic import SecretStr
import pytest

from mrhub.config import Settings
from mrhub.api.routes import public_media


def test_sign_asset_url_requires_public_https_base(monkeypatch):
    settings = Settings(
        public_media_base_url="http://media.example.com",
        public_media_signing_key=SecretStr("s" * 40),
    )
    monkeypatch.setattr(public_media, "get_settings", lambda: settings)
    with pytest.raises(ValueError, match="public HTTPS"):
        public_media.sign_asset_url("123e4567-e89b-12d3-a456-426614174000", now=1_800_000_000)


def test_sign_asset_url_generates_expiring_hmac_url(monkeypatch):
    settings = Settings(
        public_media_base_url="https://media.example.com",
        public_media_signing_key=SecretStr("s" * 40),
    )
    monkeypatch.setattr(public_media, "get_settings", lambda: settings)
    url = public_media.sign_asset_url(
        "123e4567-e89b-12d3-a456-426614174000",
        now=1_800_000_000,
    )
    assert url.startswith("https://media.example.com/public/media/123e4567-e89b-12d3-a456-426614174000?")
    assert "expires=1800000900" in url
    assert "signature=" in url


def test_sign_asset_url_rejects_missing_signing_key(monkeypatch):
    settings = Settings(public_media_base_url="https://media.example.com")
    monkeypatch.setattr(public_media, "get_settings", lambda: settings)
    with pytest.raises(Exception, match="public_media_not_configured"):
        public_media.sign_asset_url("123e4567-e89b-12d3-a456-426614174000", now=1_800_000_000)
