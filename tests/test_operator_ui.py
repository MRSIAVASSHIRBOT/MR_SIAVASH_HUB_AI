import re
import shutil
import subprocess
from importlib.resources import files

import pytest
from fastapi.testclient import TestClient

from mrhub.config import get_settings
from mrhub.main import create_app


def test_operator_ui_and_assets_are_served_locally_with_strict_csp(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("MRH_DATABASE_PATH", str(tmp_path / "ui.sqlite3"))
    get_settings.cache_clear()
    client = TestClient(create_app())

    page = client.get("/ui/")
    assert page.status_code == 200
    assert "text/html" in page.headers["content-type"]
    assert "default-src 'self'" in page.headers["content-security-policy"]
    assert "script-src 'self'" in page.headers["content-security-policy"]
    assert "unsafe-inline" not in page.headers["content-security-policy"]
    assert 'src="/ui/app.js"' in page.text
    assert 'href="/ui/app.css"' in page.text
    assert 'src="https://' not in page.text

    script = client.get("/ui/app.js")
    stylesheet = client.get("/ui/app.css")
    assert script.status_code == 200
    assert stylesheet.status_code == 200
    assert "innerHTML" not in script.text
    assert "eval(" not in script.text
    assert "sessionStorage" in script.text
    assert "localStorage" not in script.text
    assert "default-src 'self'" in script.headers["content-security-policy"]
    assert 'id="job-summary"' in page.text
    assert 'id="workflow-list"' in page.text
    assert 'id="workflow-resume-form"' in page.text
    assert 'id="workflow-reconciliation-form"' in page.text
    assert 'api("/jobs/summary")' in script.text
    assert 'api("/agent/workflows?limit=50")' in script.text
    assert "resume-check" in script.text
    assert "workflow-step-list" in script.text

    # Serving the shell does not bypass API authentication.
    assert client.get("/memory").status_code in (401, 403)
    get_settings.cache_clear()


def test_operator_ui_assets_are_included_in_installed_package() -> None:
    package = files("mrhub")
    assert package.joinpath("web/index.html").is_file()
    assert package.joinpath("web/app.js").is_file()
    assert package.joinpath("web/app.css").is_file()



def test_operator_ui_exposes_local_media_upload_and_draft_attachment_controls():
    client = TestClient(create_app())
    response = client.get("/ui/")
    assert response.status_code == 200
    assert 'id="media-file-input"' in response.text
    assert 'id="media-upload-button"' in response.text
    assert 'id="draft-media-select"' in response.text
    assert "media_asset_id" in client.get("/ui/app.js").text
    assert "/content/assets" in client.get("/ui/app.js").text



def test_operator_ui_exposes_bounded_agent_run_controls_and_result_panels():
    client = TestClient(create_app())
    response = client.get("/ui/")
    assert response.status_code == 200
    assert 'id="agent-run-form"' in response.text
    assert 'name="provider_mode"' in response.text
    assert 'name="knowledge_freshness_policy"' in response.text
    assert 'value="owner_reviewed_current_only"' in response.text
    assert 'id="agent-run-result"' in response.text
    assert 'id="agent-queue-button"' in response.text
    assert 'id="agent-queued-workflow-id"' in response.text
    assert 'id="agent-queued-refresh-button"' in response.text
    assert 'id="agent-queued-cancel-button"' in response.text
    assert 'id="agent-history-refresh-button"' in response.text
    assert 'id="agent-history-result"' in response.text
    assert 'id="agent-run-history"' in response.text
    script = client.get("/ui/app.js").text
    assert 'api("/agent/run"' in script
    assert "context_sources" in script
    assert "knowledge_freshness_policy" in script
    assert "excluded_stale_knowledge_count" in script
    assert 'api("/agent/model-runs?limit=20")' in script
    assert "metadata.selected_provider" in script
    assert "run.outcome" in script


def test_operator_ui_exposes_owner_scoped_video_render_controls():
    client = TestClient(create_app())
    page = client.get("/ui/")
    script = client.get("/ui/app.js")

    assert page.status_code == 200
    assert script.status_code == 200
    for element_id in (
        "video-render-submit",
        "video-render-refresh",
        "video-render-cancel",
        "video-render-message",
        "video-render-result",
    ):
        assert f'id="{element_id}"' in page.text

    assert "Idempotency-Key" in script.text
    assert "/video-intelligence/renders/" in script.text
    assert "/content/assets/" in script.text
    assert "downloadRenderedVideo" in script.text
    assert "downloadMediaAsset" in script.text
    assert "mrh_video_render_pending_key" in script.text
    assert "mrh_video_render_analysis_id" in script.text
    assert 'credentials: "omit"' in script.text
    assert 'cache: "no-store"' in script.text


def test_operator_ui_javascript_parses_with_node_when_available():
    node = shutil.which("node")
    if node is None:
        pytest.skip("Node.js is unavailable in this test environment")
    script = files("mrhub").joinpath("web/app.js")
    result = subprocess.run(
        [node, "--check", str(script)],
        check=False,
        capture_output=True,
        text=True,
        timeout=10,
    )
    assert result.returncode == 0, result.stderr


def test_operator_ui_static_id_selectors_resolve_and_ids_are_unique():
    html = files("mrhub").joinpath("web/index.html").read_text(encoding="utf-8")
    script = files("mrhub").joinpath("web/app.js").read_text(encoding="utf-8")

    html_ids = re.findall(r'\bid=["\']([^"\']+)["\']', html)
    duplicate_ids = sorted({item for item in html_ids if html_ids.count(item) > 1})
    assert not duplicate_ids, f"Duplicate operator UI IDs: {duplicate_ids}"

    declared_ids = set(html_ids)
    selected_ids = set(re.findall(r'\$\(["\']#([A-Za-z][\w-]*)["\']\)', script))
    missing_ids = sorted(selected_ids - declared_ids)
    assert not missing_ids, f"Operator UI selectors reference missing IDs: {missing_ids}"



def test_operator_ui_preserves_prompt_and_storyboard_state_for_same_analysis():
    script = files("mrhub").joinpath("web/app.js").read_text(encoding="utf-8")

    assert "videoPromptAnalysisId !== incomingAnalysisId" in script
    assert "videoPromptAnalysisId = activeVideoAnalysisId" in script
    assert "renderSelectedVideoPrompt();" in script
    render_analysis = script.split("function renderVideoAnalysis", 1)[1].split(
        "function clearVideoRenderState", 1
    )[0]
    submit_analysis = script.split("async function submitVideoAnalysis", 1)[1].split(
        "function renderSelectedVideoPrompt", 1
    )[0]
    assert "videoPromptAnalysisId = null" not in render_analysis
    assert "videoPromptAnalysisId = null" in submit_analysis


def test_operator_ui_scopes_active_render_status_to_selected_timeline_revision():
    script = files("mrhub").joinpath("web/app.js").read_text(encoding="utf-8")

    assert 'mrh_video_render_identity' in script
    assert "function currentVideoRenderIdentity()" in script
    assert "function syncVideoRenderTarget()" in script
    assert "activeVideoRenderIdentity !== currentVideoRenderIdentity()" in script
    assert "syncVideoRenderTarget();" in script
    assert "آخرین رندر متعلق به Timeline یا نسخهٔ دیگری است" in script
    assert 'const renderMayBeActive = Boolean(activeVideoRenderId)' in script
    assert script.count("|| renderMayBeActive") == 2
    render_status = script.split("function renderVideoRender", 1)[1].split(
        "async function refreshVideoRender", 1
    )[0]
    assert "syncVideoRenderTarget();" in render_status
    refresh = script.split("async function refreshVideoRender", 1)[1].split(
        "async function submitVideoRender", 1
    )[0]
    assert "activeVideoRenderIdentity !== currentVideoRenderIdentity()" in refresh


def test_operator_ui_exposes_saved_renderer_draft_render_selection_and_cleanup():
    client = TestClient(create_app())
    page = client.get("/ui/")
    script = client.get("/ui/app.js")

    assert page.status_code == 200
    assert script.status_code == 200
    assert 'id="video-render-source-note"' in page.text
    assert "rendererDraft.renderer_timeline" in script.text
    assert "rendererDraft.renderer_timeline_sha256" in script.text
    assert '"/video-intelligence/timeline-drafts/"' in script.text
    assert '"draft:" + rendererDraft.draft_id + ":v" + rendererDraft.version' in script.text
    assert "mrh_video_render_pending_requests" in script.text
    assert 'sessionStorage.removeItem("mrh_video_render_pending_requests")' in script.text
    assert "pendingVideoRenderIdentity = null" in script.text
