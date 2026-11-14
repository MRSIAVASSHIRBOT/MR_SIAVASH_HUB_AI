from datetime import UTC, datetime

from fastapi.testclient import TestClient

from client_helpers import authenticated_client
from mrhub.config import get_settings
from mrhub.content.resource_reply_config import ResourceReplyConfigRepository
from mrhub.main import create_app


def test_resource_reply_config_is_persisted_for_the_current_user():
    client = authenticated_client()
    initial = client.get("/content/resource-reply/config")
    assert initial.status_code == 200
    assert initial.json()["keyword"] == "راهنما"
    assert initial.json()["resource_url"] == ""

    saved = client.put(
        "/content/resource-reply/config",
        json={
            "keyword": "آموزش",
            "resource_url": "https://example.org/security-guide",
            "resource_label": "راهنمای امنیت حساب",
            "intro_text": "سلام!",
            "include_follow": True,
            "follow_cta_text": "صفحه را دنبال کن.",
            "include_share": False,
            "share_cta_text": "این متن در خروجی نباید باشد.",
        },
    )
    assert saved.status_code == 200
    assert saved.json()["keyword"] == "آموزش"
    assert saved.json()["resource_url"] == "https://example.org/security-guide"
    assert saved.json()["include_share"] is False

    loaded = client.get("/content/resource-reply/config")
    assert loaded.status_code == 200
    assert loaded.json()["keyword"] == "آموزش"
    assert loaded.json()["resource_label"] == "راهنمای امنیت حساب"
    assert loaded.json()["updated_at"] is not None


def test_resource_reply_config_is_isolated_between_owners():
    client = authenticated_client()
    repository = ResourceReplyConfigRepository(get_settings().database_path)
    with repository.tasks._connection() as connection:
        owner_id = connection.execute(
            "SELECT user_id FROM auth_users WHERE username = 'owner'"
        ).fetchone()["user_id"]
        connection.execute(
            "INSERT INTO auth_users (user_id, username, salt, password_hash, created_at) "
            "VALUES (?, ?, ?, ?, ?)",
            (
                "resource-other-owner", "resource-other-owner", "00", "00",
                datetime.now(UTC).isoformat(),
            ),
        )
    repository.save(
        owner_id,
        {
            "keyword": "ویژه",
            "resource_url": "https://example.org/private-to-owner",
            "resource_label": "راهنما",
            "intro_text": "",
            "include_follow": False,
            "follow_cta_text": "",
            "include_share": False,
            "share_cta_text": "",
        },
    )
    assert repository.get("resource-other-owner")["keyword"] == "راهنما"
    assert repository.get("resource-other-owner")["resource_url"] == ""
    assert client.get("/content/resource-reply/config").json()["keyword"] == "ویژه"


def test_resource_reply_preview_uses_user_fields_and_never_gates_the_resource():
    client = authenticated_client()
    response = client.post(
        "/content/resource-reply/preview",
        json={
            "keyword": "راهنما",
            "resource_url": "https://example.org/free-course",
            "resource_label": "دورهٔ رایگان",
            "intro_text": "درود!",
            "include_follow": False,
            "follow_cta_text": "این دعوت خاموش است.",
            "include_share": True,
            "share_cta_text": "اگر خواستی این پست را به اشتراک بگذار.",
        },
    )
    assert response.status_code == 200
    result = response.json()
    assert result["keyword"] == "راهنما"
    assert result["resource_delivery_unconditional"] is True
    assert result["automation_active"] is False
    assert result["reply"].startswith("درود!")
    assert "این دعوت خاموش است." not in result["reply"]
    assert "اگر خواستی این پست را به اشتراک بگذار." in result["reply"]
    assert result["reply"].endswith("https://example.org/free-course")


def test_resource_reply_preview_rejects_missing_or_invalid_resource_url():
    client = authenticated_client()
    missing = client.post(
        "/content/resource-reply/preview",
        json={"keyword": "راهنما", "resource_url": ""},
    )
    invalid = client.post(
        "/content/resource-reply/preview",
        json={"keyword": "راهنما", "resource_url": "http://example.org/guide"},
    )
    assert missing.status_code == 422
    assert invalid.status_code == 422


def test_resource_reply_routes_require_authentication():
    get_settings.cache_clear()
    client = TestClient(create_app())
    assert client.get("/content/resource-reply/config").status_code in (401, 403)
    assert client.put("/content/resource-reply/config", json={}).status_code in (401, 403)
    get_settings.cache_clear()
