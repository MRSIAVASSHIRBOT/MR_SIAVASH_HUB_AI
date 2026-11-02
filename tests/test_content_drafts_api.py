from datetime import UTC, datetime

from fastapi.testclient import TestClient

from client_helpers import authenticated_client
from mrhub.config import get_settings
from mrhub.content.repository import ContentDraftRepository
from mrhub.main import create_app


def test_content_draft_dedup_approval_versioning_and_edit_revokes_approval() -> None:
    client = authenticated_client()
    created = client.post(
        "/content/drafts",
        json={
            "platform": "instagram",
            "content_type": "caption",
            "title": "DNS learning post",
            "body": "DNS resolves names to records and helps troubleshoot network failures.",
            "hashtags": ["#networking", "#DNS"],
        },
    )
    assert created.status_code == 201
    draft = created.json()
    assert draft["status"] == "draft"
    assert draft["version"] == 1
    assert draft["approved_at"] is None

    duplicate = client.post(
        "/content/drafts",
        json={
            "platform": "instagram",
            "content_type": "caption",
            "title": "A different title",
            "body": "DNS resolves names to records and helps troubleshoot network failures.",
            "hashtags": ["#networking", "#DNS"],
        },
    )
    assert duplicate.status_code == 409

    approved = client.post(f"/content/drafts/{draft['draft_id']}/approve")
    assert approved.status_code == 200
    assert approved.json()["status"] == "approved"
    assert approved.json()["approved_by"] == "local-owner"
    assert approved.json()["approved_at"] is not None

    updated = client.patch(
        f"/content/drafts/{draft['draft_id']}",
        json={"body": "DNS troubleshooting starts with checking resolution and record responses."},
    )
    assert updated.status_code == 200
    assert updated.json()["status"] == "draft"
    assert updated.json()["version"] == 2
    assert updated.json()["approved_by"] is None
    assert updated.json()["approved_at"] is None

    versions = client.get(f"/content/drafts/{draft['draft_id']}/versions")
    assert versions.status_code == 200
    assert versions.json()["count"] == 2
    by_version = {item["version_number"]: item for item in versions.json()["versions"]}
    assert "helps troubleshoot network failures" in by_version[1]["body"]
    assert "checking resolution" in by_version[2]["body"]


def test_content_draft_deduplication_also_blocks_update_collisions() -> None:
    client = authenticated_client()
    first = client.post(
        "/content/drafts",
        json={
            "platform": "telegram",
            "content_type": "post_text",
            "title": "First",
            "body": "A unique draft for duplicate checking.",
        },
    )
    second = client.post(
        "/content/drafts",
        json={
            "platform": "telegram",
            "content_type": "post_text",
            "title": "Second",
            "body": "A different draft body.",
        },
    )
    assert first.status_code == 201
    assert second.status_code == 201

    collision = client.patch(
        f"/content/drafts/{second.json()['draft_id']}",
        json={"body": "A unique draft for duplicate checking."},
    )
    assert collision.status_code == 409
    unchanged = client.get(f"/content/drafts/{second.json()['draft_id']}")
    assert unchanged.json()["body"] == "A different draft body."


def test_content_draft_archive_restore_and_delete_lifecycle() -> None:
    client = authenticated_client()
    created = client.post(
        "/content/drafts",
        json={
            "platform": "generic",
            "content_type": "script",
            "title": "Lifecycle",
            "body": "A lifecycle test draft.",
        },
    )
    draft_id = created.json()["draft_id"]
    assert client.post(f"/content/drafts/{draft_id}/approve").json()["status"] == "approved"
    archived = client.post(f"/content/drafts/{draft_id}/archive")
    assert archived.status_code == 200
    assert archived.json()["status"] == "archived"
    assert archived.json()["approved_at"] is None
    assert client.patch(f"/content/drafts/{draft_id}", json={"title": "Cannot edit"}).status_code == 409
    restored = client.post(f"/content/drafts/{draft_id}/restore")
    assert restored.status_code == 200
    assert restored.json()["status"] == "draft"
    assert client.delete(f"/content/drafts/{draft_id}").status_code == 204
    assert client.get(f"/content/drafts/{draft_id}").status_code == 404
    assert client.get(f"/content/drafts/{draft_id}/versions").status_code == 404


