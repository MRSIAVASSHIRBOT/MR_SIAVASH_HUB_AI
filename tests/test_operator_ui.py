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



def test_operator_ui_exposes_saved_storyboard_timeline_preparation():
    client = TestClient(create_app())
    page = client.get("/ui/")
    script = client.get("/ui/app.js")

    assert page.status_code == 200
    assert script.status_code == 200
    assert 'id="video-storyboard-prepare-render-timeline"' in page.text
    assert 'id="video-render-submit"' in page.text
    assert "/prepare-render-timeline" in script.text
    assert "prepareSavedVideoDraftForRender" in script.text
    assert '$("#video-storyboard-prepare-render-timeline").addEventListener("click", prepareVideoRenderTimeline)' in script.text
    assert "renderer_timeline_sha256" in script.text
    assert "video-storyboard-render-submit" not in page.text
    assert "submitVideoDraftRender" not in script.text
    assert "function syncStoryboardRenderButtons()" in script.text

    prepare = script.text.split("async function prepareSavedVideoDraftForRender", 1)[1].split(
        "async function prepareVideoRenderTimeline", 1
    )[0]
    assert "/prepare-render-timeline" in prepare
    assert "if (saved.renderer_timeline && saved.renderer_timeline_sha256)" not in prepare

    submit = script.text.split("async function submitVideoRender", 1)[1].split(
        "async function cancelVideoRender", 1
    )[0]
    assert "const selectedDraft = activeVideoTimelineDraft" in submit
    assert "Timeline این Draft ناقص است" in submit


def test_operator_ui_scopes_active_render_status_to_selected_timeline_revision():
    script = files("mrhub").joinpath("web/app.js").read_text(encoding="utf-8")

    assert 'mrh_video_render_identity' in script
    assert "function currentVideoRenderIdentity()" in script
    assert "function syncVideoRenderTarget()" in script
    assert script.count("function currentVideoRenderIdentity()") == 1
    assert script.count("function syncVideoRenderTarget()") == 1
    assert "activeVideoRenderIdentity === currentVideoRenderIdentity()" in script
    lock = script.split("function lockVideoStoryboardControls", 1)[1].split(
        "function clearVideoRenderState", 1
    )[0]
    assert '$("#video-render-submit")' in lock
    assert "syncVideoRenderTarget();" in script
    assert "نمایش فعلی متعلق به Timeline یا نسخهٔ دیگری است" in script
    assert "const renderMayBeActive = !activeVideoRenderStatus" in script
    assert '$("#video-render-refresh").disabled = false;' in script
    assert '$("#video-render-cancel").disabled = !["accepted", "running"].includes(activeVideoRenderStatus);' in script
    render_status = script.split("function renderVideoRender", 1)[1].split(
        "async function refreshVideoRender", 1
    )[0]
    assert "syncVideoRenderTarget();" in render_status
    refresh = script.split("async function refreshVideoRender", 1)[1].split(
        "async function submitVideoRender", 1
    )[0]
    assert "renderIdentity && renderIdentity !== currentVideoRenderIdentity()" in refresh
    assert "activeVideoRenderIdentity !== currentVideoRenderIdentity()" not in refresh
    sync_target = script.split("function syncVideoRenderTarget", 1)[1].split(
        "function message", 1
    )[0]
    assert "replaceChildren" not in sync_target
    assert "دکمه‌های بررسی و لغو فقط همان Job قبلی را کنترل می‌کنند" in sync_target


def test_operator_ui_exposes_saved_renderer_draft_preparation_and_cleanup():
    client = TestClient(create_app())
    page = client.get("/ui/")
    script = client.get("/ui/app.js")

    assert page.status_code == 200
    assert script.status_code == 200
    assert 'id="video-storyboard-prepare-render-timeline"' in page.text
    assert 'id="video-render-submit"' in page.text
    assert 'id="video-render-source-note"' not in page.text
    assert "async function prepareVideoRenderTimeline()" in script.text
    assert "async function prepareSavedVideoDraftForRender" in script.text
    assert "selectedDraft.renderer_timeline" in script.text
    assert "selectedDraft.renderer_timeline_sha256" in script.text
    assert '"/video-intelligence/timeline-drafts/"' in script.text
    assert '"draft:" + rendererDraft.draft_id + ":v" + rendererDraft.version' in script.text
    assert "mrh_video_render_pending_requests" in script.text
    assert 'sessionStorage.removeItem("mrh_video_render_pending_requests")' in script.text
    assert "pendingVideoRenderIdentity = null" in script.text



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


