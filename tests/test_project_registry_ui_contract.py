from pathlib import Path


def test_project_registry_refresh_is_bounded_and_non_blocking_for_core_overview():
    source_path = Path(__file__).resolve().parents[1] / "backend/mrhub/web/app.js"
    source = source_path.read_text(encoding="utf-8")

    registry_start = source.index("async function loadProjectRegistry()")
    overview_start = source.index("async function loadOverview()", registry_start)
    download_start = source.index("async function downloadMediaAsset", overview_start)
    registry_source = source[registry_start:overview_start]
    overview_source = source[overview_start:download_start]

    assert "new AbortController()" in registry_source
    assert "signal: controller.signal" in registry_source
    assert "clearTimeout(timeoutId)" in registry_source
    assert "void loadProjectRegistry();" in overview_source
    assert "await loadProjectRegistry()" not in overview_source
    assert "Promise.allSettled([" in overview_source

    assert 'latestCi.branch ? " · شاخه: " + latestCi.branch' in source
    for endpoint in (
        'api("/health"',
        'api("/ready"',
        'api("/models/providers")',
        'api("/tasks?limit=12")',
        'api("/jobs/summary")',
        'api("/agent/workflows?limit=50")',
    ):
        assert endpoint in overview_source


def test_project_registry_renders_local_worker_heartbeat_provenance():
    source_path = Path(__file__).resolve().parents[1] / "backend/mrhub/web/app.js"
    source = source_path.read_text(encoding="utf-8")

    assert 'observation.details' in source
    assert 'runtime.worker_heartbeat_age_seconds' in source
    assert 'runtime.schema_version' in source
    assert 'تازگی heartbeat:' in source