def test_content_drafts_are_owner_scoped_and_audit_omits_body() -> None:
    client = authenticated_client()
    created = client.post(
        "/content/drafts",
        json={
            "platform": "instagram",
            "content_type": "caption",
            "title": "Private draft",
            "body": "private content that must not appear in audit metadata",
        },
    )
    assert created.status_code == 201
    repository = ContentDraftRepository(get_settings().database_path)
    with repository.tasks._connection() as connection:
        connection.execute(
            "INSERT INTO auth_users (user_id, username, salt, password_hash, created_at) "
            "VALUES (?, ?, ?, ?, ?)",
            (
                "content-other-owner",
                "content-other-owner",
                "00",
                "00",
                datetime.now(UTC).isoformat(),
            ),
        )
        audit = connection.execute(
            "SELECT subject_type, metadata_json FROM audit_events "
            "WHERE event_type = 'content.draft_created' ORDER BY created_at DESC LIMIT 1"
        ).fetchone()
    other = repository.create(
        "content-other-owner",
        "content-other-owner",
        platform="instagram",
        content_type="caption",
        title="Other owner's draft",
        body="private content that must not appear in audit metadata",
        hashtags=[],
    )
    assert client.get(f"/content/drafts/{other['draft_id']}").status_code == 404
    listing = client.get("/content/drafts")
    assert listing.status_code == 200
    assert listing.json()["count"] == 1
    assert audit["subject_type"] == "content_draft"
    assert "private content" not in audit["metadata_json"]


def test_content_draft_api_requires_authentication_and_has_no_publish_endpoint() -> None:
    get_settings.cache_clear()
    client = TestClient(create_app())
    assert client.get("/content/drafts").status_code in (401, 403)
    assert client.post("/content/drafts/publish").status_code in (401, 403, 404, 405)
    get_settings.cache_clear()



def test_telegram_draft_binds_media_asset_and_versions_approval_changes():
    client = authenticated_client()
    upload = client.post(
        "/content/assets",
        content=b"\x89PNG\r\n\x1a\nmedia-fixture",
        headers={
            "Content-Type": "image/png",
            "X-File-Name": "draft-preview.png",
        },
    )
    assert upload.status_code == 201
    asset_id = upload.json()["asset_id"]

    created = client.post(
        "/content/drafts",
        json={
            "platform": "telegram",
            "content_type": "post_text",
            "title": "Media draft",
            "body": "An approved Telegram photo post.",
            "hashtags": ["#Media"],
            "media_asset_id": asset_id,
        },
    )
    assert created.status_code == 201
    draft = created.json()
    assert draft["media_asset_id"] == asset_id
    assert draft["status"] == "draft"

    approved = client.post(f"/content/drafts/{draft['draft_id']}/approve")
    assert approved.status_code == 200
    assert approved.json()["status"] == "approved"

    detached = client.patch(
        f"/content/drafts/{draft['draft_id']}",
        json={"media_asset_id": None},
    )
    assert detached.status_code == 200
    assert detached.json()["media_asset_id"] is None
    assert detached.json()["status"] == "draft"
    assert detached.json()["version"] == 2

    versions = client.get(f"/content/drafts/{draft['draft_id']}/versions").json()["versions"]
    by_version = {item["version_number"]: item for item in versions}
    assert by_version[1]["media_asset_id"] == asset_id
    assert by_version[2]["media_asset_id"] is None


def test_telegram_draft_cannot_attach_another_owners_media_asset():
    client = authenticated_client()
    repository = ContentDraftRepository(get_settings().database_path)
    with repository.tasks._connection() as connection:
        connection.execute(
            "INSERT INTO auth_users (user_id, username, salt, password_hash, created_at) "
            "VALUES (?, ?, ?, ?, ?)",
            (
                "media-other-owner",
                "media-other-owner",
                "00",
                "00",
                datetime.now(UTC).isoformat(),
            ),
        )
    from mrhub.media.repository import MediaAssetRepository

    other_asset = MediaAssetRepository(get_settings().database_path).store_upload(
        "media-other-owner",
        "other.png",
        "image/png",
        b"\x89PNG\r\n\x1a\nother-owner",
    )
    response = client.post(
        "/content/drafts",
        json={
            "platform": "telegram",
            "content_type": "post_text",
            "title": "Invalid attachment",
            "body": "This must not attach another owner's media.",
            "media_asset_id": other_asset["asset_id"],
        },
    )
    assert response.status_code == 422
