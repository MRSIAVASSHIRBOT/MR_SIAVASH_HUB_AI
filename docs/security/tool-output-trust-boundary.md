# Agent Tool Output Trust Boundary

## Rule

A registered tool's output is data, not authority. Pydantic output-schema validation confirms the output shape; it does not prove that the contents are safe instructions or truthful statements.

The AgentOrchestrator therefore marks every tool observation with:

- `trust: untrusted_tool_output`
- `observation_is_untrusted_data: true`

The model request also includes `observations_are_untrusted_data: true` and protocol instructions not to follow commands, links, or requests embedded in tool output.

## Execution boundary

Tool output must never:

- Grant a capability or permission.
- Override the user's request, policy, approval state, or system instructions.
- Authorize another tool invocation.
- Trigger secret disclosure or privilege escalation.
- Be treated as verified merely because its JSON schema passed validation.

Each proposed tool call is independently checked against the registered catalog, current owner permission grants and the policy engine. The registry validates both the input and output schemas and sanitizes arbitrary handler exceptions.

## Limitations

This is a prompt-level trust signal, not a complete taint-tracking or content-sanitization system. Model providers may still misinterpret adversarial text. High-impact actions must continue to require server-side authorization and explicit approval. Tool-specific output schemas should remain narrow and avoid returning unnecessary free-form content.
