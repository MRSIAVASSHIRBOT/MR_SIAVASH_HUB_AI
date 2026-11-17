from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
WEB_ROOT = ROOT / "backend" / "mrhub" / "web"


def test_video_generation_provider_catalog_is_visible_and_read_only():
    html = (WEB_ROOT / "index.html").read_text(encoding="utf-8")
    app = (WEB_ROOT / "app.js").read_text(encoding="utf-8")

    assert 'id="video-generation-providers-refresh"' in html
    assert 'id="video-generation-providers-message"' in html
    assert 'id="video-generation-providers-list"' in html
    assert 'aria-live="polite"' in html
    assert 'api("/video-intelligence/generation/providers")' in app
    assert 'loadVideoGenerationProviders()' in app
    assert 'loadVideoGenerationProviders(),' in app
    assert 'element("article", undefined, "record")' in app
    assert 'textContent' in app
    assert "provider_unavailable" in app
    assert "هیچ Job یا درخواست خارجی اجرا نشده است" in app


def test_video_generation_provider_catalog_does_not_start_generation():
    app = (WEB_ROOT / "app.js").read_text(encoding="utf-8")
    start = app.index("  async function loadVideoGenerationProviders()")
    end = app.index("\n  async function previewVideoGenerationRoute(event)", start)
    catalog_loader = app[start:end]

    assert 'method: "POST"' not in catalog_loader
    assert "/generations" not in catalog_loader
    assert "submit_video_generation" not in catalog_loader



def test_video_generation_history_is_visible_and_owner_scoped():
    html = (WEB_ROOT / "index.html").read_text(encoding="utf-8")
    app = (WEB_ROOT / "app.js").read_text(encoding="utf-8")

    for element_id in (
        "video-generation-history-refresh",
        "video-generation-history-message",
        "video-generation-history-list",
        "video-generation-history-more",
    ):
        assert f'id="{element_id}"' in html
    assert 'aria-live="polite"' in html
    assert 'api("/video-intelligence/generations?"' in app
    assert "loadVideoGenerationHistory()" in app
    assert "loadVideoGenerationHistory()," in app
    assert "before_created_at" in app
    assert "before_generation_id" in app
    assert "videoGenerationHistoryRequestSequence" in app
    assert "replaceChildren" in app
    assert "textContent" in app


def test_video_generation_history_ui_supports_provider_confirmed_cancellation():
    app = (WEB_ROOT / "app.js").read_text(encoding="utf-8")
    start = app.index("  function renderVideoGenerationHistory()")
    end = app.index("\n  async function refreshAll()", start)
    history_ui = app[start:end]

    assert '["prepared", "queued"].includes(job.status) && !job.cancellation_requested' in history_ui
    assert '{ method: "DELETE" }' in history_ui
    assert "/video-intelligence/generations/" in history_ui
    assert "window.confirm" in history_ui
    assert "job.cancellation_requested" in history_ui
    assert '(job.status === "queued" && job.cancellation_requested)' in history_ui
    assert "تلاش دوباره برای لغو" in history_ui
    assert "وضعیت لغوشده فقط پس از تأیید Provider" in history_ui
    assert '["submitting", "unknown_outcome", "running"].includes(job.status)' in history_ui
    assert "/reconcile" in history_ui
    assert '{ method: "POST" }' in history_ui
    assert "/video-intelligence/analyses/" not in history_ui
    assert "generation/providers" not in history_ui



def test_hybrid_route_preview_is_visible_and_uses_explicit_preview_only_controls():
    html = (WEB_ROOT / "index.html").read_text(encoding="utf-8")
    app = (WEB_ROOT / "app.js").read_text(encoding="utf-8")

    for element_id in (
        "video-generation-route-preview-form",
        "video-generation-route-preview-submit",
        "video-generation-route-preview-message",
        "video-generation-route-preview-result",
    ):
        assert f'id="{element_id}"' in html
    assert 'name="remote_processing_approved"' in html
    assert 'name="remote_spend_approved"' in html
    assert 'name="max_remote_cost_usd"' in html
    assert 'api("/video-intelligence/generation/route-preview"' in app
    assert "previewVideoGenerationRoute" in app
    assert "provider_submission_started" in app
    assert 'result.execution === "not_started"' in app
    assert "هیچ Prompt یا فایل رسانه‌ای ارسال نمی‌شود" in html


def test_route_preview_ui_never_submits_or_reconciles_a_generation():
    app = (WEB_ROOT / "app.js").read_text(encoding="utf-8")
    start = app.index("  async function previewVideoGenerationRoute(")
    end = app.index("\n  function renderVideoGenerationHistory()", start)
    preview = app[start:end]

    assert 'method: "POST"' in preview
    assert "/video-intelligence/generation/route-preview" in preview
    assert "/generations" not in preview
    assert "/analyses/" not in preview
    assert "submit_video_generation" not in preview
    assert "provider_submission_started === false" in preview
