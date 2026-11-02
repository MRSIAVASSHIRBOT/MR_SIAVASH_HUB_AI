from pathlib import Path

from fastapi import HTTPException
from pydantic import SecretStr
import pytest

from mrhub.config import Settings
from mrhub.api.routes import public_media
from mrhub.media.repository import MediaAssetRepository


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



def test_signed_route_serves_only_valid_unexpired_image(monkeypatch, tmp_path: Path):
    now = 1_800_000_000
    settings = Settings(
        database_path=tmp_path / "db.sqlite3",
        public_media_base_url="https://media.example.com",
        public_media_signing_key=SecretStr("s" * 40),
    )
    monkeypatch.setattr(public_media, "get_settings", lambda: settings)
    monkeypatch.setattr(public_media.time, "time", lambda: now)
    repository = MediaAssetRepository(settings.database_path)
    asset = repository.store_upload(
        "owner-1",
        "sample.png",
        "image/png",
        b"\\x89PNG\\r\\n\\x1a\\n" + b"test-image-data",
    )
    url = public_media.sign_asset_url(str(asset["asset_id"]), now=now)
    from urllib.parse import parse_qs, urlsplit

    query = parse_qs(urlsplit(url).query)
    response = public_media.serve_signed_media(
        asset["asset_id"],
        expires=int(query["expires"][0]),
        signature=query["signature"][0],
    )
    assert response.media_type == "image/png"
    assert Path(response.path).is_file()


def test_signed_route_rejects_invalid_signature(monkeypatch, tmp_path: Path):
    now = 1_800_000_000
    settings = Settings(
        database_path=tmp_path / "db.sqlite3",
        public_media_signing_key=SecretStr("s" * 40),
    )
    monkeypatch.setattr(public_media, "get_settings", lambda: settings)
    monkeypatch.setattr(public_media.time, "time", lambda: now)
    with pytest.raises(HTTPException) as exc:
        public_media.serve_signed_media(
            "123e4567-e89b-12d3-a456-426614174000",
            expires=now + 60,
            signature="0" * 64,
        )
    assert exc.value.status_code == 403


def test_signed_route_rejects_expired_url(monkeypatch, tmp_path: Path):
    now = 1_800_000_000
    settings = Settings(
        database_path=tmp_path / "db.sqlite3",
        public_media_signing_key=SecretStr("s" * 40),
    )
    monkeypatch.setattr(public_media, "get_settings", lambda: settings)
    monkeypatch.setattr(public_media.time, "time", lambda: now)
    with pytest.raises(HTTPException) as exc:
        public_media.serve_signed_media(
            "123e4567-e89b-12d3-a456-426614174000",
            expires=now - 1,
            signature="0" * 64,
        )
    assert exc.value.status_code == 403
