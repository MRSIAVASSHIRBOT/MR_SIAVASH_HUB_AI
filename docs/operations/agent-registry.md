# Specialist agent registry

The authenticated `GET /agent/registry` endpoint exposes a metadata-only
manifest of server-reviewed specialist profiles.

## Registry contract

- Profiles are source-controlled and registered only during trusted application composition.
- Profile versions are positive integers. The current profiles start at version 1.
- Names are unique within the active registry; duplicate registration fails.
- Each profile has an immutable tool allow-list and a bounded turn count.
- The default registry is frozen after construction. Registration after freeze fails and the backing mapping is read-only.
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
