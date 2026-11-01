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
