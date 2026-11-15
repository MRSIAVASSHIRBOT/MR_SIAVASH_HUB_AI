# Hybrid video-generation routing

The hybrid route planner is provider-neutral and deliberately side-effect free. It does not inspect the machine, contact providers, submit jobs, or spend money.

## Routing order

1. Filter registered adapters by duration, aspect-ratio, and resolution capability.
2. Prefer a compatible local adapter when the worker supplies a measured local capacity snapshot that satisfies its declared RAM and VRAM requirements.
3. Consider hosted adapters only when the request carries both explicit approval to process its data remotely and explicit approval to incur remote spend.
4. Require a known per-job cost estimate and enforce the caller-approved USD cap.
5. If any required fact is unknown, fail closed with a stable reason code.

The local capacity snapshot must be produced by trusted server-side runtime measurement. It must not be accepted from an untrusted browser/client. Unknown RAM or required VRAM is not treated as sufficient capacity. A local route reports zero provider charge; this is not a claim that local electricity or hardware has zero operating cost.

Hosted cost estimates are adapter-supplied estimates, not invoices or guarantees. A future hosted adapter must document how it calculates estimates and must reject submission if the final provider quote exceeds the approved cap. This planner never creates an approval or treats the global architecture choice (hybrid) as consent to send a particular prompt, source asset, or other private data remotely.

## Current implementation boundary

The generation_routing module implements deterministic selection and returns a decision only. It does not start generation. The existing generation submission endpoint continues to require an explicit provider/model choice and the existing task approval workflow. Wiring this planner into automatic selection requires a server-side hardware probe contract, per-request consent fields and UI, provider pricing metadata, and integration tests. No provider is registered by default.

The current Dell Precision M6800 user device is not automatically assumed to be the generation host. The deployment worker's actual RAM/VRAM and accelerator availability must be measured in its own environment before a local adapter can be considered viable.
