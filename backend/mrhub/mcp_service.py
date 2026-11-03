"""Explicit, numeric-loopback-only MCP service entry point.

Install the optional dependency with: python -m pip install -e ".[mcp]"
Enable it with MRH_MCP_ENABLED=true, then run: mrhub-mcp
"""

from __future__ import annotations

from mrhub.config import get_settings
from mrhub.integrations.mcp_server import create_mcp_server


def main() -> None:
    settings = get_settings()
    if not settings.mcp_enabled:
        raise SystemExit(
            "MCP service is disabled. Set MRH_MCP_ENABLED=true to start it explicitly."
        )
    if settings.mcp_host not in {"127.0.0.1", "::1"}:
        raise SystemExit("MCP service may bind only to a numeric loopback address.")

    server = create_mcp_server()
    server.run(
        transport="streamable-http",
        host=settings.mcp_host,
        port=settings.mcp_port,
        streamable_http_path="/mcp",
        stateless_http=True,
        max_request_body_size=1_048_576,
    )


if __name__ == "__main__":
    main()