def test_operator_ui_ignores_stale_async_render_responses_after_target_switch():
    script = files("mrhub").joinpath("web/app.js").read_text(encoding="utf-8")

    refresh = script.split("async function refreshVideoRender", 1)[1].split(
        "async function submitVideoRender", 1
    )[0]
    assert "const renderId = activeVideoRenderId" in refresh
    assert "const renderIdentity = activeVideoRenderIdentity" in refresh
    assert "activeVideoRenderId !== renderId" in refresh
    assert "activeVideoRenderIdentity !== renderIdentity" in refresh
    assert "renderIdentity !== currentVideoRenderIdentity()" not in refresh.split(
        "const render = await api", 1
    )[1].split("renderVideoRender(render)", 1)[0]

    submit = script.split("async function submitVideoRender", 1)[1].split(
        "async function cancelVideoRender", 1
    )[0]
    assert "const requestAnalysisId = activeVideoAnalysisId" in submit
    assert "activeVideoRenderAnalysisId = requestAnalysisId" in submit
    assert "currentVideoRenderIdentity() === requestIdentity" in submit
    assert "syncVideoRenderTarget();" in submit
    success_guard = submit.split(
        "if (currentVideoRenderIdentity() === requestIdentity)", 1
    )[1].split("} else {", 1)[0]
    assert "message(" in success_guard
    assert "await refreshVideoRender();" in success_guard
    error_guard = submit.split("} catch (error) {", 1)[1].split("} finally", 1)[0]
    assert "if (currentVideoRenderIdentity() === requestIdentity)" in error_guard
    assert "syncVideoRenderTarget();" in error_guard

    cancel = script.split("async function cancelVideoRender", 1)[1].split(
        "async function downloadRenderedVideo", 1
    )[0]
    assert "const renderId = activeVideoRenderId" in cancel
    assert "const renderIdentity = activeVideoRenderIdentity" in cancel
    assert "encodeURIComponent(renderId)" in cancel
    assert "activeVideoRenderId !== renderId" in cancel
    assert "activeVideoRenderIdentity !== renderIdentity" in cancel
    assert "فقط همان Job قبلی لغو می‌شود" in cancel

def test_operator_ui_binds_render_retries_to_exact_analysis_or_draft_revision():
    script = files("mrhub").joinpath("web/app.js").read_text(encoding="utf-8")

    assert "pendingVideoRenderRequests[requestIdentity]" in script
    assert "mrh_video_render_pending_requests" in script
    assert '"draft:" + rendererDraft.draft_id + ":v" + rendererDraft.version' in script
    assert "rendererDraft.renderer_timeline_sha256" in script
    assert 'sessionStorage.setItem("mrh_video_render_identity", activeVideoRenderIdentity)' in script
    assert "delete pendingVideoRenderRequests[requestIdentity]" in script
    assert "while (pendingIdentities.length > 20)" in script


def test_operator_ui_blocks_storyboard_mutation_while_render_is_active():
    script = files("mrhub").joinpath("web/app.js").read_text(encoding="utf-8")
    controls = script.split("function syncStoryboardRenderButtons", 1)[1].split(
        "function lockVideoStoryboardControls", 1
    )[0]

    assert "const renderMayBeActive = Boolean(activeVideoRenderId)" in controls
    assert "const mutationBlocked = videoStoryboardControlsLocked || renderMayBeActive" in controls
    assert '$("#video-storyboard-save").disabled = !hasSelectedPrompt || mutationBlocked' in controls
    assert '$("#video-storyboard-prepare-render-timeline").disabled = !hasDraft || mutationBlocked' in controls

    cancel = script.split("async function cancelVideoRender", 1)[1].split(
        "async function downloadRenderedVideo", 1
    )[0]
    assert "const renderId = activeVideoRenderId" in cancel
    assert "const renderIdentity = activeVideoRenderIdentity" in cancel
    assert "activeVideoRenderId !== renderId" in cancel
    assert "activeVideoRenderIdentity !== renderIdentity" in cancel
