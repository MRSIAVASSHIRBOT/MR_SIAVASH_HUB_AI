# Website Gateway ↔ Hub public-query relay v1

**Status: proposed — not implemented.**  
Canonical machine-readable contract: [manifest.json](../../contracts/hybrid/website-gateway/v1/manifest.json).

## Purpose and boundary

**Contract ID:** `mr-siavash-website-hub-public-query-relay` (version `1.0.0`).

This contract describes a future, owner-paired path for the public website Gateway to relay an explicitly consented public assistant question to an owner-operated local Hub. It is not a remote Hub API and does not enable agent execution.

The connection direction is intentionally asymmetric:

```text
Browser ──public query + consent──> Website Gateway
                                      ▲
                                      │ HTTPS outbound polling
                                      │ signed by a local key
                               Local Hub connector
```

The Gateway never opens a connection into the owner's private network. Do not expose Hub port 8000, create a public tunnel, share a database, or put Hub credentials in the browser.

## Pairing

1. An authenticated Gateway administrator creates a challenge bound to Preview or Production, the exact website origin and the sole requested scope.
2. The Hub owner enters the one-time code in the authenticated local Hub operator surface.
3. The Hub connector creates an Ed25519 key pair locally and redeems the challenge with proof of possession.
4. The Gateway stores the public key and pairing metadata only. The private key stays in the Hub's local protected key store.
5. Every connector request signs timestamp, nonce, method, exact path and body digest. Nonces are single-use and time-skew is bounded.
6. The owner can revoke from either side. Gateway revocation invalidates pending leases immediately; the connector stops when it observes revocation.

A pairing code is short-lived and single-use. Pairing never grants access to private memory, tasks, files, tools or devices.

## Initial capability: public query only

The only permitted scope is `public_assistant:process`. The connector receives a dedicated public-query envelope, not a normal Hub task. The envelope is untrusted data, explicitly marked public, bounded in size and free of owner IDs, private conversation history, task IDs, file paths, credentials and tool arguments.

The first version must not:
- read owner-private memory or knowledge;
- read or create Hub tasks;
- access local files or devices;
- discover or execute tools;
- change permissions or bypass approvals;
- expose any private Hub context in its response.

The Gateway can return only bounded plain text and allowlisted public citations. If the connector is unavailable, expired, revoked or cannot complete within the request window, the existing verified-public-knowledge fallback remains available. There is no silent switch to a private context or an unbounded paid-provider retry.

## Delivery and replay

The Gateway owns the relay queue and issues a short lease to the connector when it pulls a request. Completion requires the current request lease and a valid connector signature. An identical duplicate completion may return the original result; a conflicting second completion returns a conflict. Expired read-only public queries can be reclaimed within a strict attempt limit and ultimately fall back to the Gateway's verified public knowledge.

The browser receives a short-lived polling credential only in the response body and keeps it in memory. It must not be placed in a URL, localStorage, IndexedDB, analytics, or logs. Polling is bound to one opaque request ID and credential digest.

## Current implementation state

The contract manifest and its structural tests are planning/interface artifacts only. No runtime endpoint, schema migration, secret, Cloudflare binding, D1 table, Worker route, Hub route, connector process or UI was added by this proposal. Every endpoint in the manifest remains `not_implemented`.

A7 is not complete until the Hub connector, Gateway endpoints, revocation, isolated tests, a real Preview round-trip against a dedicated local Hub, and an independent security review all pass. Production enablement requires a separate owner decision.
