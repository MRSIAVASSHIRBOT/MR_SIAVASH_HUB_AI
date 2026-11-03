# Optional MCP Tool Bridge

## Purpose

The optional MCP bridge exposes the existing Hub tool registry to compatible MCP hosts. It does not create a second tool registry, add new built-in actions, or connect to arbitrary MCP servers. The Hub remains the policy authority.

Upstream: https://github.com/modelcontextprotocol/python-sdk  
Protocol: Model Context Protocol, Streamable HTTP transport  
SDK: `mcp==2.3.0` (optional extra)  
License: MIT  
Python: 3.11+  
Cost: no license fee; the bridge itself makes no model-provider or hosted-service calls.

## Install and start

Install the optional integration:

```powershell
python -m pip install -e ".[mcp]"
```

Enable it explicitly in the deployment environment:

```powershell
$env:MRH_MCP_ENABLED = "true"
$env:MRH_MCP_HOST = "127.0.0.1"
$env:MRH_MCP_PORT = "8765"
mrhub-mcp
```

The endpoint is `http://127.0.0.1:8765/mcp`. The service is a separate process and is not started by the FastAPI application or worker. It binds only to numeric loopback IP literals (`127.0.0.1` or `::1`); hostnames such as `localhost` are rejected to avoid relying on name resolution for the security boundary. Do not expose it through a public reverse proxy. The SDK's default localhost Host/Origin protection remains enabled.

## Exposed tools

- `hub.list_tools`: returns the canonical Hub registry catalog as JSON.
- `hub.invoke_tool`: invokes a named registered Hub tool through `ToolRegistry.invoke`.

The bridge currently exposes only tools already registered in the process. The initial built-in catalog contains the deterministic `text.echo` tool. This is an interoperability slice, not a broad automation integration.

## Security boundaries and deployment warning

- The MCP SDK is an optional, exact-pinned dependency; core installs do not import it.
- Only Streamable HTTP is used. No stdio subprocess launching, arbitrary MCP server discovery, or remote MCP client connection is provided.
- Binding is restricted to numeric loopback IP literals and disabled by default.
- The transport uses `stateless_http=True`: requests do not retain MCP session state. Consequently, the SDK's `max_sessions` and `session_idle_timeout` options are not active resource limits in this configuration and are intentionally not presented as protections.
- The request body is capped at 1 MiB before parsing.
- **Loopback is not per-user authentication.** Any process or local user able to connect to the host's loopback interface may be able to call the MCP endpoint. Do not enable this service on shared or multi-user machines unless an additional, independently reviewed access-control boundary is deployed. Do not assume that binding to 127.0.0.1 isolates the service from other local processes.
- Every invocation passes through the existing Hub schema validation and policy engine.
- The bridge supplies no permission grants and cannot mark an operation as user-approved. Tools requiring permissions, high-risk approval, or external-side-effect approval are denied by the existing policy engine.
- Error responses contain stable codes only; handler exception details, credentials, and payload contents are not logged or returned.
- Tool descriptions and schemas are metadata, not authorization. The Hub registry remains the source of truth.

## Configuration

| Variable | Default | Meaning |
|---|---:|---|
| `MRH_MCP_ENABLED` | `false` | Explicitly enable the separate MCP service |
| `MRH_MCP_HOST` | `127.0.0.1` | Numeric loopback bind address only (`127.0.0.1` or `::1`) |
| `MRH_MCP_PORT` | `8765` | Local service port |

## Validation

The optional test suite uses the SDK's in-memory client/server transport and test doubles; it does not open a network listener or contact third-party services. Startup tests verify the disabled-by-default guard, reject all hostname/non-loopback binds, accept both numeric IPv4/IPv6 loopback literals, validate port bounds, and assert the actual stateless transport and request-body limit:

```powershell
python -m pip install -e ".[dev,mcp]"
pytest tests/test_mcp_integration.py tests/test_mcp_service.py
ruff check backend/mrhub/integrations/mcp_server.py backend/mrhub/mcp_service.py tests/test_mcp_integration.py tests/test_mcp_service.py
```

A real host acceptance test is still required before enabling MCP in a deployment. No production host has been connected or tested by this change.

## Upstream review and limitations

The official SDK repository is MIT-licensed, supports Python 3.11+, and has an active v2 release line. The v2 line includes transport and authentication changes; the adapter pins the reviewed 2.3.0 release rather than floating across major versions. The SDK brings a transitive dependency tree, so run the project's dependency audit after installing the optional extra and review the resulting lock/SBOM before production use.

The bridge is intentionally server-only. It does not install third-party MCP servers, execute commands, connect to stdio servers, or automatically grant access to tools. Those capabilities require separate threat modeling, explicit allowlists, credential scoping, and approval UX.
