# Specialist agent registry

## Phase mapping

Under the active H0–H32 delivery sequence:

- **H20 — Agent Registry & Lifecycle:** reviewed specialist profile versions,
  immutable allow-lists, freeze-on-composition, and metadata-only registry discovery.
- **H21 — Multi-Agent Orchestration:** bounded sequential specialist handoff,
  with at most two children and no recursive delegation.
- **H22 — Agent Intelligence & Coordination:** parent synthesis of explicitly
  untrusted child observations, including preservation of conflicting assessments.

The repository also contains an older 73-phase baseline with different phase
numbers. That legacy numbering remains historical input for a later roadmap
crosswalk; it does not override the active H0–H32 sequence. This PR is a scoped
H20–H22 capability slice, not acceptance of any complete phase.

The authenticated `GET /agent/registry` endpoint exposes a metadata-only
manifest of server-reviewed specialist profiles.

## Registry contract

- Profiles are source-controlled and registered only during trusted application composition.
- Profile versions are positive integers. The current profiles start at version 1.
- Names are unique within the active registry; duplicate registration fails.
- Each profile has an immutable tool allow-list and a bounded turn count.
- The default registry is frozen after construction. Registration after freeze fails and the backing mapping is read-only.
- Metadata composition does not initialize optional tool integrations; the owner-specific runtime registry validates every profile tool scope before execution.
- The manifest contains stable SHA-256 profile fingerprints. The digest covers the reviewed instructions and public metadata, but the instructions themselves are never returned.
- The manifest is sorted by profile name and includes an explicit statement that discovery does not authorize execution.

## API

`GET /agent/registry` requires an authenticated owner session and returns
`agent_registry_manifest.v1`. Each agent entry includes its name, version,
description, permitted tool names, maximum turns, and profile digest.

The endpoint does not return profile instructions, provider prompts, user
context, tool payloads, or secrets. It does not support runtime registration,
grant permissions, run agents, or dispatch tools. HTTP responses inherit the
application's `Cache-Control: no-store` policy.

## Trust boundary

Agent names and manifest metadata are discovery hints, not proof of capability
availability for a particular owner and not authorization. Every delegated
execution continues to use the caller's tool registry, current permission
provider, policy engine, and bounded orchestration budgets. A profile's
allow-list can only reduce the tool set; it cannot add a tool or override
server policy.

Changing reviewed profile instructions changes the profile digest. Updating a
profile therefore remains a source-controlled code review and release action,
not a model-generated mutation.


## Bounded multi-agent handoff

The existing supervisor loop can hand work to at most two registered specialists
sequentially. Each child receives the supplied evidence context, a reviewed
role instruction, a narrower tool registry, and a share of the remaining input,
tool-call, and runtime budgets. Children cannot delegate recursively.

Each child result returns to the supervisor as an explicitly untrusted
observation. The supervisor remains responsible for the final synthesis;
specialist output does not authorize tools, change permissions, or prove goal
completion. Regression tests cover two distinct specialist handoffs and ensure
conflicting assessments remain visible to the parent.

This is bounded sequential coordination, not parallel execution, a peer-to-peer
agent channel, or a formal consensus protocol. The system does not claim that
two specialist opinions are independent proofs or that conflicts are
automatically resolved.
