# Telegram Integration Operations

## Local topology and trust boundary

Keep MR_SIAVASH_HUB_AI bound to loopback (default 127.0.0.1). A Telegram client, if intentionally enabled, must use an outbound connection to the local Hub. Do not expose the Hub port publicly, create a public tunnel, or route private Hub credentials through the public MR_SIAVASH_AI Gateway.

## Owner pairing and least privilege

1. Start the Hub locally and authenticate to its owner API/UI.
2. Obtain the intended client's numeric Telegram user ID and stable client UUID through a trusted private setup flow.
3. In the authenticated Hub UI, create a pairing challenge for those exact values.
4. Keep the default status:read scope unless another capability is required.
5. Grant tasks:read, tasks:create or memory:search only after considering the data/action each scope exposes.
6. Transfer the one-time code only to the intended private client channel. The code expires after five minutes and can be used once.
7. Review the paired-client list and revoke any client that is lost, replaced or no longer trusted.

The owner UI defaults to status-only access. The API applies the same status-only default when the scopes field is omitted; client-provided claims do not override Hub-side scope checks.

## Credential lifecycle

- Access tokens expire after 15 minutes.
- Refresh tokens expire after 30 days and are bound to the paired client and Telegram numeric ID.
- The Hub stores only SHA-256 token hashes.
- Owner revocation invalidates the paired client's access and refresh credentials.
- Raw tokens and pairing codes must never be logged, pasted into public channels or committed.
- The client must use an OS-backed or equivalently protected credential store. If that cannot be verified, do not enable live pairing.

## API capabilities

- status:read: read the minimal authenticated client status.
- tasks:read: list only tasks attributed to the exact paired client; cross-client task history is not returned.
- tasks:create: submit bounded task requests through the Hub PolicyEngine. High-risk or unregistered task types remain waiting for owner approval.
- memory:search: search owner memory only when the owner explicitly grants this scope.

No agent execution, approval decisions, content publishing, destructive actions or arbitrary tools are exposed through this initial integration.

## Current verification status — 2026-11-09

- Hub pairing API, owner-facing pairing/revocation controls, scoped authentication, task/memory routes and per-client task isolation are implemented on Hub main.
- Hub CI, Windows launcher validation, video integration and defensive scan completed successfully on commit 79c2be63e9a3379f1e769c90074276d6483be37c.
- The Hub API and local controls have automated coverage, but no live Telegram pairing, client-side credential-store verification, production bot deployment or end-to-end Telegram smoke test has been verified.
- Keep the client integration disabled until its local opt-in and protected credential handling are independently verified.

Remote Hub hosting remains out of scope until its threat model, transport, access controls and deployment are separately reviewed.
