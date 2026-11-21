from pathlib import Path
from uuid import UUID

from client_helpers import authenticated_client
from mrhub.config import get_settings
from mrhub.media.repository import MediaAssetRepository

_PNG = b"\x89PNG\r\n\x1a\n" + b"test-png-payload"


def _uploaded_asset():
    client = authenticated_client()
    response = client.post(
        "/content/assets",
        content=_PNG,
        headers={
            "Content-Type": "image/png",
            "X-File-Name": "integrity-fixture.png",
        },
    )
    assert response.status_code == 201
    asset_id = UUID(response.json()["asset_id"])
    repository = MediaAssetRepository(get_settings().database_path)
    owner = repository.tasks.get_auth_user("owner")
    assert owner is not None
    record = repository.get(str(owner["user_id"]), asset_id)
    assert record is not None
    return client, repository, asset_id, record


def test_private_media_download_serves_verified_snapshot_and_cleans_it(
    tmp_path: Path, monkeypatch
):
    import mrhub.api.routes.media as media_routes

    client, _repository, asset_id, _record = _uploaded_asset()
    monkeypatch.setattr(media_routes.tempfile, "tempdir", str(tmp_path))

    response = client.get(f"/content/assets/{asset_id}/file")

    assert response.status_code == 200
    assert response.content == _PNG
    assert response.headers["X-Content-Type-Options"] == "nosniff"
    assert response.headers["Cache-Control"] == "no-store"
    assert list(tmp_path.iterdir()) == []


def test_private_media_download_rejects_tampered_asset_and_cleans_snapshot(
    tmp_path: Path, monkeypatch
):
    import mrhub.api.routes.media as media_routes

    client, repository, asset_id, record = _uploaded_asset()
    monkeypatch.setattr(media_routes.tempfile, "tempdir", str(tmp_path))
    source = repository.file_path(str(record["storage_key"]))
    tampered = bytearray(_PNG)
    tampered[-1] ^= 0x01
    source.write_bytes(tampered)

    response = client.get(f"/content/assets/{asset_id}/file")

    assert response.status_code == 409
    assert response.json()["detail"] == "media_asset_integrity_failed"
    assert list(tmp_path.iterdir()) == []


def test_private_media_download_preserves_not_found_for_missing_source(
    tmp_path: Path, monkeypatch
):
    import mrhub.api.routes.media as media_routes

    client, repository, asset_id, record = _uploaded_asset()
    monkeypatch.setattr(media_routes.tempfile, "tempdir", str(tmp_path))
    repository.file_path(str(record["storage_key"])).unlink()

    response = client.get(f"/content/assets/{asset_id}/file")

    assert response.status_code == 404
    assert response.json()["detail"] == "Media file is missing"
    assert list(tmp_path.iterdir()) == []
