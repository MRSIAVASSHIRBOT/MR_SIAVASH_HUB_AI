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
    assert 'textContent' in app
    assert "provider_unavailable" in app
    assert "هیچ Job یا درخواست خارجی اجرا نشده است" in app


def test_video_generation_provider_catalog_does_not_start_generation():
    app = (WEB_ROOT / "app.js").read_text(encoding="utf-8")
    start = app.index("  async function loadVideoGenerationProviders()")
    end = app.index("\n  async function refreshAll()", start)
    catalog_loader = app[start:end]

    assert 'method: "POST"' not in catalog_loader
    assert "/generations" not in catalog_loader
    assert "submit_video_generation" not in catalog_loader
