# Goal-to-Prompt Decision Analysis

## Purpose

The preflight analyser adds a deterministic, bounded interpretation layer before planning. It reports advisory signals for complexity, research needs, tool needs, information gaps and input modalities. It does not execute a model, invoke a tool, grant permission or authorize an external action.

## Output

`GoalDecisionAnalysis` contains:

- A heuristic complexity score (0–100) and low/moderate/high band.
- `research_required`, based on explicit freshness, comparison, source and research cues.
- `tool_use_required`, based on action language or declared WorkOrder capabilities.
- `information_gaps` and `clarification_recommended`, including missing outcome, missing action scope and unresolved assumptions.
- Required input modalities (text, vision, audio) and whether the registered tool catalog is relevant.
- Machine-readable reason codes and explicit non-authorization/non-execution flags.

The score is a transparent routing heuristic, not a learned prediction, guaranteed estimate of effort, or acceptance criterion. The analysis is reproducible for the same inputs.

## API

`POST /agent/work-orders/analyze` requires an authenticated session. It performs local deterministic analysis only; it does not select an inference provider or call an LLM.

`POST /agent/work-orders/plan` additionally returns `decision_analysis` generated from the validated WorkOrder. The current planning route continues to use its configured local-only model policy; decision signals are reported, not used to silently switch provider modes.

## Trust and execution boundary

- Goal text and generated WorkOrders remain untrusted input.
- Tool catalog relevance is not a permission grant.
- Capability presence, permission grants, policy authorization and user approval remain separate checks.
- Research-required does not assert that research has been performed.
- A modality signal does not prove that an available provider supports the modality.
- Ambiguous or high-impact scope is reported for review; the analyser does not guess missing targets or expand permissions.
- Heuristic false positives and false negatives are possible. Use an explicit WorkOrder and review its assumptions, scope and acceptance criteria before execution.

## Validation

Unit tests cover information-only requests, current-source research cues, tool-use cues, image/audio inputs, underspecified goals, unresolved WorkOrder assumptions, scope gaps and input bounds. API tests verify authentication and prove that the preflight endpoint does not select or invoke an inference provider.