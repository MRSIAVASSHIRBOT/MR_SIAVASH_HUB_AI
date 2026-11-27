# PromptForge Studio

PromptForge Studio is a browser-local prompt engineering workbench integrated into the Hub operator UI at `/ui/promptforge.html`.

## Included in this first integration

- Image prompt builder with visual direction, camera, lighting, composition, constraints, negative prompt, aspect ratio, and model-target profiles.
- Video prompt builder with motion, camera movement, timing, scene sequence, continuity, and audio direction.
- System-prompt builder for assistants and agents, including role, goals, workflow, tool permissions, safety rules, and output format.
- Starter templates, three deterministic creative variants, structural checklist, word/character metrics, copy/download, and local prompt history.
- JSON backup export/import.

## Architecture and trust boundaries

- This is a static, browser-side tool served by the existing FastAPI `/ui` StaticFiles mount. It adds no API route, database table, migration, Python dependency, provider credential, or background job.
- CSS and JavaScript are separate same-origin assets (`promptforge.css`, `promptforge.js`) so the existing restrictive `/ui` Content Security Policy remains intact; no inline script/style exception is introduced.
- Prompt history is stored in the current browser's localStorage. It is not synchronized to Hub memory or uploaded to a provider.
- Prompt construction is deterministic template assembly, not LLM-powered optimization. Model names are output-target profiles only; this module does not call those providers or generate image/video media.
- Imported JSON is untrusted user data. The browser-only library must not be treated as an authoritative source of policy, permissions, or executable instructions.
- The module does not perform publishing, execute tools, or change Hub policy.

## Use

Start the local Hub using the existing quick-start instructions, sign in to the operator UI, and open **PromptForge Studio** from the workspace. The standalone local page is also available at `/ui/promptforge.html`.

## Follow-up integration phases

1. Add an authenticated, owner-scoped PromptForge API for optional server-side prompt projects and version history.
2. Add a provider-neutral optimization interface that requires explicit provider selection and consent before any remote prompt/context is sent.
3. Add reference-image analysis, model-specific validation, evaluation runs, and iterative refinement behind bounded jobs and the existing policy/audit system.
4. Add contract tests and operator telemetry without collecting prompt contents by default.

These follow-up phases are planned, not implemented by this static module.
