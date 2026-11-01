# Agent core operations

The authenticated `POST /agent/plan` endpoint connects the model router,
registered tool catalog, and server-side policy engine into one planning
response. A request supplies a goal, required model capabilities, local
preference, and up to five explicitly named tools with typed payloads.

## Planning behavior

1. The model router selects a registered model matching the requested
   capabilities.
2. Each requested tool is looked up in the allow-listed tool registry.
3. Tool input is validated against its registered Pydantic schema.
4. The policy engine classifies each tool step as ready, approval-required,
   blocked, invalid-input, or not-registered.
5. The API returns an ordered plan and an execution-readiness flag.

## Current execution boundary

This is the initial deterministic planning core, not an autonomous LLM agent.
It does not send the goal to a model, run inference, execute tools, download
models, or create external side effects. `decision_mode` is always
`plan_only`; `model_inference_started` and `tools_executed` are always
false. The endpoint is designed to establish orchestration contracts before
adding separately approved execution and persistent multi-step workflows.
