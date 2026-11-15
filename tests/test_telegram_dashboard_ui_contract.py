from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
WEB_ROOT = ROOT / "backend" / "mrhub" / "web"


def test_telegram_pairing_form_exposes_the_complete_allowlisted_scope_set():
    html = (WEB_ROOT / "index.html").read_text(encoding="utf-8")

    for scope in (
        "status:read",
        "tasks:read",
        "tasks:result",
        "tasks:create",
        "tasks:cancel",
        "memory:search",
        "video:read",
        "video:cancel",
    ):
        assert f'value="{scope}"' in html


def test_active_telegram_clients_can_replace_scopes_with_owner_confirmation():
    app = (WEB_ROOT / "app.js").read_text(encoding="utf-8")
    start = app.index("  const TELEGRAM_SCOPE_OPTIONS")
    end = app.index("\n  async function createTelegramPairing", start)
    editor = app[start:end]

    assert 'if (client.status === "active")' in editor
    assert 'name = "telegram-client-scopes"' in editor
    assert '"/scopes"' in editor
    assert 'method: "PUT"' in editor
    assert "body: { scopes: nextScopes }" in editor
    assert "window.confirm" in editor
    assert "scopeEditor.disabled = true" in editor
    assert "await loadTelegramClients()" in editor
    assert "video:read" in editor
    assert "video:cancel" in editor


def test_telegram_scope_editor_rejects_empty_or_unchanged_updates_in_the_ui():
    app = (WEB_ROOT / "app.js").read_text(encoding="utf-8")
    start = app.index("  const TELEGRAM_SCOPE_OPTIONS")
    end = app.index("\n  async function createTelegramPairing", start)
    editor = app[start:end]

    assert "if (!nextScopes.length)" in editor
    assert "مجوزها تغییری نکرده‌اند" in editor
    assert "مجوزهای اتصال با موفقیت به‌روزرسانی شدند" in editor
