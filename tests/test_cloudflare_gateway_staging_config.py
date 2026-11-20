from __future__ import annotations

import tomllib
from pathlib import Path


def test_hub_staging_worker_is_isolated_and_has_no_committed_credentials():
    repository_root = Path(__file__).resolve().parents[1]
    config_path = repository_root / "cloudflare" / "gateway" / "wrangler.toml"
    config = tomllib.loads(config_path.read_text(encoding="utf-8"))

    assert config["name"] == "mr-siavash-hub-gateway-staging"
    assert config["main"] == "src/index.js"
    assert config["workers_dev"] is True
    assert config["preview_urls"] is False
    assert "routes" not in config
    assert "route" not in config
    assert "custom_domains" not in config
    assert "vars" not in config
    assert "secrets" not in config
    assert "d1_databases" not in config
    assert (config_path.parent / config["main"]).is_file()

    config_text = config_path.read_text(encoding="utf-8")
    assert "CF_API_TOKEN" in config_text  # names only; secret values stay external
    assert "GATEWAY_AUTH_TOKEN" in config_text
    assert "CF_ACCOUNT_ID" in config_text
    assert "CF_ZONE_ID" in config_text
    assert "Bearer " not in config_text
