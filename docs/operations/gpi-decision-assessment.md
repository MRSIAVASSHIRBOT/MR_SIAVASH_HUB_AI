# GPI/AWI decision assessment

The authenticated `POST /agent/work-orders/plan` response now includes a deterministic decision assessment alongside the validated WorkOrder, ExecutionPlan, and capability-gap report.

## Assessment dimensions

- **Complexity:** a deterministic, bounded score based on plan steps, dependency edges, capability requirements, acceptance criteria, verification work, assumptions, missing information, research questions, and server-derived risk class. It is an explainable planning heuristic, not a model-quality score or execution budget.
- **Missing information:** GPI may identify unresolved information and propose bounded clarification questions. These are advisory and should be resolved before any later execution decision.
- **Research:** GPI may flag that current or external evidence is required and provide research questions. The planning endpoint does not start a search, fetch remote content, or call an external research provider.
- **Tools:** only exact, case-insensitive capability-name matches against the server-owned registry are surfaced as candidate tools. Missing capabilities remain explicit. A match does not grant permission or authorize invocation.
- **Execution order:** AWI dependencies are rendered in a stable topological order, preserving input order for independent steps. The assessment does not invoke those steps.
- **Model:** the response records the actual model selected by the existing capability-aware router for local text-only planning. This does not claim that the provider is suitable for every future modality or execution task.

The response explicitly sets `planning_only`, `authorization_checked=false`, `research_started=false`, `execution_started=false`, and `tools_executed=false`. All generated and derived fields remain untrusted advisory data. Permissions and policy must be re-evaluated at execution time.
