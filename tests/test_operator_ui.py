from importlib.resources import files

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
    assert 'id="agent-run-result"' in response.text
    assert 'id="agent-queue-button"' in response.text
    assert 'id="agent-queued-workflow-id"' in response.text
    assert 'id="agent-queued-refresh-button"' in response.text
    assert 'id="agent-queued-cancel-button"' in response.text
    script = client.get("/ui/app.js").text
    assert 'api("/agent/run"' in script
    assert 'api("/agent/model-runs"' in script
    assert '"/agent/model-run-workflows/"' in script
    assert "pendingModelRunIdempotencyKey = crypto.randomUUID()" in script
    assert 'headers: { "Idempotency-Key": pendingModelRunIdempotencyKey }' in script
    assert "context_sources" in script
    assert "setInterval(" not in script
