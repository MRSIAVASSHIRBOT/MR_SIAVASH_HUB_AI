# Tool registry operations

The tool layer uses explicit registration and typed input/output contracts.
The authenticated `GET /tools` endpoint lists only registered tools and
publishes their JSON schemas, risk class, required permissions, and external
side-effect declaration.

## Invocation

`POST /tools/{tool_name}/invoke` accepts a JSON object under `payload`.
Unknown tools return 404 and invalid input returns a sanitized 422 response.
The API does not accept client-supplied permission grants or approval flags:
policy context is supplied by trusted server code only.

The initial built-in `text.echo` tool is deterministic and has no external
side effects. It exists to exercise the registry contract; it is not an AI
model or an external integration.

## Policy boundaries

- Tool names must be explicitly registered; unknown names fail closed.
- Inputs and outputs are validated against registered Pydantic models.
- Required permissions are evaluated by the server-side policy engine.
- External side effects and high-risk operations require explicit approval.
- Tool handlers are never exposed in the catalog or API response.
- No shell, arbitrary Python, network access, or dynamic tool loading is
  provided by the initial registry.


## Owner-scoped permission grants

The authenticated owner can manage a small, explicit allow-list of tool permissions:

- GET /tools/grants lists only the current owner's active grants.
- PUT /tools/grants/cloudflare.read creates or renews a read-only Cloudflare metadata grant.
- DELETE /tools/grants/cloudflare.read revokes that grant.

Grants expire automatically. The default lifetime is one hour; callers may request 60 seconds through 24 hours. Unsupported permissions are rejected. Grant and revoke mutations write their audit events in the same SQLite transaction as the permission change.

Tool invocation loads active permissions from the authenticated session owner in the server-side database. The request body cannot supply permissions or approval flags. Every invocation outcome records only allow-listed metadata and a generated correlation ID; input payloads, provider responses, and credentials are not recorded.
