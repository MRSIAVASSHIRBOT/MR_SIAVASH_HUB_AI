"""Optional MCP bridge exposing only policy-approved Hub tools."""

from __future__ import annotations

import json
from typing import Any

from mrhub.tools.builtins import build_tool_registry
from mrhub.tools.registry import (
    ToolExecutionError,
    ToolPolicyError,
    ToolRegistry,
)


def create_mcp_server(registry: ToolRegistry | None = None):
    """Build an MCP server backed by the canonical Hub tool registry.

    The MCP SDK is imported lazily so the core application has no mandatory
    dependency on MCP. No subprocess transport, arbitrary server discovery,
    or automatic grants are enabled by this bridge.
    """
    try:
        from mcp.server import MCPServer
    except ImportError as exc:  # pragma: no cover - exercised in minimal installs
        raise RuntimeError(
            "MCP support is optional; install the project with the [mcp] extra"
        ) from exc

    tool_registry = registry if registry is not None else build_tool_registry()
    server = MCPServer(
        "MR_SIAVASH_HUB_AI",
        version="0.1.0",
        instructions=(
            "Only invoke explicitly listed Hub tools. Tool calls are independently "
            "validated by the Hub policy engine. This server grants no permissions."
        ),
    )

    def list_hub_tools() -> str:
        """Return the registered Hub tool catalog as JSON."""
        return json.dumps(tool_registry.catalog(), ensure_ascii=False, separators=(",", ":"))

    def invoke_hub_tool(name: str, payload: dict[str, Any] | None = None) -> str:
        """Invoke one registered Hub tool without implicit permission grants."""
        try:
            result = tool_registry.invoke(name, payload or {})
        except ToolPolicyError:
            response = {"ok": False, "error_code": "policy_denied"}
        except LookupError:
            response = {"ok": False, "error_code": "tool_not_registered"}
        except (ToolExecutionError, ValueError, TypeError):
            response = {"ok": False, "error_code": "tool_invocation_failed"}
        else:
            response = {"ok": True, "result": result}
        return json.dumps(response, ensure_ascii=False, separators=(",", ":"))

    server.add_tool(
        list_hub_tools,
        name="hub.list_tools",
        description="List Hub tools that are registered for this MCP process.",
    )
    server.add_tool(
        invoke_hub_tool,
        name="hub.invoke_tool",
        description=(
            "Invoke a registered Hub tool. The Hub validates its schema and "
            "applies its own policy; no permissions or approvals are inferred."
        ),
    )
    return server
